"""Batched CT monitor log persistence client."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_POST_TIMEOUT_SEC = 30


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CTLogSubmitter:
    """Buffers CT monitor decisions and persists them through the internal API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        flush_interval: float = 5.0,
        batch_max: int = 200,
        queue_maxsize: int = 5000,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.flush_interval = max(1.0, float(flush_interval))
        self.batch_max = max(1, int(batch_max))
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
            maxsize=max(1, int(queue_maxsize))
        )
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self.submitted = 0
        self.dropped = 0
        self.failures = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            "CT log submitter started (flush_interval=%ss, batch_max=%s)",
            self.flush_interval,
            self.batch_max,
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
        logger.info("CT log submitter stopped")

    def enqueue(self, log: Dict[str, Any]) -> None:
        if "occurred_at" not in log or log["occurred_at"] is None:
            log = {**log, "occurred_at": _utc_iso()}
        try:
            self._queue.put_nowait(log)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                logger.warning("CT monitor log queue full; dropped %s event(s)", self.dropped)

    async def flush_now(self) -> None:
        batch: List[Dict[str, Any]] = []
        while len(batch) < self.batch_max:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if batch:
            await self._post_batch(batch)

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_now()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("CT log submitter flush loop error: %s", e)

    async def _post_batch(self, batch: List[Dict[str, Any]]) -> None:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            timeout = aiohttp.ClientTimeout(total=_POST_TIMEOUT_SEC)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.api_url}/internal/ct-monitor/logs",
                    json={"logs": batch},
                    headers=headers,
                ) as resp:
                    if resp.status not in (200, 201, 202):
                        body = await resp.text()
                        self.failures += 1
                        logger.warning(
                            "CT log submit failed: HTTP %s %s",
                            resp.status,
                            body[:300],
                        )
                        return
        except aiohttp.ClientError as e:
            self.failures += 1
            logger.warning("CT log submit HTTP error: %s", e)
            return
        except Exception as e:
            self.failures += 1
            logger.warning("CT log submit error: %s", e)
            return

        self.submitted += len(batch)

    def get_stats(self) -> Dict[str, int]:
        return {
            "ct_logs_buffered": self._queue.qsize(),
            "ct_logs_submitted": self.submitted,
            "ct_logs_dropped": self.dropped,
            "ct_log_submit_failures": self.failures,
        }
