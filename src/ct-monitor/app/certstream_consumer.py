"""
Real-time Certificate Transparency log consumer using CertStream.

CertStream aggregates CT logs from all major CAs and provides a 
WebSocket stream of newly issued certificates in real-time.

Processes ~5-10 million certificates per day.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional, Callable, Set, Awaitable
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from models import CertificateInfo, ProcessingStats

logger = logging.getLogger(__name__)

# Default CertStream URL
DEFAULT_CERTSTREAM_URL = "wss://certstream.calidog.io/"


class CertStreamConsumer:
    """
    Consumes certificate transparency logs in real-time via CertStream.
    
    CertStream provides ~5-10 million certificates per day from all major
    Certificate Authorities. We filter and process only relevant domains.
    """
    
    def __init__(
        self,
        callback: Callable[[CertificateInfo], Awaitable[None]],
        certstream_url: str = DEFAULT_CERTSTREAM_URL,
        tld_filter: Optional[Set[str]] = None,
        reconnect_delay: int = 5
    ):
        """
        Initialize CertStream consumer.
        
        Args:
            callback: Async function to call for each certificate
            certstream_url: CertStream WebSocket URL
            tld_filter: Optional set of TLDs to filter (e.g., {'com', 'net', 'org'})
                       If None, all certificates are processed
            reconnect_delay: Seconds to wait before reconnecting on disconnect
        """
        self.callback = callback
        self.certstream_url = certstream_url
        self.tld_filter = tld_filter or set()
        self.reconnect_delay = reconnect_delay
        self._running = False
        self._stats = ProcessingStats()
        self._websocket = None
    
    async def start(self):
        """Start consuming certificates with automatic reconnection"""
        self._running = True
        logger.info(f"Starting CertStream consumer (URL: {self.certstream_url})")
        
        if self.tld_filter:
            logger.info(f"TLD filter enabled: {sorted(self.tld_filter)}")
        else:
            logger.warning("No TLD filter - processing ALL certificates (high volume!)")
        
        while self._running:
            try:
                await self._consume_stream()
            except ConnectionClosedError as e:
                if self._running:
                    logger.warning(f"CertStream connection closed: {e}. Reconnecting in {self.reconnect_delay}s...")
                    await asyncio.sleep(self.reconnect_delay)
            except ConnectionClosed as e:
                if self._running:
                    logger.warning(f"CertStream connection closed: {e}. Reconnecting in {self.reconnect_delay}s...")
                    await asyncio.sleep(self.reconnect_delay)
            except asyncio.CancelledError:
                logger.info("CertStream consumer cancelled")
                break
            except Exception as e:
                if self._running:
                    logger.error(f"CertStream error: {e}. Reconnecting in {self.reconnect_delay}s...")
                    self._stats.errors += 1
                    await asyncio.sleep(self.reconnect_delay)
    
    async def _consume_stream(self):
        """Connect to CertStream and process certificates"""
        logger.info(f"Connecting to CertStream: {self.certstream_url}")
        
        try:
            async with websockets.connect(
                self.certstream_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                max_size=2**20  # 1MB max message size
            ) as ws:
                self._websocket = ws
                logger.info("✅ Connected to CertStream, receiving certificates...")
                logger.debug(f"WebSocket state: open={ws.open}, closed={ws.closed}")
                
                # Use explicit recv() instead of async for to better debug
                while self._running and ws.open:
                    try:
                        # Wait for message with timeout
                        message = await asyncio.wait_for(ws.recv(), timeout=60.0)
                        
                        # Log first message to confirm data reception
                        if self._stats.total_received == 0:
                            logger.info(f"🎉 First message received! Length: {len(message)} bytes")
                            logger.debug(f"First message preview: {message[:500]}...")
                        
                        try:
                            cert_data = json.loads(message)
                            await self._process_certificate(cert_data)
                        except json.JSONDecodeError as e:
                            logger.debug(f"Invalid JSON from CertStream: {e}")
                            self._stats.errors += 1
                        except Exception as e:
                            logger.error(f"Error processing certificate: {e}")
                            self._stats.errors += 1
                            
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ No message received in 60 seconds - CertStream may be stalled")
                        continue
                        
        except Exception as e:
            logger.error(f"WebSocket connection error: {type(e).__name__}: {e}")
            raise
    
    async def _process_certificate(self, cert_data: Dict[str, Any]):
        """Process a single certificate from the stream"""
        self._stats.total_received += 1
        
        # Log progress every 100 certificates
        if self._stats.total_received % 100 == 0:
            logger.debug(
                f"📡 CertStream progress: received={self._stats.total_received}, "
                f"processed={self._stats.processed}, filtered={self._stats.filtered_by_tld}"
            )
        
        # Log first few certificates for debugging
        if self._stats.total_received <= 5:
            logger.info(f"📜 Raw certificate #{self._stats.total_received}: message_type={cert_data.get('message_type')}")
        
        # CertStream message structure check
        message_type = cert_data.get("message_type")
        if message_type != "certificate_update":
            return
        
        data = cert_data.get("data", {})
        leaf_cert = data.get("leaf_cert", {})
        
        # Extract domains from certificate
        # Certificates contain: Common Name (CN) + Subject Alternative Names (SANs)
        all_domains = set()
        
        # Get Common Name
        subject = leaf_cert.get("subject", {})
        cn = subject.get("CN")
        if cn and isinstance(cn, str):
            all_domains.add(cn.lower().strip())
        
        # Get Subject Alternative Names (more common for multi-domain certs)
        all_domains_from_cert = leaf_cert.get("all_domains", [])
        for domain in all_domains_from_cert:
            if isinstance(domain, str):
                # Remove wildcard prefix if present
                clean_domain = domain.lstrip("*.").lower().strip()
                if clean_domain:
                    all_domains.add(clean_domain)
        
        if not all_domains:
            return
        
        # Apply TLD filter if configured
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
        
        # Build certificate info
        issuer = leaf_cert.get("issuer", {})
        cert_info = CertificateInfo(
            domains=list(all_domains),
            issuer=issuer.get("O", "Unknown"),
            issuer_cn=issuer.get("CN", "Unknown"),
            not_before=leaf_cert.get("not_before"),
            not_after=leaf_cert.get("not_after"),
            fingerprint=leaf_cert.get("fingerprint"),
            serial_number=leaf_cert.get("serial_number"),
            source=data.get("source", {}).get("name", "unknown"),
            cert_index=data.get("cert_index"),
            seen_at=data.get("seen"),
            update_type=data.get("update_type")
        )
        
        self._stats.processed += 1
        
        # Log every 50th processed certificate to show activity
        if self._stats.processed % 50 == 0:
            logger.info(
                f"🔍 Processed {self._stats.processed} certs | "
                f"Latest: {list(all_domains)[:3]} | Issuer: {cert_info.issuer}"
            )
        
        # Debug log for first 10 processed
        if self._stats.processed <= 10:
            logger.debug(f"📋 Certificate #{self._stats.processed}: domains={list(all_domains)}, issuer={cert_info.issuer}")
        
        # Call the callback with certificate info
        try:
            await self.callback(cert_info)
        except Exception as e:
            logger.error(f"Error in certificate callback: {e}")
            self._stats.errors += 1
    
    def stop(self):
        """Stop consuming certificates"""
        logger.info("Stopping CertStream consumer...")
        self._running = False
        
        # Close websocket if connected
        if self._websocket:
            asyncio.create_task(self._close_websocket())
    
    async def _close_websocket(self):
        """Close websocket connection"""
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
    
    def get_stats(self) -> ProcessingStats:
        """Get processing statistics"""
        return self._stats
