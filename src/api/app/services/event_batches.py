#!/usr/bin/env python3
"""
Event-handler batch status service for admin dashboard.

Reads Redis keys used by the event-handler's SimpleBatchManager to list
batches that are waiting to be flushed (max_events or max_delay).
"""

import logging
import os
import time
from typing import Any, Dict, List

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
BATCH_KEY_PREFIX = "notify:batch:"


def get_event_batches() -> Dict[str, Any]:
    """
    List all event-handler batches waiting in Redis.

    Scans for notify:batch:*:first_ts keys and returns batch info:
    handler_id, program_name, item_count, age_seconds, timeout_seconds.
    """
    result: Dict[str, Any] = {
        "connected": False,
        "batches": [],
        "error": None,
    }

    try:
        r = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        r.ping()
        result["connected"] = True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        result["error"] = str(e)
        return result

    current_time = int(time.time())
    batches: List[Dict[str, Any]] = []

    try:
        # count=1000 reduces round-trips vs default 10; critical for large keyspaces
        for key in r.scan_iter(match=f"{BATCH_KEY_PREFIX}*:meta", count=1000):
            try:
                key_str = key if isinstance(key, str) else key.decode("utf-8")
                parts = key_str.split(":")
                if len(parts) < 5:
                    continue

                handler_id = parts[2]
                program_name = ":".join(parts[3:-1])

                meta = r.hgetall(key)
                if not meta:
                    continue

                first_ts_raw = meta.get("first_ts") or meta.get(b"first_ts")
                if not first_ts_raw:
                    continue

                first_ts = int(first_ts_raw.decode("utf-8") if isinstance(first_ts_raw, bytes) else first_ts_raw)
                age = current_time - first_ts

                items_key = f"{BATCH_KEY_PREFIX}{handler_id}:{program_name}:items"
                item_count = r.llen(items_key)
                if item_count == 0:
                    continue

                timeout_raw = meta.get("timeout") or meta.get(b"timeout")
                timeout_seconds = (
                    int(timeout_raw.decode("utf-8") if isinstance(timeout_raw, bytes) else timeout_raw)
                    if timeout_raw else None
                )

                batches.append({
                    "handler_id": handler_id,
                    "program_name": program_name,
                    "item_count": item_count,
                    "age_seconds": age,
                    "timeout_seconds": timeout_seconds,
                    "first_ts": first_ts,
                })
            except Exception as e:
                logger.debug(f"Error processing batch key {key}: {e}")
                continue

        result["batches"] = sorted(batches, key=lambda b: -b["age_seconds"])

    except Exception as e:
        logger.error(f"Error listing event batches: {e}")
        result["error"] = str(e)

    return result
