"""
Real-time Certificate Transparency log consumer via self-hosted CertStream.

Uses certstream-python (WebSocket client) in a background thread and bridges
messages into asyncio for certificate processing.
"""

import asyncio
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from certstream.core import CertStreamClient

from models import CertificateInfo, ProcessingStats

logger = logging.getLogger(__name__)

DEFAULT_CERTSTREAM_URL = "ws://certstream:4000/"
_QUEUE_DROP_LOG_INTERVAL_SEC = 10.0


def extract_domains_from_message(cert_data: Dict[str, Any]) -> Set[str]:
    """Lightweight domain extraction for pre-queue TLD filtering."""
    if cert_data.get("message_type") != "certificate_update":
        return set()
    data = cert_data.get("data", {})
    leaf_cert = data.get("leaf_cert", {})
    all_domains: Set[str] = set()

    subject = leaf_cert.get("subject", {})
    cn = subject.get("CN")
    if cn and isinstance(cn, str):
        all_domains.add(cn.lower().strip())

    for domain in leaf_cert.get("all_domains", []):
        if isinstance(domain, str):
            clean = domain.lstrip("*.").lower().strip()
            if clean:
                all_domains.add(clean)

    return all_domains


def message_passes_tld_filter(cert_data: Dict[str, Any], tld_filter: Optional[Set[str]]) -> bool:
    """Return True if the frame should be enqueued (no filter = accept all)."""
    if not tld_filter:
        return True
    domains = extract_domains_from_message(cert_data)
    if not domains:
        return False
    for domain in domains:
        tld = domain.split(".")[-1] if "." in domain else ""
        if tld in tld_filter:
            return True
    return False


class _StoppableCertStreamClient(CertStreamClient):
    """CertStream WebSocket client that honors an external stop event."""

    def __init__(
        self,
        message_callback,
        url: str,
        stop_event: threading.Event,
        skip_heartbeats: bool = True,
        on_open=None,
        on_error=None,
    ):
        self._stop_event = stop_event
        super().__init__(
            message_callback,
            url,
            skip_heartbeats=skip_heartbeats,
            on_open=on_open,
            on_error=on_error,
        )

    def _on_message(self, ws, message):
        if self._stop_event.is_set():
            try:
                ws.close()
            except Exception:
                pass
            return
        super()._on_message(ws, message)


class CertStreamConsumer:
    """
    Consumes certificate transparency logs in real-time via CertStream.

    Aggregates all major CT logs through certstream-server; TLD filtering
    is applied before enqueue and again when building CertificateInfo.
    """

    def __init__(
        self,
        callback: Callable[[CertificateInfo], Awaitable[None]],
        certstream_url: str = DEFAULT_CERTSTREAM_URL,
        tld_filter: Optional[Set[str]] = None,
        reconnect_delay: int = 5,
        queue_maxsize: int = 5000,
        yield_every_n: int = 50,
    ):
        self.callback = callback
        self.certstream_url = certstream_url
        self.tld_filter = tld_filter or set()
        self.reconnect_delay = reconnect_delay
        self._running = False
        self._stats = ProcessingStats()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client: Optional[_StoppableCertStreamClient] = None
        self._queue_maxsize = max(1, int(queue_maxsize))
        self._yield_every_n = max(1, int(yield_every_n))
        self._last_queue_drop_log = 0.0
        self._processed_since_yield = 0

    async def start(self):
        """Start consuming certificates with automatic reconnection."""
        self._running = True
        self._stop_event.clear()
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self._queue_maxsize)

        logger.info("Starting CertStream consumer (URL: %s)", self.certstream_url)
        if self.tld_filter:
            logger.info("TLD filter enabled: %s", sorted(self.tld_filter))
        else:
            logger.info("TLD filter disabled — processing all certificate TLDs")

        self._processor_task = asyncio.create_task(self._process_queue())
        self._thread = threading.Thread(
            target=self._run_certstream_thread,
            name="certstream-consumer",
            daemon=True,
        )
        self._thread.start()

        try:
            await self._processor_task
        except asyncio.CancelledError:
            logger.info("CertStream consumer cancelled")
            raise

    def _log_queue_drop(self) -> None:
        now = time.monotonic()
        if now - self._last_queue_drop_log >= _QUEUE_DROP_LOG_INTERVAL_SEC:
            self._last_queue_drop_log = now
            qsize = self._queue.qsize() if self._queue is not None else 0
            logger.warning(
                "CertStream message queue full (max=%s, size=%s); dropped=%s total",
                self._queue_maxsize,
                qsize,
                self._stats.queue_drops,
            )

    def _enqueue_message(self, message: Dict[str, Any]) -> None:
        if not self._running or self._queue is None or self._loop is None:
            return

        if not message_passes_tld_filter(message, self.tld_filter or None):
            self._stats.filtered_before_queue += 1
            return

        if self._queue.qsize() >= int(self._queue_maxsize * 0.8):
            self._stats.queue_drops += 1
            self._log_queue_drop()
            return

        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._stats.queue_drops += 1
            self._log_queue_drop()

    def get_queue_size(self) -> int:
        if self._queue is None:
            return 0
        return self._queue.qsize()

    def get_queue_maxsize(self) -> int:
        return self._queue_maxsize

    def _run_certstream_thread(self) -> None:
        def on_message(message, _context):
            if self._stop_event.is_set():
                return
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._enqueue_message, message)

        def on_open():
            logger.info("Connected to CertStream, receiving certificates...")

        def on_error(exc):
            if self._stop_event.is_set():
                return
            logger.warning("CertStream connection error: %s", exc)

        while self._running and not self._stop_event.is_set():
            try:
                client = _StoppableCertStreamClient(
                    on_message,
                    self.certstream_url,
                    stop_event=self._stop_event,
                    skip_heartbeats=True,
                    on_open=on_open,
                    on_error=on_error,
                )
                self._client = client
                client.run_forever(ping_interval=15)
            except Exception as e:
                if self._running and not self._stop_event.is_set():
                    logger.error("CertStream thread error: %s", e)
                    self._stats.errors += 1
            finally:
                self._client = None

            if self._running and not self._stop_event.is_set():
                logger.info(
                    "CertStream disconnected; reconnecting in %ss...",
                    self.reconnect_delay,
                )
                time.sleep(self.reconnect_delay)

    async def _process_queue(self) -> None:
        while self._running:
            try:
                cert_data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await self._process_certificate(cert_data)
            except Exception as e:
                logger.error("Error processing certificate: %s", e)
                self._stats.errors += 1
            finally:
                self._processed_since_yield += 1
                if self._processed_since_yield >= self._yield_every_n:
                    self._processed_since_yield = 0
                    await asyncio.sleep(0)

    async def _process_certificate(self, cert_data: Dict[str, Any]):
        """Process a single certificate from the stream."""
        self._stats.total_received += 1

        if self._stats.total_received % 100 == 0:
            logger.debug(
                "CertStream progress: received=%s, processed=%s, filtered=%s, pre_queue_filtered=%s",
                self._stats.total_received,
                self._stats.processed,
                self._stats.filtered_by_tld,
                self._stats.filtered_before_queue,
            )

        if self._stats.total_received <= 5:
            logger.info(
                "Raw certificate #%s: message_type=%s",
                self._stats.total_received,
                cert_data.get("message_type"),
            )

        message_type = cert_data.get("message_type")
        if message_type != "certificate_update":
            return

        data = cert_data.get("data", {})
        leaf_cert = data.get("leaf_cert", {})

        all_domains = set()

        subject = leaf_cert.get("subject", {})
        cn = subject.get("CN")
        if cn and isinstance(cn, str):
            all_domains.add(cn.lower().strip())

        all_domains_from_cert = leaf_cert.get("all_domains", [])
        for domain in all_domains_from_cert:
            if isinstance(domain, str):
                clean_domain = domain.lstrip("*.").lower().strip()
                if clean_domain:
                    all_domains.add(clean_domain)

        if not all_domains:
            return

        if self.tld_filter:
            filtered_domains = set()
            for domain in all_domains:
                tld = domain.split(".")[-1] if "." in domain else ""
                if tld in self.tld_filter:
                    filtered_domains.add(domain)

            if not filtered_domains:
                self._stats.filtered_by_tld += 1
                return

            all_domains = filtered_domains

        issuer = leaf_cert.get("issuer", {})
        cert_info = CertificateInfo(
            domains=list(all_domains),
            issuer=issuer.get("O", "Unknown") if isinstance(issuer, dict) else "Unknown",
            issuer_cn=issuer.get("CN", "Unknown") if isinstance(issuer, dict) else "Unknown",
            not_before=leaf_cert.get("not_before"),
            not_after=leaf_cert.get("not_after"),
            fingerprint=leaf_cert.get("fingerprint"),
            serial_number=leaf_cert.get("serial_number"),
            source=data.get("source", {}).get("name", "unknown"),
            cert_index=data.get("cert_index"),
            seen_at=data.get("seen"),
            update_type=data.get("update_type"),
        )

        self._stats.processed += 1

        if self._stats.processed % 50 == 0:
            logger.info(
                "Processed %s certs | Latest: %s | Issuer: %s",
                self._stats.processed,
                list(all_domains)[:3],
                cert_info.issuer,
            )

        if self._stats.processed <= 10:
            logger.debug(
                "Certificate #%s: domains=%s, issuer=%s",
                self._stats.processed,
                list(all_domains),
                cert_info.issuer,
            )

        try:
            await self.callback(cert_info)
        except Exception as e:
            logger.error("Error in certificate callback: %s", e)
            self._stats.errors += 1

    def stop(self):
        """Stop consuming certificates."""
        logger.info("Stopping CertStream consumer...")
        self._running = False
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        if self._processor_task and not self._processor_task.done():
            self._processor_task.cancel()

    def get_stats(self) -> ProcessingStats:
        """Get processing statistics."""
        return self._stats
