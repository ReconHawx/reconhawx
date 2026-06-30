"""
CT asset submitter: batches in-scope SANs into POST /assets calls.

Hostnames matched against a program's scope are buffered per program and
flushed periodically (or when a program buffer is full) as subdomain assets:

    POST {API_URL}/assets
    {"program_id": "...", "assets": {"subdomain": [{"name": "..."}, ...]}}

No DNS resolution happens here — the API inserts subdomains whether or not
they resolve, and re-checks program scope server-side (the authority on what
lands in the database).

Redis dedup keys (``ct_monitor:asset_seen:{program_id}:{hostname}``) are set
only after a successful POST so failed batches are retried on later sightings.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Set

import aiohttp

if TYPE_CHECKING:
    from ct_log_submitter import CTLogSubmitter

logger = logging.getLogger(__name__)

_POST_TIMEOUT_SEC = 30


class CTAssetSubmitter:
    """Buffers scope-matched hostnames and submits them as subdomain assets."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        redis_client=None,
        *,
        cache_ttl: int = 86400,
        flush_interval: float = 15.0,
        batch_max: int = 200,
        log_submitter: Optional["CTLogSubmitter"] = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.redis_client = redis_client
        self.log_submitter = log_submitter
        self.cache_ttl = max(1, int(cache_ttl))
        self.flush_interval = max(1.0, float(flush_interval))
        self.batch_max = max(1, int(batch_max))

        # program_id -> buffered hostnames; program_id -> program_name (logging)
        self._buffers: Dict[str, Set[str]] = {}
        self._program_names: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        # Counters surfaced in /status
        self.assets_submitted = 0
        self.asset_dedup_hits = 0
        self.batches_posted = 0
        self.post_failures = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            "CT asset submitter started (flush_interval=%ss, batch_max=%s, cache_ttl=%ss)",
            self.flush_interval,
            self.batch_max,
            self.cache_ttl,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush_now()
        logger.info("CT asset submitter stopped")

    def _dedup_key(self, program_id: str, hostname: str) -> str:
        return f"ct_monitor:asset_seen:{program_id}:{hostname}"

    def _seen_recently(self, program_id: str, hostname: str) -> bool:
        if self.redis_client is None:
            return False
        try:
            return self.redis_client.get(self._dedup_key(program_id, hostname)) is not None
        except Exception as e:
            logger.warning("Redis dedup read error for %s: %s", hostname, e)
            return False

    def _mark_seen(self, program_id: str, hostnames: List[str]) -> None:
        if self.redis_client is None:
            return
        try:
            pipe = self.redis_client.pipeline()
            for hostname in hostnames:
                pipe.setex(self._dedup_key(program_id, hostname), self.cache_ttl, "1")
            pipe.execute()
        except Exception as e:
            logger.warning("Redis dedup write error: %s", e)

    async def add(self, hostname: str, program_name: str, program_id: str) -> None:
        """Queue a scope-matched hostname for submission (dedup via Redis)."""
        hostname = hostname.lower().strip()
        if not hostname:
            return

        if self._seen_recently(program_id, hostname):
            self.asset_dedup_hits += 1
            self._log_asset_submission(
                program_id=program_id,
                program_name=program_name,
                hostname=hostname,
                outcome="dedup_skipped",
            )
            return

        flush_program: Optional[str] = None
        async with self._lock:
            buffer = self._buffers.setdefault(program_id, set())
            self._program_names[program_id] = program_name
            buffer.add(hostname)
            self._log_asset_submission(
                program_id=program_id,
                program_name=program_name,
                hostname=hostname,
                outcome="queued",
                details={"buffer_size": len(buffer)},
            )
            if len(buffer) >= self.batch_max:
                flush_program = program_id

        if flush_program is not None:
            await self._flush_program(flush_program)

    async def flush_now(self) -> None:
        """Flush all buffered programs (used on stop and in tests)."""
        async with self._lock:
            program_ids = [pid for pid, buf in self._buffers.items() if buf]
        for program_id in program_ids:
            await self._flush_program(program_id)

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_now()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("CT asset submitter flush loop error: %s", e)

    async def _flush_program(self, program_id: str) -> None:
        async with self._lock:
            buffer = self._buffers.get(program_id)
            if not buffer:
                return
            hostnames = sorted(buffer)
            buffer.clear()
        await self._post_batch(program_id, hostnames)

    async def _post_batch(self, program_id: str, hostnames: List[str]) -> None:
        program_name = self._program_names.get(program_id, program_id)
        payload = {
            "program_id": program_id,
            "source": "ct_monitor",
            "assets": {"subdomain": [{"name": h} for h in hostnames]},
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            timeout = aiohttp.ClientTimeout(total=_POST_TIMEOUT_SEC)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.api_url}/assets",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status not in (200, 201, 202):
                        body = await resp.text()
                        logger.error(
                            "CT asset submit failed for program '%s': HTTP %s %s",
                            program_name,
                            resp.status,
                            body[:300],
                        )
                        self.post_failures += 1
                        self._log_batch_submission(
                            program_id=program_id,
                            program_name=program_name,
                            hostnames=hostnames,
                            outcome="submit_failed",
                            details={"http_status": resp.status, "body": body[:300]},
                        )
                        return
        except aiohttp.ClientError as e:
            logger.error("CT asset submit HTTP error for program '%s': %s", program_name, e)
            self.post_failures += 1
            self._log_batch_submission(
                program_id=program_id,
                program_name=program_name,
                hostnames=hostnames,
                outcome="submit_failed",
                details={"error": str(e)},
            )
            return
        except Exception as e:
            logger.error("CT asset submit error for program '%s': %s", program_name, e)
            self.post_failures += 1
            self._log_batch_submission(
                program_id=program_id,
                program_name=program_name,
                hostnames=hostnames,
                outcome="submit_failed",
                details={"error": str(e)},
            )
            return

        self.batches_posted += 1
        self.assets_submitted += len(hostnames)
        self._mark_seen(program_id, hostnames)
        self._log_batch_submission(
            program_id=program_id,
            program_name=program_name,
            hostnames=hostnames,
            outcome="submitted",
            details={"batch_size": len(hostnames)},
        )
        logger.info(
            "CT ASSET: submitted %s subdomain(s) for program '%s' (e.g. %s)",
            len(hostnames),
            program_name,
            ", ".join(hostnames[:3]),
        )

    def _log_asset_submission(
        self,
        *,
        program_id: str,
        program_name: str,
        hostname: str,
        outcome: str,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        if not self.log_submitter:
            return
        self.log_submitter.enqueue(
            {
                "program_id": program_id,
                "program_name": program_name,
                "event_type": "asset_submission",
                "outcome": outcome,
                "domain": hostname,
                "details": details or {},
            }
        )

    def _log_batch_submission(
        self,
        *,
        program_id: str,
        program_name: str,
        hostnames: List[str],
        outcome: str,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        for hostname in hostnames:
            event_details = dict(details or {})
            event_details["batch_domains"] = hostnames
            self._log_asset_submission(
                program_id=program_id,
                program_name=program_name,
                hostname=hostname,
                outcome=outcome,
                details=event_details,
            )

    def get_stats(self) -> Dict[str, int]:
        return {
            "assets_submitted": self.assets_submitted,
            "asset_dedup_hits": self.asset_dedup_hits,
            "batches_posted": self.batches_posted,
            "post_failures": self.post_failures,
            "buffered": sum(len(b) for b in self._buffers.values()),
        }
