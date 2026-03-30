#!/usr/bin/env python3
"""
NATS JetStream statistics service for admin dashboard.

Fetches stream and consumer metrics from the EVENTS stream using short-lived
connections to avoid coupling with the event publisher.
"""

import base64
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from nats.aio.client import Client as NATS
from nats.js.errors import NotFoundError as NatsNotFoundError

logger = logging.getLogger(__name__)

NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "EVENTS")
CONSUMER_NAME = "notifier"

_DEFAULT_MAX_SCAN = 5000
_HARD_MAX_SCAN = 50000


def _payload_search_text(payload: Any) -> str:
    if isinstance(payload, dict):
        return json.dumps(payload, sort_keys=True, default=str)
    return str(payload)


def pending_message_matches_search(subject: str, payload: Any, needle_lower: str) -> bool:
    haystack = f"{subject}\n{_payload_search_text(payload)}".lower()
    return needle_lower in haystack


def _row_from_msg_get_body(data: Dict[str, Any], default_seq: int) -> Optional[Dict[str, Any]]:
    if "error" in data:
        logger.debug("MSG_GET error: %s", data["error"])
        return None
    msg_obj = data.get("message", {})
    raw_data = msg_obj.get("data", "")
    seq = msg_obj.get("seq", default_seq)
    try:
        payload = base64.b64decode(raw_data).decode("utf-8")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            pass
    except Exception:
        payload = raw_data
    return {
        "seq": seq,
        "subject": msg_obj.get("subject", ""),
        "time": msg_obj.get("time", ""),
        "payload": payload,
    }


async def _js_api_request(nc: NATS, subject: str, payload: bytes, timeout: float) -> Dict[str, Any]:
    resp = await nc.request(subject, payload, timeout=timeout)
    if not resp.data:
        return {}
    return json.loads(resp.data.decode("utf-8"))


async def _stream_msg_get(nc: NATS, seq: int) -> Optional[Dict[str, Any]]:
    subject = f"$JS.API.STREAM.MSG.GET.{EVENTS_STREAM}"
    try:
        req = json.dumps({"seq": seq}).encode("utf-8")
        data = await _js_api_request(nc, subject, req, timeout=3.0)
        return _row_from_msg_get_body(data, seq)
    except Exception as e:
        logger.debug("Failed to get msg seq=%s: %s", seq, e)
        return None


def _api_error_str(data: Dict[str, Any]) -> Optional[str]:
    err = data.get("error")
    if err is None:
        return None
    if isinstance(err, dict):
        return err.get("description") or err.get("err_code") or json.dumps(err)
    return str(err)


async def get_event_stats() -> Dict[str, Any]:
    """
    Fetch NATS JetStream statistics for the EVENTS stream and notifier consumer.

    Returns a dict with stream, consumer stats, and connection status.
    Uses a short-lived connection (connect -> fetch -> close).
    """
    nc: Optional[NATS] = None
    result: Dict[str, Any] = {
        "connected": False,
        "stream": None,
        "consumer": None,
        "error": None,
    }

    try:
        t0 = time.monotonic()
        nc = NATS()
        await nc.connect(
            NATS_URL,
            connect_timeout=5,
            reconnect_time_wait=1,
            max_reconnect_attempts=1,
        )
        t_connect = time.monotonic() - t0
        logger.debug(f"NATS connect took {t_connect:.2f}s")
        js = nc.jetstream()

        # Stream info
        try:
            t1 = time.monotonic()
            stream_info = await js.stream_info(EVENTS_STREAM)
            logger.debug(f"stream_info took {time.monotonic() - t1:.2f}s")
            state = stream_info.state
            result["stream"] = {
                "name": EVENTS_STREAM,
                "messages": getattr(state, "messages", 0) or 0,
                "bytes": getattr(state, "bytes", 0) or 0,
                "first_seq": getattr(state, "first_seq", 0) or 0,
                "last_seq": getattr(state, "last_seq", 0) or 0,
                "consumer_count": getattr(state, "consumer_count", 0) or 0,
                "num_subjects": getattr(state, "num_subjects", 0) or 0,
            }
        except Exception as e:
            logger.warning(f"Failed to get stream info for {EVENTS_STREAM}: {e}")
            result["stream"] = {"name": EVENTS_STREAM, "error": str(e)}

        # Consumer info (notifier consumer is created by event-handler when it connects;
        # it may not exist if event-handler is not running)
        try:
            t2 = time.monotonic()
            consumer_info = await js.consumer_info(EVENTS_STREAM, CONSUMER_NAME)
            logger.debug(f"consumer_info took {time.monotonic() - t2:.2f}s")
            delivered = getattr(consumer_info, "delivered", None)
            stream_seq = getattr(delivered, "stream_seq", 0) if delivered else 0

            # nats-py may use ack_pending or num_ack_pending
            ack_pending = getattr(consumer_info, "ack_pending", None) or getattr(
                consumer_info, "num_ack_pending", 0
            ) or 0

            result["consumer"] = {
                "name": CONSUMER_NAME,
                "num_pending": getattr(consumer_info, "num_pending", 0) or 0,
                "delivered_stream_seq": stream_seq,
                "ack_pending": ack_pending,
            }
        except NatsNotFoundError:
            # Expected when event-handler has not connected yet (consumer created on first connect)
            logger.debug(f"Consumer '{CONSUMER_NAME}' not found (event-handler may not be running)")
            result["consumer"] = {"name": CONSUMER_NAME, "error": "consumer not found (event-handler may not be running)"}
        except Exception as e:
            logger.warning(f"Failed to get consumer info for {CONSUMER_NAME}: {e}")
            result["consumer"] = {"name": CONSUMER_NAME, "error": str(e)}

        result["connected"] = True
        total_ms = (time.monotonic() - t0) * 1000
        if total_ms > 2000:
            logger.warning(f"NATS stats slow: total={total_ms:.0f}ms (connect={t_connect*1000:.0f}ms)")
        else:
            logger.debug(f"NATS stats took {total_ms:.0f}ms")

    except Exception as e:
        logger.error(f"NATS stats connection failed: {e}")
        result["error"] = str(e)

    finally:
        if nc and not nc.is_closed:
            try:
                await nc.close()
            except Exception as e:
                logger.debug(f"Error closing NATS connection: {e}")

    return result


async def _pending_range_bounds(js) -> Tuple[int, int, int, int]:
    """Returns first_seq, last_seq, start_seq (pending start), end_seq."""
    stream_info = await js.stream_info(EVENTS_STREAM)
    state = stream_info.state
    first_seq = getattr(state, "first_seq", 0) or 0
    last_seq = getattr(state, "last_seq", 0) or 0

    delivered_seq = 0
    try:
        consumer_info = await js.consumer_info(EVENTS_STREAM, CONSUMER_NAME)
        delivered = getattr(consumer_info, "delivered", None)
        delivered_seq = getattr(delivered, "stream_seq", 0) if delivered else 0
    except Exception:
        pass

    start_seq = max(first_seq, delivered_seq + 1)
    end_seq = last_seq
    return first_seq, last_seq, start_seq, end_seq


async def get_pending_messages(
    limit: int = 50,
    search: Optional[str] = None,
    max_scan: int = _DEFAULT_MAX_SCAN,
) -> Dict[str, Any]:
    """
    Fetch pending messages from the EVENTS stream without consuming or acking them.

    Uses the JetStream STREAM.MSG.GET API to read messages by sequence directly
    from the stream - this does not affect the notifier consumer.

    Returns messages in the pending range (delivered_seq+1 to last_seq).

    If ``search`` is set, scans sequences until ``limit`` matches, end of range,
    or ``max_scan`` messages examined.
    """
    nc: Optional[NATS] = None
    result: Dict[str, Any] = {
        "connected": False,
        "messages": [],
        "error": None,
    }

    needle: Optional[str] = None
    if search is not None:
        stripped = search.strip()
        if stripped:
            needle = stripped.lower()

    try:
        nc = NATS()
        await nc.connect(
            NATS_URL,
            connect_timeout=5,
            reconnect_time_wait=1,
            max_reconnect_attempts=1,
        )
        js = nc.jetstream()
        _, _, start_seq, end_seq = await _pending_range_bounds(js)

        if start_seq > end_seq:
            result["connected"] = True
            result["pending_range"] = {
                "start": start_seq,
                "end": end_seq,
                "total": 0,
                "shown": 0,
            }
            return result

        total_pending = end_seq - start_seq + 1
        result["pending_range"] = {
            "start": start_seq,
            "end": end_seq,
            "total": total_pending,
            "shown": 0,
        }

        messages: List[Dict[str, Any]] = []

        if not needle:
            fetch_count = min(limit, total_pending)
            for i in range(fetch_count):
                seq = start_seq + i
                row = await _stream_msg_get(nc, seq)
                if row:
                    messages.append(row)
            result["pending_range"]["shown"] = len(messages)
        else:
            cap = max(1, min(max_scan, _HARD_MAX_SCAN))
            examined = 0
            seq = start_seq
            truncated = False
            while seq <= end_seq and len(messages) < limit and examined < cap:
                examined += 1
                row = await _stream_msg_get(nc, seq)
                if row and pending_message_matches_search(
                    row["subject"], row["payload"], needle
                ):
                    messages.append(row)
                seq += 1
            if examined >= cap and seq <= end_seq:
                truncated = True
            result["messages"] = messages
            result["pending_range"]["shown"] = len(messages)
            result["scan"] = {"examined": examined, "truncated": truncated}
            result["connected"] = True
            return result

        result["connected"] = True
        result["messages"] = messages

    except Exception as e:
        logger.error(f"NATS pending messages failed: {e}")
        result["error"] = str(e)

    finally:
        if nc and not nc.is_closed:
            try:
                await nc.close()
            except Exception as e:
                logger.debug(f"Error closing NATS connection: {e}")

    return result


async def purge_events_stream() -> Dict[str, Any]:
    """Purge all messages from the EVENTS JetStream stream."""
    nc: Optional[NATS] = None
    try:
        nc = NATS()
        await nc.connect(
            NATS_URL,
            connect_timeout=5,
            reconnect_time_wait=1,
            max_reconnect_attempts=1,
        )
        subject = f"$JS.API.STREAM.PURGE.{EVENTS_STREAM}"
        data = await _js_api_request(nc, subject, b"{}", timeout=30.0)
        err = _api_error_str(data)
        if err:
            raise ValueError(err)
        return {"success": True, "purge": data}
    finally:
        if nc and not nc.is_closed:
            try:
                await nc.close()
            except Exception as e:
                logger.debug(f"Error closing NATS connection: {e}")


async def delete_event_messages_by_seq(sequences: List[int]) -> Dict[str, Any]:
    """
    Delete messages from the EVENTS stream by stream sequence number.
    """
    deleted: List[int] = []
    failed: List[Dict[str, Any]] = []
    nc: Optional[NATS] = None
    try:
        nc = NATS()
        await nc.connect(
            NATS_URL,
            connect_timeout=5,
            reconnect_time_wait=1,
            max_reconnect_attempts=1,
        )
        subject = f"$JS.API.STREAM.MSG.DELETE.{EVENTS_STREAM}"
        for seq in sequences:
            try:
                payload = json.dumps({"seq": seq}).encode("utf-8")
                data = await _js_api_request(nc, subject, payload, timeout=10.0)
                err = _api_error_str(data)
                if err:
                    failed.append({"seq": seq, "error": err})
                else:
                    deleted.append(seq)
            except Exception as e:
                failed.append({"seq": seq, "error": str(e)})
    finally:
        if nc and not nc.is_closed:
            try:
                await nc.close()
            except Exception as e:
                logger.debug(f"Error closing NATS connection: {e}")
    return {"deleted": deleted, "failed": failed}
