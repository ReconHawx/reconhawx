#!/usr/bin/env python3
"""
NATS result publisher for worker tasks.

INVARIANT: Child process stdout is the only stream forwarded to the runner
(NATS ``output`` field). Application logs and subprocess stderr mirror must use
stderr only, never print() to default stdout, or downstream JSON parsing breaks.
"""
import logging
import subprocess
import sys
import os
import json
import time
import asyncio

from worker_logging import configure_worker_logging

configure_worker_logging()
import nats  # noqa: E402  # import after logging so nats/urllib3 respect levels

# Reduce chunk size to avoid NATS 'maximum payload exceeded' errors
# NATS default max payload is 1MB, so set to 500KB to be safe for encoded messages with metadata
CHUNK_SIZE = 500 * 1024  # 500KB chunks (reduced from 900KB)
# Estimate for JSON overhead and encoding expansion
JSON_OVERHEAD = 200  # Conservative estimate for JSON structure and metadata

log = logging.getLogger(__name__)


async def publish_result(
    output, success, is_final=True, chunk_num=None, total_chunks=None, max_retries=2
):
    """Publish the task result to the output queue"""
    # Get task information from environment variables
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    task_id = os.getenv("TASK_ID", "unknown")
    workflow_id = os.getenv("WORKFLOW_ID", "unknown")
    step_name = os.getenv("STEP_NAME", "unknown")
    step_num = os.getenv("STEP_NUM", "0")
    output_subject = os.getenv("OUTPUT_QUEUE_SUBJECT")
    if not output_subject:
        log.error("OUTPUT_QUEUE_SUBJECT environment variable not set")
        return False

    log.info("Using subject: %s (workflow_id: %s)", output_subject, workflow_id)

    # Get current time for chunk tracking
    current_time = time.time()

    # Create result message
    result = {
        "task_id": task_id,
        "workflow_id": workflow_id,
        "step_name": step_name,
        "step_num": int(step_num),
        "success": success,
        "output": output,
        "execution_time": current_time,
        "is_final": is_final,
        "chunk_num": chunk_num,
        "total_chunks": total_chunks,
        "timestamp": current_time,  # Added explicit timestamp for chunk tracking
    }

    # Validate the message size before sending
    encoded_message = json.dumps(result).encode()
    message_size = len(encoded_message)

    # NATS typically has a 1MB limit; warn if we're getting close
    if message_size > 1000000:  # 1MB
        log.warning(
            "Message size %s bytes exceeds NATS typical limit of 1MB", message_size
        )
        return False

    # Add retry logic
    for retry in range(max_retries + 1):
        try:
            # Connect to NATS
            nc = await nats.connect(
                nats_url, connect_timeout=5, reconnect_time_wait=1
            )
            js = nc.jetstream()

            # Publish the result to the workflow-specific subject
            ack = await js.publish(output_subject, encoded_message)
            log.info(
                "Published %s result to %s with sequence %s",
                "final" if is_final else f"chunk {chunk_num}",
                output_subject,
                ack.seq,
            )

            # Close the connection
            try:
                await nc.drain()  # Remove timeout parameter
            except Exception:  # noqa: BLE001
                await nc.close()

            return True
        except Exception as e:  # noqa: BLE001
            log.error(
                "Error publishing result (attempt %s/%s): %s",
                retry + 1,
                max_retries + 1,
                e,
            )
            if retry < max_retries:
                # Exponential backoff between retries
                wait_time = 0.5 * (2**retry)
                log.info("Retrying in %s seconds...", wait_time)
                await asyncio.sleep(wait_time)
            else:
                log.error("Failed to publish result after %s attempts", max_retries + 1)
                return False


async def send_chunked_output(output, success):
    """Split output into chunks by line and send them to NATS"""
    # If output is small enough, send as a single message
    if len(output) <= CHUNK_SIZE - JSON_OVERHEAD:
        success = await publish_result(
            output, success, is_final=True, chunk_num=1, total_chunks=1
        )
        if not success:
            log.error(
                "Failed to send single message chunk, output size: %s", len(output)
            )
        return

    # Split the output into lines
    lines = output.split("\n")

    # Calculate total number of chunks based on lines and size
    chunks = []
    current_chunk = []
    current_size = 0
    effective_chunk_size = CHUNK_SIZE - JSON_OVERHEAD  # Account for JSON overhead

    log.info(
        "Splitting output of %s bytes into chunks of max %s bytes",
        len(output),
        effective_chunk_size,
    )

    for line in lines:
        # Add newline character length except for the first line in a chunk
        line_size = len(line) + (1 if current_size > 0 else 0)  # +1 for '\n'

        # Force chunk break if a single line would exceed chunk size
        if line_size > effective_chunk_size:
            log.warning(
                "Very long line detected (%s bytes), breaking it into multiple chunks",
                line_size,
            )
            # Finalize current chunk if not empty
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_size = 0

            # Break the long line into multiple chunks of effective_chunk_size
            for i in range(0, len(line), effective_chunk_size):
                line_chunk = line[i : i + effective_chunk_size]
                chunks.append(line_chunk)
                log.info("Created chunk from long line: %s bytes", len(line_chunk))

        # If adding this line would exceed effective chunk size and we already have content,
        # finalize the current chunk and start a new one
        elif (
            current_size + line_size > effective_chunk_size and current_chunk
        ):
            chunks.append("\n".join(current_chunk))
            log.info("Finalized chunk: %s bytes", current_size)
            current_chunk = [line]
            current_size = len(line)
        else:
            current_chunk.append(line)
            current_size += line_size

    # Add the last chunk if it has content
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        log.info("Added final chunk: %s bytes", current_size)

    total_chunks = len(chunks)
    log.info(
        "Output split into %s chunks respecting line boundaries", total_chunks
    )

    # Verify chunk sizes and warn if any might be too large
    max_chunk_size = 0

    # Function to split a chunk into smaller chunks
    def split_chunk(chunk, max_size):
        """Split a chunk into smaller chunks of max_size bytes"""
        result = []
        for j in range(0, len(chunk), max_size):
            sub_chunk = chunk[j : j + max_size]
            result.append(sub_chunk)
        return result

    # First pass: identify and split oversized chunks
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        chunk_size = len(chunk)
        max_chunk_size = max(max_chunk_size, chunk_size)

        # Verify that chunk size plus overhead is within NATS limit
        estimated_message_size = chunk_size + JSON_OVERHEAD
        if estimated_message_size > CHUNK_SIZE:
            log.warning(
                "Chunk %s/%s exceeds safe size limit: %s > %s",
                i + 1,
                len(chunks),
                estimated_message_size,
                CHUNK_SIZE,
            )
            # Split this chunk into smaller ones
            smaller_chunks = split_chunk(chunk, CHUNK_SIZE // 2)
            if len(smaller_chunks) > 1:
                # Replace current chunk with first smaller chunk
                chunks[i] = smaller_chunks[0]
                # Insert remaining smaller chunks after current position
                for j, small_chunk in enumerate(smaller_chunks[1:], 1):
                    chunks.insert(i + j, small_chunk)
                log.info(
                    "Split oversized chunk %s into %s smaller chunks",
                    i + 1,
                    len(smaller_chunks),
                )
                # Don't increment i, we'll check the new chunk at position i next
            else:
                # If we couldn't split further, just move on
                i += 1
        else:
            # Chunk is OK, move to next
            i += 1

    # Update total chunks count after all splitting
    total_chunks = len(chunks)

    # Second pass: log final chunk sizes
    log.info("After splitting, output has %s chunks:", total_chunks)
    for i, chunk in enumerate(chunks):
        log.info("Chunk %s/%s size: %s bytes", i + 1, total_chunks, len(chunk))

    log.info("Largest chunk size before splitting: %s bytes", max_chunk_size)

    # Establish a single NATS connection for all chunks
    try:
        nats_url = os.getenv("NATS_URL", "nats://dev-nats:4222")
        nc = await nats.connect(
            nats_url, connect_timeout=5, reconnect_time_wait=1
        )
        js = nc.jetstream()

        # Send each chunk with appropriate metadata
        success_count = 0
        max_retries = 3  # Maximum number of retries for each chunk

        for i, chunk in enumerate(chunks):
            chunk_num = i + 1
            is_final = chunk_num == total_chunks

            log.info(
                "Sending chunk %s/%s, size: %s bytes", chunk_num, total_chunks, len(chunk)
            )

            # Add a delay between chunks to prevent overwhelming the NATS server
            # Use progressive backoff for more reliable delivery
            if i > 0:
                await asyncio.sleep(0.2)  # Increased from 0.1 to 0.2 seconds

            # Retry logic for sending chunks
            for retry in range(max_retries):
                try:
                    # Get task information from environment variables
                    task_id = os.getenv("TASK_ID", "unknown")
                    workflow_id = os.getenv("WORKFLOW_ID", "unknown")
                    step_name = os.getenv("STEP_NAME", "unknown")
                    step_num = os.getenv("STEP_NUM", "0")
                    output_subject = os.getenv("OUTPUT_QUEUE_SUBJECT")
                    if not output_subject:
                        log.error("OUTPUT_QUEUE_SUBJECT environment variable not set")
                        continue

                    # Create result message
                    result = {
                        "task_id": task_id,
                        "workflow_id": workflow_id,
                        "step_name": step_name,
                        "step_num": int(step_num),
                        "success": success,
                        "output": chunk,
                        "execution_time": time.time(),
                        "is_final": is_final,
                        "chunk_num": chunk_num,
                        "total_chunks": total_chunks,
                        "timestamp": time.time(),
                    }

                    # Encode message and check size before sending
                    encoded_message = json.dumps(result).encode()
                    message_size = len(encoded_message)

                    if message_size > 1000000:  # 1MB - NATS typical limit
                        log.error(
                            "Message is too large (%s bytes) - skipping this chunk",
                            message_size,
                        )
                        # Try to reduce the chunk size and resend
                        if len(chunk) > 1000:
                            # Create two sub-chunks
                            half_size = len(chunk) // 2
                            sub_chunk1 = chunk[:half_size]
                            sub_chunk2 = chunk[half_size:]

                            # Insert the new sub-chunk and update current chunk
                            chunks.insert(i + 1, sub_chunk2)
                            chunks[i] = sub_chunk1
                            total_chunks = len(chunks)

                            log.info(
                                "Split chunk %s into two parts: %s and %s bytes",
                                chunk_num,
                                len(sub_chunk1),
                                len(sub_chunk2),
                            )
                            break  # Break out of retry loop, will try again with smaller chunk
                        else:
                            # If the chunk is already very small, we have a serious problem
                            log.critical(
                                "Cannot reduce chunk size further (%s bytes)",
                                len(chunk),
                            )
                            raise ValueError(  # noqa: TRY301
                                "Chunk size is too small to split but still exceeds "
                                "NATS limit"
                            )

                    # Publish directly with the shared connection
                    log.info(
                        "Sending chunk %s/%s to %s", chunk_num, total_chunks, output_subject
                    )
                    ack = await js.publish(output_subject, encoded_message)
                    log.info(
                        "Attempt %s: Sent chunk %s/%s successfully with sequence %s",
                        retry + 1,
                        chunk_num,
                        total_chunks,
                        ack.seq,
                    )
                    success_count += 1
                    break  # Break the retry loop on success

                except Exception as e:  # noqa: BLE001
                    log.exception(
                        "Attempt %s: Error sending chunk %s/%s: %s",
                        retry + 1,
                        chunk_num,
                        total_chunks,
                        e,
                    )
                    if retry < max_retries - 1:
                        # Exponential backoff between retries
                        wait_time = 0.5 * (2**retry)
                        log.info("Retrying in %s seconds...", wait_time)
                        await asyncio.sleep(wait_time)
                    else:
                        log.error(
                            "Failed to send chunk %s/%s after %s attempts",
                            chunk_num,
                            total_chunks,
                            max_retries,
                        )

        # Close the connection once all chunks are sent
        await nc.close()

        log.info("Sent %s/%s chunks successfully", success_count, total_chunks)
        if success_count < total_chunks:
            log.warning("Failed to send %s chunks", total_chunks - success_count)

    except Exception as e:  # noqa: BLE001
        log.exception("Fatal error in chunk sending process: %s", e)
        # Try to report error via simple publish if possible
        try:
            error_msg = f"Error sending chunked output: {e!s}"
            await publish_result(error_msg, False)
        except Exception:  # noqa: BLE001
            log.error("Unable to report error to NATS")


def run_command(command):
    try:
        # Run the command and directly pass through stdout
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr
            text=True,
            shell=True,
        )

        # First, collect all output lines
        all_lines = []
        stderr_lines = []

        # Read stdout
        if process.stdout:
            for line in process.stdout:
                line = line.rstrip("\n")
                if line:  # Skip empty lines
                    all_lines.append(line)
                    # Don't print stdout lines directly - they should go to NATS only
                    # print(line)  # Commented out to prevent stdout pollution

        # Read stderr
        # if process.stderr:
        #     for line in process.stderr:
        #         line = line.rstrip("\n")
        #         if line:
        #             stderr_lines.append(line)
        #             log.info("stderr: %s", line)

        # Wait for the process to complete
        process.wait()
        return_code = process.returncode
        success = return_code == 0

        # For parsing JSON properly, we need to ensure that the output is a valid JSON
        # If the output has JSON content, use only that without the stderr messages
        output = ""
        if all_lines:
            # Join all stdout lines, which is probably JSON content
            output = "\n".join(all_lines)

        # Log stderr separately, but don't include it in the actual output if we have stdout content
        if stderr_lines:
            stderr_output = "\n".join(f"stderr: {line}" for line in stderr_lines)
            log.info(
                "Stderr content: %s%s",
                stderr_output[:200],
                "..." if len(stderr_output) > 200 else "",
            )

        # CRITICAL: Only send stdout content to NATS, never mix in stderr
        # This prevents output pollution that breaks parsing
        if not output:
            # If no stdout, create a clear error message instead of mixing stderr
            output = ""
            log.warning(
                "No stdout content, using fallback message instead of mixing stderr"
            )

        # Publish result to NATS if environment variables are set
        if os.getenv("NATS_URL") and os.getenv("TASK_ID"):
            # Log the output being sent
            log.info("Command return code: %s", return_code)
            log.info("Command success: %s", success)
            log.info("Output length: %s", len(output))
            log.info("Output preview (first 200 chars): %r", output[:200])
            log.info("Stderr lines count: %s", len(stderr_lines))
            log.info(
                "Sending output (success=%s): %s%s",
                success,
                output,
                "..." if len(output) > 200 else "",
            )

            # Send output with chunking if needed
            asyncio.run(send_chunked_output(output, success))

            # Log after publishing
            log.info("Published result for task %s", os.getenv("TASK_ID"))

        # Exit with the same code as the command
        sys.exit(return_code)

    except Exception as e:  # noqa: BLE001
        error_msg = f"Error executing command: {e!s}"
        log.exception("run_command: %s", e)
        # Try to publish the error if possible
        if os.getenv("NATS_URL") and os.getenv("TASK_ID"):
            asyncio.run(publish_result(error_msg, False))
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        log.error("No command provided")
        sys.exit(1)

    # Reconstruct the command from arguments

    command = " ".join(sys.argv[1:])
    log.info("Executing command: %s", command)
    run_command(command)
