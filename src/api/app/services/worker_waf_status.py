"""
Aggregate per-worker-node WAF block entries from Redis (``waf:block:*`` keys).

Matches runner reputation layout in ``src/runner/app/services/waf_reputation.py``.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
WAF_BLOCK_PREFIX = "waf:block:"


def get_worker_waf_status() -> Dict[str, Any]:
    """
    Scan Redis for active WAF block keys and group JSON payloads by worker node name.

    Returns:
        redis_connected: whether ping succeeded before scan
        error: optional error string (connection failure or scan exception)
        blocked_by_node: mapping node name -> list of target detail dicts
    """
    result: Dict[str, Any] = {
        "redis_connected": False,
        "error": None,
        "blocked_by_node": {},
    }
    r: Optional[Any] = None
    try:
        r = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        r.ping()
        result["redis_connected"] = True
    except Exception as e:
        logger.error("Redis connection failed for worker WAF status: %s", e)
        result["error"] = str(e)
        return result

    blocked_by_node: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    try:
        assert r is not None
        for key in r.scan_iter(match=f"{WAF_BLOCK_PREFIX}*", count=1000):
            try:
                ttl = int(r.ttl(key))
                if ttl == -2:
                    continue
                raw = r.get(key)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("Skipping malformed WAF block payload at %s", key)
                    continue
                node = str(payload.get("node") or "").strip()
                if not node:
                    continue
                entry = {
                    "target": payload.get("target"),
                    "vendor": payload.get("vendor"),
                    "source": payload.get("source"),
                    "blocked_at": payload.get("blocked_at"),
                    "ttl_seconds": ttl if ttl >= 0 else None,
                    "evidence": payload.get("evidence") or [],
                }
                blocked_by_node[node].append(entry)
            except Exception as exc:
                logger.debug("Error processing WAF block key %s: %s", key, exc)
                continue

        for node in blocked_by_node:
            blocked_by_node[node].sort(key=lambda x: str(x.get("target") or ""))

        result["blocked_by_node"] = dict(blocked_by_node)
    except Exception as e:
        logger.error("Error scanning WAF block keys: %s", e)
        result["error"] = str(e)
    finally:
        try:
            if r is not None:
                r.close()
        except Exception:
            pass

    return result
