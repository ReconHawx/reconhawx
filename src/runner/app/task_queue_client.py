#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Any, Optional, Callable
import time

from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy
from nats.aio.client import Client as NATS


logger = logging.getLogger(__name__)

# Environment variables
NATS_URL = os.getenv("NATS_URL", "nats://dev-nats:4222")
TASK_QUEUE_STREAM = os.getenv("TASK_QUEUE_STREAM", "TASKS")
TASK_QUEUE_SUBJECT = os.getenv("TASK_QUEUE_SUBJECT", "tasks.pending")
OUTPUT_QUEUE_STREAM = os.getenv("OUTPUT_QUEUE_STREAM", "OUTPUTS")
OUTPUT_QUEUE_SUBJECT = os.getenv("OUTPUT_QUEUE_SUBJECT", "tasks.output")
TASK_DEFAULT_TIMEOUT = int(os.getenv("TASK_DEFAULT_TIMEOUT", "7200"))  # 2 hours

class TaskQueueClient:
    """A client for interacting with the task queuing system"""
    
    def __init__(self):
        self.nc = None
        self.js = None
        self.output_handlers: Dict[str, Callable] = {}
        self.running = False
        self.output_listener_task = None
        self.subscription = None
        self.task_outputs = {}
        self.task_chunks = {}  # Store chunks for each task
        self.consumer_name = f"runner-{uuid.uuid4().hex[:8]}"
        # Use EXECUTION_ID for routing (always valid) and WORKFLOW_ID for workflow definition reference (can be empty for custom workflows)
        self.execution_id = os.getenv('EXECUTION_ID')
        self.workflow_id = os.getenv('WORKFLOW_ID')
        self.task_executor = None  # Will be set by TaskExecutor
        
        if self.execution_id:
            self.workflow_output_subject = f"{OUTPUT_QUEUE_SUBJECT}.{self.execution_id}"
        else:
            logger.error("EXECUTION_ID environment variable is not set")
            raise ValueError("EXECUTION_ID environment variable is required")
        
    async def setup(self):
        """Set up the connection to NATS"""
        # List of NATS URLs to try
        
        try:
            # Connect to NATS
            self.nc = NATS()
            await self.nc.connect(NATS_URL, connect_timeout=5, reconnect_time_wait=1)
            logger.debug(f"Connected to NATS at {NATS_URL}")
            
            # Initialize JetStream
            self.js = self.nc.jetstream()
                        
            # Set up the workflow-specific consumer and subscription if workflow_id is set
            workflow_subscription = None
            workflow_consumer_name = f"{self.consumer_name}-workflow"
            workflow_consumer_config = ConsumerConfig(
                name=workflow_consumer_name,
                deliver_policy=DeliverPolicy.ALL,
                ack_policy=AckPolicy.EXPLICIT,
                filter_subject=self.workflow_output_subject,
                durable_name=workflow_consumer_name
            )
                
            try:
                # Try to delete existing consumer if it exists
                try:
                    await self.js.delete_consumer(OUTPUT_QUEUE_STREAM, workflow_consumer_name)
                except Exception:
                    pass
                # Create new consumer
                await self.js.add_consumer(OUTPUT_QUEUE_STREAM, workflow_consumer_config)
                logger.debug(f"Created workflow-specific consumer: {workflow_consumer_name}")
            except Exception as e:
                logger.warning(f"Workflow-specific consumer error: {e}")
            
            # Create pull subscription for workflow-specific subject
            workflow_subscription = await self.js.pull_subscribe(
                self.workflow_output_subject,
                workflow_consumer_name
            )
            logger.debug(f"Subscribed to workflow-specific subject: {self.workflow_output_subject}")
            
            # Store subscriptions
            # self.subscription = general_subscription
            self.workflow_subscription = workflow_subscription
            
            # Start the output listener
            self.running = True
            self.output_listener_task = asyncio.create_task(self.listen_for_outputs())
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NATS at {NATS_URL}: {e}")
            return False
    
    async def shutdown(self):
        """Shut down the client and clean up all resources"""
        try:
            logger.debug("Starting task queue client shutdown...")
            self.running = False
            
            # Cancel output listener task if it exists
            if self.output_listener_task:
                logger.debug("Cancelling output listener task...")
                self.output_listener_task.cancel()
                try:
                    await asyncio.wait_for(self.output_listener_task, timeout=2)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                self.output_listener_task = None
                logger.info("Output listener task cancelled")
            
            # Process any tasks with partial chunks before shutting down
            if self.task_chunks:
                logger.warning(f"Attempting to process {len(self.task_chunks)} tasks with partial chunks during shutdown")
                for task_id, chunks in list(self.task_chunks.items()):
                    # If we have any chunks at all, use what we've got
                    if chunks:
                        chunk_count = len(chunks)
                        total_expected = 0
                        for chunk_num, chunk_data in chunks.items():
                            total = chunk_data.get("total_chunks", 0)
                            if total > total_expected:
                                total_expected = total
                        
                        logger.warning(f"Task {task_id} has {chunk_count}/{total_expected} chunks during shutdown - using partial data")
                        
                        # Reassemble what we have
                        combined_output = ""
                        for i in range(1, total_expected + 1):
                            if i in chunks:
                                chunk_data = chunks[i]
                                combined_output += chunk_data.get("output", "")
                        
                        # Create a payload with the partial output
                        last_chunk = chunks[max(chunks.keys())]
                        partial_payload = last_chunk.copy()
                        partial_payload["output"] = combined_output
                        partial_payload["is_chunked"] = True
                        partial_payload["chunks_received"] = chunk_count
                        partial_payload["chunks_expected"] = total_expected
                        partial_payload["is_partial"] = True
                        
                        # Store the partial output
                        self.task_outputs[task_id] = partial_payload
                        
                        # Call handler with partial output if registered
                        if task_id in self.output_handlers:
                            try:
                                handler = self.output_handlers[task_id]
                                handler(partial_payload)
                                del self.output_handlers[task_id]
                                logger.info(f"Called handler with partial output for task {task_id}")
                            except Exception as e:
                                logger.error(f"Error calling handler with partial output for task {task_id}: {e}")
            
            # Unsubscribe from workflow-specific subscription if it exists
            if hasattr(self, 'workflow_subscription') and self.workflow_subscription:
                try:
                    logger.debug("Unsubscribing from workflow subject...")
                    await self.workflow_subscription.unsubscribe()
                    logger.debug("Unsubscribed from workflow subject")
                except Exception as e:
                    logger.error(f"Error unsubscribing from workflow subject: {e}")
                self.workflow_subscription = None
            
            # Clear any pending tasks 
            if self.task_executor:
                pending_count = len(self.task_executor.pending_tasks)
                if pending_count > 0:
                    logger.warning(f"Force-terminating {pending_count} pending tasks during shutdown")
                    # Use a copy since we'll be modifying during iteration
                    pending_task_ids = list(self.task_executor.pending_tasks.keys())
                    for task_id in pending_task_ids:
                        self.task_executor.mark_task_completed(task_id, success=False, error="Forced termination during shutdown")
            
            # Drain and close NATS connection
            if self.nc:
                try:
                    logger.debug("Draining NATS connection...")
                    # Drain connection with a timeout
                    await asyncio.wait_for(self.nc.drain(), timeout=2)
                    logger.debug("NATS connection drained")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.error(f"Error draining NATS connection: {e}")
                
                try:
                    logger.debug("Closing NATS connection...")
                    # Close connection with a timeout
                    await asyncio.wait_for(self.nc.close(), timeout=2)
                    logger.debug("NATS connection closed")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.error(f"Error closing NATS connection: {e}")
                
                self.nc = None
                self.js = None
            
            # Clear any stored state
            # Don't need to clear task_executor.pending_tasks as it's cleared by mark_task_completed above
            self.output_handlers.clear()
            self.task_outputs.clear()
            self.task_chunks.clear()
            
            logger.debug("Task queue client shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during task queue client shutdown: {e}")
            raise
    
    async def listen_for_outputs(self):
        """Listen for task outputs on the output queue"""
        logger.debug("Starting to listen for task outputs")
        
        last_activity = time.time()
        last_chunk_check = time.time()
        # Increase batch size for better throughput with chunked messages
        batch_size = 500  # Increase to handle more messages at once
        
        while self.running:
            try:
                # Check if we should exit early
                if not self.running:
                    logger.debug("Exiting output listener - running flag is False")
                    break
                
                current_time = time.time()
                received_messages = False
                
                try:
                    # Use a longer timeout and larger batch size to ensure we don't miss messages
                    if self.workflow_subscription is None:
                        continue
                    workflow_messages = await self.workflow_subscription.fetch(batch=batch_size, timeout=0.5)
                    
                    if workflow_messages:
                        received_messages = True
                        last_activity = current_time
                                        
                    for msg in workflow_messages:
                        try:
                            # Check running flag before processing each message
                            if not self.running:
                                await msg.ack()
                                continue
                                
                            # Process the message
                            await self.process_output(msg)
                            # Acknowledge the message
                            await msg.ack()
                        except Exception as e:
                            logger.error(f"Error processing workflow output message: {e}")
                            # Still ack to avoid redelivery of problematic messages
                            try:
                                await msg.ack()
                            except Exception as e2:
                                logger.error(f"Failed to ack message after processing error: {e2}")
                
                except TimeoutError:
                    # No messages, just continue
                    pass
                except Exception as e:
                    logger.error(f"Error fetching workflow messages: {e}")
                
                # Log periodic status updates for tasks with chunks
                if self.task_chunks and (current_time - last_activity > 5):  # Every 5 seconds
                    for task_id, task_info in self.task_chunks.items():
                        # Skip tasks that are already marked complete
                        if task_info.get("is_complete", False):
                            continue
                            
                        # Get details about this chunked task
                        processed_chunks = task_info.get("processed_chunks", set())
                        total_chunks = task_info.get("total_chunks", 0)
                        
                        if total_chunks > 0:
                            processed_count = len(processed_chunks)
                            logger.info(f"Task {task_id} chunk status: {processed_count}/{total_chunks} chunks processed")
                    last_activity = current_time
                
                # Check for stalled chunk processing every 5 seconds (was 10)
                if current_time - last_chunk_check > 5:
                    await self.check_stalled_chunks()
                    last_chunk_check = current_time
                
                # Small delay if no messages were received
                if not received_messages:
                    # Use asyncio.sleep with a small timeout to ensure we can exit quickly
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                # Handle task cancellation explicitly
                logger.debug("Output listener task was cancelled")
                break
            except Exception as e:
                logger.error(f"Error in output listener: {e}")
                # Don't immediately exit on errors, but add a small delay
                await asyncio.sleep(0.5)
        
        logger.info("Output listener stopped")
    
    async def process_output(self, msg):
        """Process an output message from the queue"""
        try:
            # Parse the output
            payload = json.loads(msg.data.decode())
            task_id = payload.get("task_id")
            
            if not task_id:
                logger.error(f"Task ID missing from output message: {payload}")
                return
            
            # Log output details for debugging
            success = payload.get("success", False)
            output = payload.get("output", "")
            output_length = len(output)
            
            # Check if this is a chunked message
            is_final = payload.get("is_final", True)
            chunk_num = payload.get("chunk_num", 1)
            total_chunks = payload.get("total_chunks", 1)
            
            # Handle chunked messages
            if total_chunks > 1:
                # Process each chunk immediately                
                # Initialize task chunks tracking if not exists
                if task_id not in self.task_chunks:
                    self.task_chunks[task_id] = {
                        "processed_chunks": set(),
                        "chunks": {},  # Store each chunk by its chunk_num
                        "total_chunks": total_chunks,
                        "last_chunk_time": time.time(),
                        "success": success,
                        "is_complete": False
                    }
                
                # Update the timestamp for the most recent chunk
                self.task_chunks[task_id]["last_chunk_time"] = time.time()
                
                # Store this chunk
                if output:
                    # Mark this chunk as processed
                    self.task_chunks[task_id]["processed_chunks"].add(chunk_num)
                    # Store the chunk with its metadata
                    self.task_chunks[task_id]["chunks"][chunk_num] = {
                        "output": output,
                        "chunk_num": chunk_num,
                        "total_chunks": total_chunks,
                        "is_final": is_final,
                        "timestamp": payload.get("timestamp", time.time())
                    }
                    
                    # Log progress
                    processed_count = len(self.task_chunks[task_id]["processed_chunks"])
                    self.task_chunks[task_id]["total_chunks"]
                    
                    # Check if we have all chunks or if this is the final chunk
                    if processed_count == total_chunks or is_final:
                        # Assemble the complete output in the correct order
                        combined_output = ""
                        for i in range(1, total_chunks + 1):
                            if i in self.task_chunks[task_id]["chunks"]:
                                chunk_data = self.task_chunks[task_id]["chunks"][i]
                                combined_output += chunk_data["output"]
                            else:
                                logger.warning(f"Missing chunk {i} while assembling output for task {task_id}")
                        logger.info(f"Processed all {processed_count} chunks for task {task_id}")
                        # Create final payload
                        final_payload = payload.copy()
                        final_payload["output"] = combined_output
                        final_payload["is_chunked"] = True
                        final_payload["chunks_received"] = processed_count
                        final_payload["chunks_expected"] = total_chunks
                        final_payload["is_final"] = True
                        final_payload["is_partial"] = (processed_count < total_chunks)
                        
                        # Store the final assembled output
                        self.task_outputs[task_id] = final_payload
                        self.task_chunks[task_id]["is_complete"] = True
                        
                        # Call the output handler with the assembled output
                        if task_id in self.output_handlers:
                            try:
                                handler = self.output_handlers[task_id]
                                handler(final_payload)
                                #logger.info(f"Successfully called output handler for task {task_id} with complete output ({processed_count}/{total_chunks} chunks)")
                                del self.output_handlers[task_id]
                            except Exception as e:
                                logger.error(f"Error calling output handler for task {task_id}: {e}")
                        
                        # Clean up after processing all chunks
                        if task_id in self.task_chunks:
                            del self.task_chunks[task_id]
            
            else:
                # Not a chunked message, process as before
                # Only consider task complete if it has both success=True and valid output
                if success and output_length > 0:
                    # Store the output immediately
                    self.task_outputs[task_id] = payload
                    
                    # Call the output handler if registered
                    if task_id in self.output_handlers:
                        try:
                            handler = self.output_handlers[task_id]
                            handler(payload)
                            #logger.info(f"Successfully called output handler for task {task_id}")
                            del self.output_handlers[task_id]
                        except Exception as e:
                            logger.error(f"Error calling output handler for task {task_id}: {e}")
                    else:
                        logger.debug(f"No output handler registered for task {task_id}")
                else:
                    logger.info(f"Task {task_id} had no valid output (success={success}, output_length={output_length})")
                    if task_id in self.output_handlers:
                        # Call handler with failure
                        handler = self.output_handlers[task_id]
                        failure_payload = {
                            "task_id": task_id,
                            "success": True,
                            "output": "Task completed but produced no valid output"
                        }
                        try:
                            handler(failure_payload)
                            del self.output_handlers[task_id]
                        except Exception as e:
                            logger.error(f"Error calling failure handler for task {task_id}: {e}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse output message data: {msg.data}, error: {e}")
        except Exception as e:
            logger.exception(f"Error processing output: {e}")
    
    async def get_task_output(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the output for a specific task if it's available without waiting
        
        This is used by the asynchronous output collector to check if an output
        is available without blocking.
        """
        try:
            # Check if we already have the output
            if task_id in self.task_outputs:
                logger.info(f"Found existing output for task {task_id}")
                output = self.task_outputs[task_id]
                # Remove the output from storage after retrieving it
                del self.task_outputs[task_id]
                logger.info(f"Returning output for task {task_id}")
                return output
            
            # Check if task has chunks but the final chunk hasn't been received yet
            if task_id in self.task_chunks and not self.task_chunks[task_id].get("is_complete", False):
                # Check if we have enough chunks to consider the task complete
                task_info = self.task_chunks[task_id]
                processed_chunks = task_info.get("processed_chunks", set())
                total_chunks = task_info.get("total_chunks", 0)
                processed_count = len(processed_chunks)
                
                # If we have all expected chunks, assemble and return output
                if processed_count == total_chunks:
                    logger.info(f"All {processed_count}/{total_chunks} chunks received for task {task_id}")
                    
                    # Assemble the complete output
                    combined_output = ""
                    for i in range(1, total_chunks + 1):
                        if i in task_info["chunks"]:
                            chunk_data = task_info["chunks"][i]
                            combined_output += chunk_data["output"]
                        else:
                            logger.warning(f"Missing chunk {i} while assembling output for task {task_id}")
                    
                    # Create final payload with the complete output
                    last_chunk_num = max(task_info["chunks"].keys())
                    last_chunk = task_info["chunks"][last_chunk_num]
                    
                    final_payload = {
                        "task_id": task_id,
                        "workflow_id": last_chunk.get("workflow_id", "unknown"),
                        "step_name": last_chunk.get("step_name", "unknown"),
                        "step_num": last_chunk.get("step_num", 0),
                        "success": task_info.get("success", True),
                        "output": combined_output,
                        "is_chunked": True,
                        "chunks_received": processed_count,
                        "chunks_expected": total_chunks,
                        "is_final": True,
                        "is_partial": False
                    }
                    
                    # Mark as complete to prevent further processing
                    task_info["is_complete"] = True
                    
                    # Clean up this task
                    del self.task_chunks[task_id]
                    
                    return final_payload
                
                # Task has chunks but hasn't completed yet
                return None
            
            # Output isn't available yet
            return None
        except Exception as e:
            logger.error(f"Error getting task output: {str(e)}")
            return None

    async def check_stalled_chunks(self):
        """Check for tasks with stalled chunk processing"""
        if not self.task_chunks:
            return
        
        current_time = time.time()
        for task_id, task_info in list(self.task_chunks.items()):
            # Skip tasks that are already marked complete
            if task_info.get("is_complete", False):
                continue
            
            # Get details about this chunked task
            processed_chunks = task_info.get("processed_chunks", set())
            total_chunks = task_info.get("total_chunks", 0)
            last_chunk_time = task_info.get("last_chunk_time", 0)
            time_since_last_chunk = current_time - last_chunk_time
            
            # Log stalled tasks that haven't received chunks in a while
            if time_since_last_chunk > 30:  # No new chunks in 30 seconds
                processed_count = len(processed_chunks)
                missing_count = total_chunks - processed_count
                
                logger.warning(f"Task {task_id} appears stalled with {processed_count}/{total_chunks} "
                              f"chunks processed. Missing {missing_count} chunks. "
                              f"Last chunk received {time_since_last_chunk:.1f} seconds ago.")
                
                # If we have more than 90% of chunks and it's been over 60 seconds,
                # consider the task complete with the chunks we have
                if processed_count > total_chunks * 0.9 and time_since_last_chunk > 60:
                    logger.warning(f"Task {task_id} has {processed_count}/{total_chunks} chunks (>{total_chunks*0.9:.0f}) "
                                  f"and no new chunks in over 60 seconds. Marking as complete.")
                    
                    # Assemble the output from the chunks we have
                    combined_output = ""
                    for i in range(1, total_chunks + 1):
                        if i in task_info["chunks"]:
                            chunk_data = task_info["chunks"][i]
                            combined_output += chunk_data["output"]
                    
                    # Create a final payload with the partial output
                    last_chunk_num = max(task_info["chunks"].keys())
                    last_chunk = task_info["chunks"][last_chunk_num]
                    
                    # Create payload based on the most recent chunk
                    partial_payload = {
                        "task_id": task_id,
                        "workflow_id": last_chunk.get("workflow_id", "unknown"),
                        "step_name": last_chunk.get("step_name", "unknown"),
                        "step_num": last_chunk.get("step_num", 0),
                        "success": task_info.get("success", True),
                        "output": combined_output,
                        "is_chunked": True,
                        "chunks_received": processed_count,
                        "chunks_expected": total_chunks,
                        "is_final": True,
                        "is_partial": True
                    }
                    
                    # Store the partial output
                    self.task_outputs[task_id] = partial_payload
                    
                    # Mark as complete to prevent further processing
                    task_info["is_complete"] = True
                    
                    # Call handler with partial output if registered
                    if task_id in self.output_handlers:
                        try:
                            handler = self.output_handlers[task_id]
                            handler(partial_payload)
                            del self.output_handlers[task_id]
                            logger.info(f"Called handler with partial output ({processed_count}/{total_chunks} chunks) for stalled task {task_id}")
                        except Exception as e:
                            logger.error(f"Error calling handler with partial output for task {task_id}: {e}")
                    
                    # Clean up this task
                    del self.task_chunks[task_id]
