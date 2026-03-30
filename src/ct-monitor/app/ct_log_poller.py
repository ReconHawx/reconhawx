"""
Direct Certificate Transparency Log Poller.

Polls CT logs directly instead of relying on CertStream.
This is more reliable as it doesn't depend on third-party aggregators.

CT Log API documentation:
https://datatracker.ietf.org/doc/html/rfc6962#section-4
"""

import asyncio
import logging
import base64
import struct
import tldextract
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Set, List, Awaitable
from dataclasses import dataclass

import aiohttp
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from models import CertificateInfo, ProcessingStats

logger = logging.getLogger(__name__)

# Popular CT logs to poll
# These are high-volume logs that see most certificates.
# Note: Log URLs are year/half-year based shards - re-evaluate yearly.
# Reference lists:
#   - Let's Encrypt Sunlight logs: https://log.sycamore.ct.letsencrypt.org/, https://log.willow.ct.letsencrypt.org/
#   - Google known logs: https://github.com/google/certificate-transparency-community-site/blob/master/docs/google/known-logs.md
DEFAULT_CT_LOGS = [
    # Sectigo "Elephant" logs (current shards)
    {
        "name": "Sectigo Elephant 2026 H1",
        "url": "https://elephant2026h1.ct.sectigo.com/",
        "operator": "Sectigo",
    },
    {
        "name": "Sectigo Elephant 2026 H2",
        "url": "https://elephant2026h2.ct.sectigo.com/",
        "operator": "Sectigo",
    },
    {
        "name": "Sectigo Elephant 2027 H1",
        "url": "https://elephant2027h1.ct.sectigo.com/",
        "operator": "Sectigo",
    },
    {
        "name": "Sectigo Elephant 2027 H2",
        "url": "https://elephant2027h2.ct.sectigo.com/",
        "operator": "Sectigo",
    },

    # Let's Encrypt "Sycamore" Sunlight logs ([log.sycamore.ct.letsencrypt.org](https://log.sycamore.ct.letsencrypt.org/))
    {
        "name": "LE Sycamore 2026 H1",
        "url": "https://log.sycamore.ct.letsencrypt.org/2026h1/",
        "operator": "Let's Encrypt",
    },
    {
        "name": "LE Sycamore 2026 H2",
        "url": "https://log.sycamore.ct.letsencrypt.org/2026h2/",
        "operator": "Let's Encrypt",
    },

    # Let's Encrypt "Willow" Sunlight logs ([log.willow.ct.letsencrypt.org](https://log.willow.ct.letsencrypt.org/))
    {
        "name": "LE Willow 2026 H1",
        "url": "https://log.willow.ct.letsencrypt.org/2026h1/",
        "operator": "Let's Encrypt",
    },
    {
        "name": "LE Willow 2026 H2",
        "url": "https://log.willow.ct.letsencrypt.org/2026h2/",
        "operator": "Let's Encrypt",
    },

    # Google Solera logs (EU region) from the known-logs list
    # See entries like `https://ct.googleapis.com/logs/eu1/solera2026h1/` in the Google known-logs doc.
    {
        "name": "Google Solera 2026 H1 (EU1)",
        "url": "https://ct.googleapis.com/logs/eu1/solera2026h1/",
        "operator": "Google",
    },
    {
        "name": "Google Solera 2026 H2 (EU1)",
        "url": "https://ct.googleapis.com/logs/eu1/solera2026h2/",
        "operator": "Google",
    },
    {
        "name": "Google Solera 2027 H1 (EU1)",
        "url": "https://ct.googleapis.com/logs/eu1/solera2027h1/",
        "operator": "Google",
    },

    # TODO: Add TrustAsia CT logs from https://ct.trustasia.com/blog/english/ once
    #       specific log URLs are selected (they can also be passed in via ct_logs).
]


@dataclass
class CTLogState:
    """Tracks state for a single CT log"""
    name: str
    url: str
    operator: str
    tree_size: int = 0
    last_index: int = 0
    errors: int = 0
    last_poll: Optional[datetime] = None


class CTLogPoller:
    """
    Polls Certificate Transparency logs directly for new certificates.
    
    This approach is more reliable than CertStream as it doesn't depend
    on third-party aggregators. It polls multiple CT logs and extracts
    certificate information.
    """
    
    def __init__(
        self,
        callback: Callable[[CertificateInfo], Awaitable[None]],
        ct_logs: Optional[List[Dict[str, str]]] = None,
        tld_filter: Optional[Set[str]] = None,
        poll_interval: int = 10,
        batch_size: int = 100,
        max_entries_per_poll: int = 1000,
        start_offset: int = 0
    ):
        """
        Initialize CT Log Poller.
        
        Args:
            callback: Async function to call for each certificate
            ct_logs: List of CT logs to poll (default: major logs)
            tld_filter: Optional set of TLDs to filter
            poll_interval: Seconds between polls
            batch_size: Number of entries to fetch per request
            max_entries_per_poll: Maximum entries to process per poll cycle
            start_offset: Number of entries behind current to start (for testing)
        """
        self.callback = callback
        self.ct_logs = ct_logs or DEFAULT_CT_LOGS
        self.tld_filter = tld_filter or set()
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_entries_per_poll = max_entries_per_poll
        self.start_offset = start_offset
        
        self._running = False
        self._stats = ProcessingStats()
        self._log_states: Dict[str, CTLogState] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Initialize log states
        for log in self.ct_logs:
            self._log_states[log["url"]] = CTLogState(
                name=log["name"],
                url=log["url"],
                operator=log.get("operator", "Unknown")
            )
    
    async def start(self):
        """Start polling CT logs"""
        self._running = True
        logger.info(f"Starting CT Log Poller with {len(self.ct_logs)} logs")
        
        if self.tld_filter:
            logger.info(f"TLD filter enabled: {sorted(self.tld_filter)}")
        else:
            logger.warning("No TLD filter - processing ALL certificates (high volume!)")
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        try:
            # Initialize - get current tree sizes
            await self._initialize_log_states()
            
            # Start polling loop
            while self._running:
                try:
                    await self._poll_all_logs()
                    await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in poll cycle: {e}")
                    self._stats.errors += 1
                    await asyncio.sleep(self.poll_interval)
        finally:
            if self._session:
                await self._session.close()
    
    def stop(self):
        """Stop polling"""
        logger.info("Stopping CT Log Poller...")
        self._running = False
    
    async def _initialize_log_states(self):
        """Get current tree sizes for all logs"""
        logger.info("Initializing CT log states...")
        
        working_logs = 0
        failed_logs = []
        
        for url, state in list(self._log_states.items()):
            try:
                sth = await self._get_sth(url)
                if sth and sth.get("tree_size", 0) > 0:
                    state.tree_size = sth.get("tree_size", 0)
                    # Start from current position minus offset (for testing)
                    if self.start_offset > 0:
                        # When offset > 0, go back that many entries
                        state.last_index = max(0, state.tree_size - self.start_offset)
                        logger.info(
                            f"  ✓ {state.name}: tree_size={state.tree_size:,}, "
                            f"starting at {state.last_index:,} ({self.start_offset:,} entries behind)"
                        )
                    else:
                        # When offset = 0, start from tree_size - 1 to process the most recent entry
                        # This ensures we process at least one entry on startup, then continue with new ones
                        state.last_index = max(0, state.tree_size - 1)
                        logger.info(
                            f"  ✓ {state.name}: tree_size={state.tree_size:,}, "
                            f"starting at {state.last_index:,} (will process new entries only)"
                        )
                    working_logs += 1
                else:
                    failed_logs.append(state.name)
                    # Remove non-working logs to avoid repeated failures
                    del self._log_states[url]
            except Exception as e:
                logger.warning(f"  ✗ {state.name}: {e}")
                state.errors += 1
                failed_logs.append(state.name)
                del self._log_states[url]
        
        if failed_logs:
            logger.warning(f"Removed {len(failed_logs)} unavailable logs: {', '.join(failed_logs)}")
        
        if working_logs == 0:
            logger.error("No CT logs available! Cannot monitor certificates.")
        else:
            logger.info(f"Successfully connected to {working_logs} CT log(s)")
    
    async def _get_sth(self, log_url: str) -> Optional[Dict[str, Any]]:
        """Get Signed Tree Head (current state) from a CT log"""
        try:
            url = f"{log_url}ct/v1/get-sth"
            # Add cache-busting headers
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Log the STH timestamp for debugging
                    timestamp = data.get("timestamp", 0)
                    if timestamp:
                        from datetime import datetime
                        sth_time = datetime.utcfromtimestamp(timestamp / 1000)
                        logger.debug(f"STH from {log_url}: timestamp={sth_time.isoformat()}")
                    return data
                else:
                    logger.debug(f"STH request failed: {resp.status}")
                    return None
        except Exception as e:
            logger.debug(f"Error getting STH from {log_url}: {e}")
            return None
    
    async def _poll_all_logs(self):
        """Poll all CT logs for new entries"""
        logger.debug(f"Polling {len(self._log_states)} CT logs...")
        tasks = []
        for url, state in self._log_states.items():
            tasks.append(self._poll_log(state))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Poll task failed: {result}")
    
    async def _poll_log(self, state: CTLogState):
        """Poll a single CT log for new entries"""
        try:
            # Get current tree size
            sth = await self._get_sth(state.url)
            if not sth:
                logger.debug(f"{state.name}: Failed to get STH")
                return
            
            current_size = sth.get("tree_size", 0)
            
            # Log tree size comparison
            logger.debug(
                f"{state.name}: current_size={current_size:,}, "
                f"last_index={state.last_index:,}, "
                f"diff={current_size - state.last_index:,}"
            )
            
            # Check if there are new entries
            if current_size <= state.last_index:
                return
            
            new_entries = current_size - state.last_index
            entries_to_fetch = min(new_entries, self.max_entries_per_poll)
            
            if entries_to_fetch > 0:
                logger.info(
                    f"📥 {state.name}: {new_entries:,} new entries, "
                    f"fetching {entries_to_fetch:,}"
                )
            
            # Fetch entries in batches
            start = state.last_index
            end = start + entries_to_fetch
            
            for batch_start in range(start, end, self.batch_size):
                if not self._running:
                    break
                
                batch_end = min(batch_start + self.batch_size - 1, end - 1)
                
                entries = await self._get_entries(state.url, batch_start, batch_end)
                if entries:
                    await self._process_entries(entries, state)
                    state.last_index = batch_end + 1
            
            state.tree_size = current_size
            state.last_poll = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error polling {state.name}: {e}")
            state.errors += 1
    
    async def _get_entries(
        self, 
        log_url: str, 
        start: int, 
        end: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Get entries from a CT log"""
        try:
            url = f"{log_url}ct/v1/get-entries?start={start}&end={end}"
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("entries", [])
                else:
                    logger.debug(f"get-entries failed: {resp.status}")
                    return None
        except Exception as e:
            logger.debug(f"Error getting entries: {e}")
            return None
    
    async def _process_entries(
        self, 
        entries: List[Dict[str, Any]], 
        state: CTLogState
    ):
        """Process CT log entries and extract certificates"""
        sample_cert = None  # Track first certificate in batch for debug output
        
        for entry in entries:
            if not self._running:
                break
            
            self._stats.total_received += 1
            
            try:
                # Parse the entry
                cert_info = self._parse_entry(entry, state)
                if cert_info:
                    # Apply TLD filter
                    if self.tld_filter:
                        filtered_domains = []
                        for domain in cert_info.domains:
                            tld = tldextract.extract(domain).suffix
                            if tld in self.tld_filter:
                                filtered_domains.append(domain)
                        
                        if not filtered_domains:
                            self._stats.filtered_by_tld += 1
                            continue
                        
                        cert_info.domains = filtered_domains
                    
                    # Capture first certificate in batch for debug output
                    if sample_cert is None:
                        sample_cert = cert_info
                    
                    self._stats.processed += 1
                    
                    # Log progress
                    if self._stats.processed % 50 == 0:
                        logger.info(
                            f"🔍 Processed {self._stats.processed} certs | "
                            f"Latest: {cert_info.domains[:3]} | "
                            f"Issuer: {cert_info.issuer}"
                        )
                    
                    # Call callback
                    await self.callback(cert_info)
                    
            except Exception as e:
                logger.debug(f"Error processing entry: {e}")
                self._stats.errors += 1
        
        # Log sample certificate from batch
        if sample_cert:
            domains_str = ", ".join(sample_cert.domains[:3])
            if len(sample_cert.domains) > 3:
                domains_str += f" (+{len(sample_cert.domains) - 3} more)"
            logger.debug(
                f"📋 Batch sample [{state.name}]: domain={domains_str} | "
                f"not_before={sample_cert.not_before} | issuer={sample_cert.issuer}"
            )
    
    def _parse_entry(
        self, 
        entry: Dict[str, Any], 
        state: CTLogState
    ) -> Optional[CertificateInfo]:
        """Parse a CT log entry and extract certificate info"""
        try:
            leaf_input = base64.b64decode(entry.get("leaf_input", ""))
            extra_data = base64.b64decode(entry.get("extra_data", ""))
            
            # Parse MerkleTreeLeaf structure
            # https://datatracker.ietf.org/doc/html/rfc6962#section-3.4
            if len(leaf_input) < 2:
                return None
            
            # Skip version (1 byte) and leaf type (1 byte)
            # Then parse TimestampedEntry
            pos = 2
            
            # Skip timestamp (8 bytes)
            pos += 8
            
            # Get entry type (2 bytes)
            if len(leaf_input) < pos + 2:
                return None
            entry_type = struct.unpack(">H", leaf_input[pos:pos+2])[0]
            pos += 2
            
            cert_data = None
            
            if entry_type == 0:  # X509Entry
                # Get certificate length (3 bytes)
                if len(leaf_input) < pos + 3:
                    return None
                cert_len = struct.unpack(">I", b"\x00" + leaf_input[pos:pos+3])[0]
                pos += 3
                
                # Get certificate
                if len(leaf_input) < pos + cert_len:
                    return None
                cert_data = leaf_input[pos:pos+cert_len]
                
            elif entry_type == 1:  # PrecertEntry
                # Skip issuer key hash (32 bytes)
                pos += 32
                
                # Get TBS certificate length (3 bytes)
                if len(leaf_input) < pos + 3:
                    return None
                pos += 3
                
                # For precerts, the actual cert is in extra_data
                # Parse certificate chain from extra_data
                if len(extra_data) >= 3:
                    cert_chain_len = struct.unpack(">I", b"\x00" + extra_data[0:3])[0]
                    if len(extra_data) >= 3 + cert_chain_len and cert_chain_len >= 3:
                        cert_len = struct.unpack(">I", b"\x00" + extra_data[3:6])[0]
                        if len(extra_data) >= 6 + cert_len:
                            cert_data = extra_data[6:6+cert_len]
            
            if not cert_data:
                return None
            
            # Parse X.509 certificate
            cert = x509.load_der_x509_certificate(cert_data, default_backend())
            
            # Extract domains
            domains = set()
            
            # Get Common Name
            try:
                for attr in cert.subject:
                    if attr.oid == x509.oid.NameOID.COMMON_NAME:
                        cn = attr.value
                        if cn and isinstance(cn, str):
                            clean = cn.lstrip("*.").lower().strip()
                            if clean and "." in clean:
                                domains.add(clean)
            except Exception:
                pass
            
            # Get Subject Alternative Names
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        clean = name.value.lstrip("*.").lower().strip()
                        if clean and "." in clean:
                            domains.add(clean)
            except x509.ExtensionNotFound:
                pass
            except Exception:
                pass
            
            if not domains:
                return None
            
            # Extract issuer info
            issuer_org = "Unknown"
            issuer_cn = "Unknown"
            try:
                for attr in cert.issuer:
                    if attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                        issuer_org = attr.value
                    elif attr.oid == x509.oid.NameOID.COMMON_NAME:
                        issuer_cn = attr.value
            except Exception:
                pass
            
            return CertificateInfo(
                domains=list(domains),
                issuer=issuer_org,
                issuer_cn=issuer_cn,
                not_before=cert.not_valid_before_utc.isoformat() if hasattr(cert, 'not_valid_before_utc') else str(cert.not_valid_before),
                not_after=cert.not_valid_after_utc.isoformat() if hasattr(cert, 'not_valid_after_utc') else str(cert.not_valid_after),
                fingerprint=cert.fingerprint(cert.signature_hash_algorithm).hex() if cert.signature_hash_algorithm else None,
                serial_number=str(cert.serial_number),
                source=state.name,
                cert_index=None,
                seen_at=datetime.utcnow().isoformat(),
                update_type="X509LogEntry"
            )
            
        except Exception as e:
            logger.debug(f"Error parsing certificate: {e}")
            return None
    
    def get_stats(self) -> ProcessingStats:
        """Get processing statistics"""
        return self._stats
    
    def get_log_states(self) -> Dict[str, Dict[str, Any]]:
        """Get current state of all CT logs"""
        return {
            url: {
                "name": state.name,
                "operator": state.operator,
                "tree_size": state.tree_size,
                "last_index": state.last_index,
                "errors": state.errors,
                "last_poll": state.last_poll.isoformat() if state.last_poll else None
            }
            for url, state in self._log_states.items()
        }

