"""
Redis-backed (node, target) WAF quarantine state with TTL recovery.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Set
from urllib.parse import urlparse

import redis

logger = logging.getLogger(__name__)

_QUARANTINE_TTL = int(os.getenv("WAF_QUARANTINE_TTL", "1800"))
_SECONDARY_PROMOTE = max(1, int(os.getenv("WAF_SECONDARY_PROMOTE", "2")))
_SECONDARY_WINDOW = int(os.getenv("WAF_SECONDARY_WINDOW", "900"))

_PREFIX = "waf"
_BLOCK = f"{_PREFIX}:block"
_PROBE = f"{_PREFIX}:probed"
_HIT = f"{_PREFIX}:hit"
_INDEX = f"{_PREFIX}:index"


@dataclass
class WafReputationEntry:
    node: str
    target: str
    vendor: Optional[str]
    evidence: List[str]
    blocked_at: float
    source: str


def target_key(target: str) -> str:
    """Canonical key: scheme + host + port (URLs drop path/query for v1)."""
    t = (target or "").strip()
    if not t:
        return ""
    if t.startswith(("http://", "https://")):
        u = urlparse(t)
        host = (u.hostname or "").lower()
        if not host:
            return t.lower()
        port = u.port or (443 if u.scheme == "https" else 80)
        return f"{u.scheme}://{host}:{port}"
    t = t.lower()
    if ":" in t and not t.startswith("["):
        host, _, port = t.partition(":")
        if port.isdigit():
            return f"http://{host}:{port}"
        return f"http://{t}:80"
    return f"http://{t}:80"


def _sanitize_map_key(fragment: str) -> str:
    return fragment.replace(":", "|")


class WafReputation:
    """``identity`` here is worker node name (``NODE_NAME``) today; egress id later."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        *,
        redis_client: Optional[Any] = None,
    ):
        url = redis_url or os.getenv("REDIS_URL", "redis://dev-redis:6379/0")
        self._ttl = _QUARANTINE_TTL
        self.redis = redis_client
        if self.redis is None:
            try:
                self.redis = redis.from_url(url, decode_responses=True)
                self.redis.ping()
            except Exception as exc:  # noqa: BLE001
                logger.warning("WAF reputation Redis unavailable (%s); behaving as accept-all", exc)
                self.redis = None

    def _bkey(self, node: str, key: str) -> str:
        return f"{_BLOCK}:{_sanitize_map_key(node)}:{_sanitize_map_key(key)}"

    def _pkey(self, node: str, key: str) -> str:
        return f"{_PROBE}:{_sanitize_map_key(node)}:{_sanitize_map_key(key)}"

    def _hkey(self, node: str, key: str) -> str:
        return f"{_HIT}:{_sanitize_map_key(node)}:{_sanitize_map_key(key)}"

    def _ikey(self, key: str) -> str:
        return f"{_INDEX}:{_sanitize_map_key(key)}"

    def is_blocked(self, node: str, target: str) -> bool:
        if not self.redis:
            return False
        k = target_key(target)
        if not k:
            return False
        try:
            return bool(self.redis.exists(self._bkey(node, k)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("is_blocked Redis error: %s", exc)
            return False

    def blocked_nodes_verified_for(self, target: str) -> Set[str]:
        """Nodes that are both indexed and still have an active block key."""
        if not self.redis:
            return set()
        k = target_key(target)
        if not k:
            return set()
        try:
            members = list(self.redis.smembers(self._ikey(k)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("blocked_nodes_verified Redis error: %s", exc)
            return set()
        out: Set[str] = set()
        pipe = self.redis.pipeline()
        for node in members:
            pipe.exists(self._bkey(node, k))
        try:
            exists_flags = pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("blocked_nodes_verified pipeline error: %s", exc)
            return set()
        for node, exists in zip(members, exists_flags):
            if exists:
                out.add(node)
        return out

    def blocked_nodes_union_for_inputs(self, inputs: List[str]) -> Set[str]:
        union: Set[str] = set()
        for inp in inputs or []:
            union |= self.blocked_nodes_verified_for(str(inp))
        return union

    def union_excluded_sorted(self, inputs: List[str]) -> List[str]:
        """Sorted list suitable for Kubernetes NotIn affinity."""
        return sorted(self.blocked_nodes_union_for_inputs(inputs))

    def record_blocked(
        self,
        identity: str,
        target: str,
        *,
        vendor: Optional[str],
        evidence: List[str],
        source: str,
    ) -> None:
        if not self.redis:
            return
        k = target_key(target)
        if not k:
            return
        node = identity
        payload = json.dumps(
            {
                "node": node,
                "target": k,
                "vendor": vendor,
                "evidence": evidence[:25],
                "blocked_at": time.time(),
                "source": source,
            }
        )
        bk = self._bkey(node, k)
        ik = self._ikey(k)
        try:
            pipe = self.redis.pipeline()
            pipe.setex(bk, self._ttl, payload)
            pipe.sadd(ik, node)
            pipe.expire(ik, self._ttl)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_blocked failed: %s", exc)

    def record_secondary_signal(
        self,
        identity: str,
        target: str,
        vendor: Optional[str],
        evidence: List[str],
    ) -> None:
        if not self.redis:
            return
        k = target_key(target)
        if not k:
            return
        hk = self._hkey(identity, k)
        now = time.time()
        cutoff = now - _SECONDARY_WINDOW
        member = f"{now:.6f}-{id(self):x}"
        try:
            self.redis.zadd(hk, {member: now})
            self.redis.expire(hk, _SECONDARY_WINDOW + 120)
            self.redis.zremrangebyscore(hk, "-inf", cutoff)
            cnt = int(self.redis.zcard(hk) or 0)
            if cnt >= _SECONDARY_PROMOTE:
                self.record_blocked(
                    identity,
                    k,
                    vendor=vendor,
                    evidence=list(evidence or []),
                    source="secondary",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_secondary_signal failed: %s", exc)

    def has_recent_probe(self, node: str, target: str) -> bool:
        if not self.redis:
            return False
        k = target_key(target)
        if not k:
            return False
        try:
            return bool(self.redis.exists(self._pkey(node, k)))
        except Exception:
            return False

    def mark_probed(self, node: str, target: str) -> None:
        if not self.redis:
            return
        k = target_key(target)
        if not k:
            return
        try:
            self.redis.setex(self._pkey(node, k), self._ttl, "1")
        except Exception as exc:  # noqa: BLE001
            logger.warning("mark_probed failed: %s", exc)

    def clear(self, node: str, target: str) -> None:
        if not self.redis:
            return
        k = target_key(target)
        if not k:
            return
        bk = self._bkey(node, k)
        ik = self._ikey(k)
        hk = self._hkey(node, k)
        pk = self._pkey(node, k)
        try:
            pipe = self.redis.pipeline()
            pipe.delete(bk)
            pipe.srem(ik, node)
            pipe.delete(hk)
            pipe.delete(pk)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("clear failed: %s", exc)
