#!/usr/bin/env python3
"""
Certificate Transparency Monitor Service

Monitors CT logs in real-time for certificates issued to domains
that look similar to protected domains (typosquatting detection).

This service:
1. Streams certificates from CertStream (all major CT logs)
2. Matches certificate domains against protected domains per program
3. Publishes alerts to NATS when suspicious certificates are found
4. Triggers automatic typosquat analysis workflows

Usage:
    python main.py

Environment Variables:
    API_URL              - API base URL (default: http://api:8000)
    NATS_URL                  - NATS server URL (default: nats://nats:4222)
    INTERNAL_SERVICE_API_KEY  - API authentication key
    CT_TLD_FILTER            - Comma-separated TLDs (default: com,net,org,io,co,app)
    LOG_LEVEL                - Logging level (default: INFO)

Per-program similarity thresholds: API ct_monitor_program_settings.similarity_threshold.
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, Set, Optional, List, Any, Tuple

import aiohttp
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from config import get_config, CTMonitorConfig
import program_ct_settings
from certstream_consumer import CertStreamConsumer
from ct_log_poller import CTLogPoller
from variation_generator import DnstwistVariationGenerator
from protected_domain_similarity import best_match_among_protected
from alert_publisher import CTAlertPublisher
from models import CertificateInfo, ProcessingStats, MatchResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@dataclass
class ProgramCTMatchState:
    """Per-program keywords and API-aligned similarity inputs (protected_domain_similarity.py)."""

    keywords: List[str]
    similarity_threshold: float
    protected_list: List[str]


class CTMonitorService:
    """
    Main CT monitoring service.
    
    Coordinates all components:
    - CTLogPoller or CertStreamConsumer: Receives certificates
    - DnstwistVariationGenerator: Fast O(1) lookup for pre-computed variations
    - Keyword + API-aligned similarity vs protected domains (per-program threshold)
    - CTAlertPublisher: Publishes alerts to NATS
    """
    
    def __init__(self, config: Optional[CTMonitorConfig] = None):
        self.config = config or get_config()
        
        # Set log level from config
        logging.getLogger().setLevel(self.config.log_level)
        
        # Components (initialized in start())
        self.consumer: Optional[CertStreamConsumer] = None  # CertStream fallback
        self.poller: Optional[CTLogPoller] = None  # Direct CT log polling
        self.publisher: Optional[CTAlertPublisher] = None
        
        # Primary matcher: dnstwist variation generator (fast O(1) lookup)
        self.variation_generator = DnstwistVariationGenerator()
        
        # Keyword + similarity fallback (API-aligned; see protected_domain_similarity.py)
        self.program_match_states: Dict[str, ProgramCTMatchState] = {}
        
        # Protected domains by program
        self.protected_domains: Dict[str, Set[str]] = {}  # program_name -> domains
        
        # Redis client for caching typosquat domain existence checks
        self.redis_client: Optional[redis.Redis] = None
        if self.config.enable_cache:
            try:
                self.redis_client = redis.from_url(
                    self.config.redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                logger.info(f"✅ Redis cache initialized at {self.config.redis_url}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to connect to Redis cache: {e}. Cache will be disabled.")
                self.redis_client = None
        else:
            logger.info("Redis cache disabled by configuration")
        
        # State
        self._running = False
        self._stats = ProcessingStats()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._http_app: Optional[FastAPI] = None
        # Serialize config reload vs certificate matching (same in-memory structures)
        self._domain_config_lock = asyncio.Lock()
        # True if API reports ≥1 program with ct_monitoring_enabled (controls CT log fetching only)
        self._any_program_ct_monitoring_enabled: bool = False
        self._ct_fetch_active: bool = False
        self._ct_ingest_task: Optional[asyncio.Task] = None
        # Global runtime from API GET /internal/ct-monitor/runtime-settings (merged with defaults)
        self._runtime_overlay: Dict[str, int] = {
            "domain_refresh_interval": self.config.domain_refresh_interval,
            "stats_interval": self.config.stats_interval,
            "ct_poll_interval": self.config.ct_poll_interval,
            "ct_batch_size": self.config.ct_batch_size,
            "ct_max_entries_per_poll": self.config.ct_max_entries_per_poll,
            "ct_start_offset": self.config.ct_start_offset,
        }
        # Union of per-program TLD allowlists for CertStream / CTLogPoller
        self._ingestion_tld_union: Set[str] = program_ct_settings.default_tld_set()
        # Snapshot for /status: programs with ct_monitoring_enabled (after last successful refresh)
        self._programs_ct_enabled_detail: List[Dict[str, Any]] = []

    def _poll_sig_from_overlay(self) -> Tuple[int, int, int, int]:
        o = self._runtime_overlay
        return (
            int(o["ct_poll_interval"]),
            int(o["ct_batch_size"]),
            int(o["ct_max_entries_per_poll"]),
            int(o["ct_start_offset"]),
        )

    async def _fetch_runtime_settings_from_api(self) -> None:
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        url = f"{self.config.api_url.rstrip('/')}/internal/ct-monitor/runtime-settings"
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 403:
                        logger.warning(
                            "Runtime settings: API returned 403 (check INTERNAL_SERVICE_API_KEY)"
                        )
                        return
                    if resp.status != 200:
                        logger.warning("Runtime settings: HTTP %s", resp.status)
                        return
                    data = await resp.json()
                    s = data.get("settings")
                    if not isinstance(s, dict):
                        return
                    new_overlay = dict(self._runtime_overlay)
                    for k in self._runtime_overlay.keys():
                        if k in s:
                            try:
                                new_overlay[k] = int(s[k])
                            except (TypeError, ValueError):
                                pass
                    self._runtime_overlay = new_overlay
        except aiohttp.ClientError as e:
            logger.warning("Runtime settings fetch failed: %s", e)
        except Exception as e:
            logger.warning("Runtime settings fetch error: %s", e)

    async def reload_runtime_settings_now(self) -> None:
        """Apply new global runtime from API; restart CT ingestion if poll parameters changed."""
        if not self._running:
            raise RuntimeError("CT monitor service is not running")
        old_sig = self._poll_sig_from_overlay()
        await self._fetch_runtime_settings_from_api()
        new_sig = self._poll_sig_from_overlay()
        if old_sig != new_sig and self._ct_fetch_active:
            logger.info("CT poll/batch runtime changed; restarting CT ingestion")
            await self._stop_ct_ingestion()

    async def start(self):
        """Start the CT monitoring service"""
        if self._running:
            logger.warning("CT Monitor Service is already running")
            return
        
        logger.info("=" * 60)
        logger.info("Starting CT Monitor Service")
        logger.info("=" * 60)
        logger.info(f"API URL: {self.config.api_url}")
        logger.info(f"NATS URL: {self.config.nats_url}")
        logger.info("Per-program CT similarity / TLD filter from API; global intervals from API runtime settings")
        logger.info("=" * 60)
        
        self._running = True
        
        try:
            # Initialize publisher and connect to NATS
            self.publisher = CTAlertPublisher(self.config.nats_url)
            await self.publisher.connect()

            await self._fetch_runtime_settings_from_api()
            
            # Load protected domains from API
            await self._refresh_protected_domains()
            
            if not self.program_match_states:
                logger.warning("No CT match config loaded - alerts will not be generated")
                logger.warning("Ensure programs have ct_monitoring_enabled and protected domains or keywords")
            
            # Poller / CertStream are started only when ≥1 program has ct_monitoring_enabled
            self.poller = None
            self.consumer = None
            logger.info("Using direct CT log polling")            
            self._monitoring_task = asyncio.create_task(self._run_monitoring())
            
        except Exception as e:
            logger.error(f"Fatal error starting CT Monitor: {e}")
            self._running = False
            raise
    
    async def _run_monitoring(self):
        """Run domain refresh, stats, and conditional CT log / CertStream ingestion."""
        try:
            await asyncio.gather(
                self._ct_ingestion_loop(),
                self._domain_refresh_loop(),
                self._stats_reporter(),
                return_exceptions=True,
            )
        except asyncio.CancelledError:
            logger.info("Monitoring task cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring task: {e}")
            self._running = False

    async def _ct_ingestion_loop(self):
        """Start or stop CT provider fetching based on program settings."""
        try:
            while self._running:
                await self._reconcile_ct_ingestion()
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        finally:
            await self._stop_ct_ingestion()

    async def _reconcile_ct_ingestion(self) -> None:
        """Turn CT log / CertStream ingestion on or off to match API program flags."""
        want = self._any_program_ct_monitoring_enabled
        ingest_running = (
            self._ct_ingest_task is not None and not self._ct_ingest_task.done()
        )

        if not want:
            if not self._ct_fetch_active:
                return
            await self._stop_ct_ingestion()
            return

        if self._ct_fetch_active and ingest_running:
            return

        await self._start_ct_log_ingestion()

    async def _start_ct_log_ingestion(self) -> None:
        if self._ct_ingest_task and not self._ct_ingest_task.done():
            return
        await self._stop_ct_ingestion()
        o = self._runtime_overlay
        if o["ct_start_offset"] > 0:
            logger.info(f"Starting {o['ct_start_offset']:,} entries behind for testing")
        self.poller = CTLogPoller(
            callback=self._on_certificate,
            tld_filter=self._ingestion_tld_union,
            poll_interval=o["ct_poll_interval"],
            batch_size=o["ct_batch_size"],
            max_entries_per_poll=o["ct_max_entries_per_poll"],
            start_offset=o["ct_start_offset"],
        )
        self._ct_ingest_task = asyncio.create_task(self.poller.start())
        self._ct_fetch_active = True
        logger.info("CT log polling started (≥1 program has CT monitoring enabled)")

    async def _start_certstream_ingestion(self) -> None:
        if self._ct_ingest_task and not self._ct_ingest_task.done():
            return
        await self._stop_ct_ingestion()
        self.consumer = CertStreamConsumer(
            callback=self._on_certificate,
            certstream_url=self.config.certstream_url,
            tld_filter=self._ingestion_tld_union,
            reconnect_delay=self.config.reconnect_delay,
        )
        self._ct_ingest_task = asyncio.create_task(self.consumer.start())
        self._ct_fetch_active = True
        logger.info("CertStream ingestion started (≥1 program has CT monitoring enabled)")

    async def _stop_ct_ingestion(self) -> None:
        if self.poller:
            self.poller.stop()
        if self.consumer:
            self.consumer.stop()
        if self._ct_ingest_task:
            self._ct_ingest_task.cancel()
            try:
                await self._ct_ingest_task
            except asyncio.CancelledError:
                pass
            self._ct_ingest_task = None
        self.poller = None
        self.consumer = None
        if self._ct_fetch_active:
            logger.info("CT provider ingestion stopped (no programs with CT monitoring enabled)")
        self._ct_fetch_active = False
    
    async def stop(self):
        """Stop the service gracefully"""
        if not self._running:
            return
        
        logger.info("Stopping CT Monitor Service...")
        self._running = False
        
        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop CT source
        if self.poller:
            self.poller.stop()
        if self.consumer:
            self.consumer.stop()
        
        # Disconnect from NATS
        if self.publisher:
            await self.publisher.disconnect()
        
        # Print final stats
        self._log_stats()
        
        logger.info("CT Monitor Service stopped")
    
    def is_running(self) -> bool:
        """Check if the service is currently running"""
        return self._running
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status and statistics"""
        # Get stats from either poller or consumer
        source_stats = None
        if self.poller:
            source_stats = self.poller.get_stats()
        elif self.consumer:
            source_stats = self.consumer.get_stats()
        
        stats_dict = {}
        if source_stats:
            stats_dict = source_stats.to_dict()
        
        # Include service-level stats
        stats_dict.update({
            "matches_found": self._stats.matches_found,
            "alerts_published": self._stats.alerts_published,
            "skipped_existing": self._stats.skipped_existing,
            "cache_hits": self._stats.cache_hits,
            "cache_misses": self._stats.cache_misses,
        })
        
        # Get variation generator stats
        var_count = self.variation_generator.get_variation_count()
        protected_count = self.variation_generator.get_protected_domain_count()
        var_stats = self.variation_generator.get_stats()
        
        # Get CT log states if using direct polling
        ct_logs = []
        if self.poller:
            log_states = self.poller.get_log_states()
            for url, state in log_states.items():
                ct_logs.append({
                    "name": state["name"],
                    "operator": state.get("operator", "Unknown"),
                    "tree_size": state["tree_size"],
                    "last_index": state["last_index"],
                    "errors": state["errors"],
                    "last_poll": state.get("last_poll"),
                    "connected": state["errors"] < 10  # Consider connected if < 10 errors
                })
        
        return {
            "status": "running" if self._running else "stopped",
            "ct_source": self.config.ct_source,
            "any_program_ct_monitoring_enabled": self._any_program_ct_monitoring_enabled,
            "ct_fetch_active": self._ct_fetch_active,
            "stats": stats_dict,
            "protected_domains": {
                "total": protected_count,
                "variations": var_count,
                "programs": len(self.protected_domains),
                "variation_stats": var_stats
            },
            "ct_logs": ct_logs,
            "config": {
                "runtime_overlay": dict(self._runtime_overlay),
                "ingestion_tld_union": sorted(self._ingestion_tld_union),
                "domain_refresh_interval": self._runtime_overlay["domain_refresh_interval"],
                "stats_interval": self._runtime_overlay["stats_interval"],
            },
            "programs_ct_enabled": list(self._programs_ct_enabled_detail),
        }
    
    async def _refresh_protected_domains(self):
        """Fetch protected domains from API for all programs and generate variations"""
        logger.info("Refreshing protected domains from API...")
        
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.config.api_url}/programs",
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch programs: {resp.status}")
                        return
                    
                    data = await resp.json()
                    if isinstance(data, dict):
                        programs = data.get("programs", [])
                    else:
                        programs = data
                    
                    logger.debug(f"Fetched {len(programs)} programs from API")

                loaded: List[Tuple[str, Any]] = []
                for program in programs:
                    program_name = (
                        program
                        if isinstance(program, str)
                        else program.get("name")
                        if isinstance(program, dict)
                        else str(program)
                    )
                    if not program_name:
                        continue
                    try:
                        async with session.get(
                            f"{self.config.api_url}/programs/{program_name}",
                            headers=headers,
                        ) as resp:
                            if resp.status != 200:
                                continue
                            loaded.append((program_name, await resp.json()))
                    except Exception as e:
                        logger.debug(f"Error loading program {program_name}: {e}")

                any_ct_enabled = any(
                    bool(pd.get("ct_monitoring_enabled")) for _, pd in loaded
                )

                prev_union = set(self._ingestion_tld_union)

                async with self._domain_config_lock:
                    self._any_program_ct_monitoring_enabled = any_ct_enabled
                    self.variation_generator.clear()
                    self.program_match_states.clear()
                    self.protected_domains.clear()

                    union_tlds: Set[str] = set()
                    for _, program_data in loaded:
                        if not program_data.get("ct_monitoring_enabled"):
                            continue
                        ptlds, _ = program_ct_settings.program_tlds_and_similarity(program_data)
                        union_tlds |= ptlds
                    if any_ct_enabled:
                        self._ingestion_tld_union = (
                            union_tlds if union_tlds else program_ct_settings.default_tld_set()
                        )
                    else:
                        self._ingestion_tld_union = program_ct_settings.default_tld_set()
                    logger.info(
                        "CT ingestion TLD union (%s programs enabled): %s",
                        "≥1" if any_ct_enabled else "0",
                        sorted(self._ingestion_tld_union),
                    )

                    total_domains = 0
                    total_variations = 0

                    for program_name, program_data in loaded:
                        if not program_data.get("ct_monitoring_enabled"):
                            continue

                        domains = set()
                        protected = program_data.get("protected_domains", [])
                        if protected:
                            domains.update(d.lower().strip() for d in protected if d)
                        seeds = program_data.get("seed_domains", [])
                        if seeds:
                            domains.update(d.lower().strip() for d in seeds if d)
                        settings = program_data.get("settings", {})
                        if isinstance(settings, dict):
                            root_domains = settings.get("root_domains", [])
                            if root_domains:
                                domains.update(d.lower().strip() for d in root_domains if d)

                        raw_keywords = program_data.get("protected_subdomain_prefixes") or []
                        keywords_norm: List[str] = []
                        seen_kw: Set[str] = set()
                        for k in raw_keywords:
                            if not k:
                                continue
                            k2 = str(k).lower().strip()
                            if k2 and k2 not in seen_kw:
                                seen_kw.add(k2)
                                keywords_norm.append(k2)

                        if not domains and not keywords_norm:
                            continue

                        self.protected_domains[program_name] = domains
                        if domains:
                            variations_added = self.variation_generator.add_protected_domains(
                                list(domains),
                                program_name,
                                max_variations_per_domain=5000,
                            )
                            total_variations += variations_added
                        else:
                            variations_added = 0

                        _, sim_thr = program_ct_settings.program_tlds_and_similarity(program_data)
                        protected_sorted = sorted(domains)
                        self.program_match_states[program_name] = ProgramCTMatchState(
                            keywords=keywords_norm,
                            similarity_threshold=sim_thr,
                            protected_list=protected_sorted,
                        )

                        total_domains += len(domains)
                        kw_info = f", {len(keywords_norm)} keywords" if keywords_norm else ""
                        logger.info(
                            f"  ✓ Program '{program_name}': {len(domains)} protected domains{kw_info}, "
                            f"{variations_added:,} variations generated (CT similarity={sim_thr:.2f})"
                        )

                    prog_ct_rows: List[Dict[str, Any]] = []
                    for program_name, program_data in loaded:
                        if not program_data.get("ct_monitoring_enabled"):
                            continue
                        ptlds, sim_thr = program_ct_settings.program_tlds_and_similarity(program_data)
                        prog_ct_rows.append(
                            {
                                "program_name": program_name,
                                "similarity_threshold": round(float(sim_thr), 4),
                                "tld_allowlist": sorted(ptlds),
                                "matcher_active": program_name in self.program_match_states,
                            }
                        )
                    prog_ct_rows.sort(key=lambda r: r["program_name"])
                    self._programs_ct_enabled_detail = prog_ct_rows

                    var_stats = self.variation_generator.get_stats()
                    logger.info(
                        f"Loaded {total_domains} protected domains across {len(self.program_match_states)} programs"
                    )
                    logger.info(
                        f"Generated {total_variations:,} total variations for fast O(1) matching"
                    )
                    if var_stats.get("variations_by_fuzzer"):
                        top_fuzzers = sorted(
                            var_stats["variations_by_fuzzer"].items(),
                            key=lambda x: -x[1],
                        )[:5]
                        logger.info(f"Top fuzzers: {dict(top_fuzzers)}")

                if self._ct_fetch_active and self._ingestion_tld_union != prev_union:
                    logger.info("CT ingestion TLD union changed; restarting CT provider")
                    await self._stop_ct_ingestion()
        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error refreshing protected domains: {e}")
        except Exception as e:
            logger.error(f"Error refreshing protected domains: {e}")

    async def refresh_domains_now(self) -> None:
        """Reload program CT config from API while the service is running."""
        if not self._running:
            raise RuntimeError("CT monitor service is not running")
        await self._refresh_protected_domains()
    
    async def _domain_refresh_loop(self):
        """Periodically refresh protected domains from API"""
        while self._running:
            try:
                await self._fetch_runtime_settings_from_api()
                interval = max(1, int(self._runtime_overlay["domain_refresh_interval"]))
                await asyncio.sleep(interval)
                if self._running:
                    await self._refresh_protected_domains()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in domain refresh loop: {e}")
    
    @staticmethod
    def _cert_metadata_details(cert_info: CertificateInfo) -> Dict[str, Any]:
        return {
            "cert_issuer": cert_info.issuer,
            "cert_fingerprint": cert_info.fingerprint,
            "cert_not_before": cert_info.not_before,
            "cert_seen_at": cert_info.seen_at,
            "cert_all_domains": cert_info.domains,
        }

    def _match_keyword_or_similarity(
        self,
        domain_lower: str,
        state: ProgramCTMatchState,
        cert_info: CertificateInfo,
    ) -> Optional[MatchResult]:
        base_details = dict(self._cert_metadata_details(cert_info))
        base_details["match_source"] = "keyword_or_similarity"

        for keyword in state.keywords:
            if keyword in domain_lower:
                d = dict(base_details)
                d["matched_keyword"] = keyword
                return MatchResult(
                    matched=True,
                    protected_domain=keyword,
                    cert_domain=domain_lower,
                    similarity_score=0.90,
                    match_type="keyword",
                    details=d,
                )

        if state.protected_list:
            best_s, best_p = best_match_among_protected(domain_lower, state.protected_list)
            if best_s >= state.similarity_threshold and best_p is not None:
                d = dict(base_details)
                d["similarity_threshold"] = state.similarity_threshold
                return MatchResult(
                    matched=True,
                    protected_domain=best_p,
                    cert_domain=domain_lower,
                    similarity_score=best_s,
                    match_type="protected_similarity",
                    details=d,
                )

        return None

    async def _on_certificate(self, cert_info: CertificateInfo):
        """
        Handle incoming certificate from CertStream/CT logs.

        Per SAN: (1) exact dnstwist variation, (2) else keyword then API-aligned similarity per program.

        Called for each certificate that passes TLD filtering.
        """
        pending: List[Tuple[MatchResult, str]] = []

        async with self._domain_config_lock:
            alerted_domains = set()

            for domain in cert_info.domains:
                domain_lower = domain.lower().strip()

                if domain_lower in alerted_domains:
                    continue

                if self.variation_generator.is_legitimate_subdomain(domain_lower):
                    continue

                if self.variation_generator.is_protected_domain(domain_lower):
                    continue

                variation_info = self.variation_generator.match(domain_lower)

                if variation_info:
                    alerted_domains.add(domain_lower)
                    self._stats.matches_found += 1

                    match = MatchResult(
                        matched=True,
                        protected_domain=variation_info.protected_domain,
                        cert_domain=domain_lower,
                        similarity_score=0.95,
                        match_type=f"dnstwist:{variation_info.fuzzer}",
                        details={
                            "fuzzer": variation_info.fuzzer,
                            **self._cert_metadata_details(cert_info),
                            "match_source": "variation_generator",
                        },
                    )

                    logger.warning(
                        f"🚨 CT ALERT: {match.cert_domain} matches variation of {match.protected_domain} "
                        f"(program={variation_info.program_name}, fuzzer={variation_info.fuzzer})"
                    )

                    pending.append((match, variation_info.program_name))

            for domain in cert_info.domains:
                domain_lower = domain.lower().strip()

                if domain_lower in alerted_domains:
                    continue

                if self.variation_generator.is_legitimate_subdomain(domain_lower):
                    continue

                if self.variation_generator.is_protected_domain(domain_lower):
                    continue

                for program_name, state in list(self.program_match_states.items()):
                    if domain_lower in alerted_domains:
                        continue
                    try:
                        match = self._match_keyword_or_similarity(domain_lower, state, cert_info)
                        if match:
                            alerted_domains.add(domain_lower)
                            self._stats.matches_found += 1
                            logger.warning(
                                f"🚨 CT ALERT: {match.cert_domain} looks like {match.protected_domain} "
                                f"(program={program_name}, type={match.match_type}, "
                                f"score={match.similarity_score:.2f})"
                            )
                            pending.append((match, program_name))
                    except Exception as e:
                        logger.error(f"Error processing certificate for program {program_name}: {e}")
                        self._stats.errors += 1

        for match, program_name in pending:
            await self._publish_alert(match, cert_info, program_name)
    
    async def _check_typosquat_domain_exists(self, domain: str, program_name: str) -> bool:
        """
        Check if a typosquat domain already exists in the database.
        
        Uses Redis cache to avoid redundant API calls. Cache strategy:
        - Existing domains: cached for 24 hours (they rarely change)
        - Non-existing domains: cached for 5 minutes (to catch newly added domains faster)
        
        Args:
            domain: The typosquat domain to check (will be lowercased)
            program_name: The program name to filter by
            
        Returns:
            True if domain exists, False otherwise
        """
        domain_lower = domain.lower().strip()
        cache_key = f"ct_monitor:typosquat_exists:{program_name}:{domain_lower}"
        
        # Check Redis cache first
        if self.redis_client:
            try:
                cached_value = self.redis_client.get(cache_key)
                if cached_value is not None:
                    self._stats.cache_hits += 1
                    exists = cached_value == "1"
                    logger.debug(f"Cache hit for {domain_lower}: exists={exists}")
                    return exists
            except Exception as e:
                logger.warning(f"Redis cache read error for {cache_key}: {e}")
        
        # Cache miss - need to check API
        self._stats.cache_misses += 1
        logger.debug(f"Cache miss for {domain_lower}, checking API...")
        
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Search for exact match
                search_body = {
                    "exact_match": domain_lower,
                    "program": program_name,
                    "page": 1,
                    "page_size": 1
                }
                
                async with session.post(
                    f"{self.config.api_url}/findings/typosquat/search",
                    json=search_body,
                    headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to check typosquat domain existence: {resp.status}")
                        # Fail-open: return False to allow alert publishing
                        return False
                    
                    data = await resp.json()
                    items = data.get("items", [])
                    exists = len(items) > 0
                    
                    # Cache the result
                    if self.redis_client:
                        try:
                            ttl = self.config.cache_ttl_exists if exists else self.config.cache_ttl_not_exists
                            cache_value = "1" if exists else "0"
                            self.redis_client.setex(cache_key, ttl, cache_value)
                            logger.debug(f"Cached {domain_lower}: exists={exists}, TTL={ttl}s")
                        except Exception as e:
                            logger.warning(f"Redis cache write error for {cache_key}: {e}")
                    
                    return exists
                    
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error checking typosquat domain existence: {e}")
            # Fail-open: return False to allow alert publishing
            return False
        except Exception as e:
            logger.error(f"Error checking typosquat domain existence: {e}")
            # Fail-open: return False to allow alert publishing
            return False
    
    async def _publish_alert(self, match: MatchResult, cert_info: CertificateInfo, program_name: str):
        """Helper to publish an alert and update stats"""
        # Check if domain already exists before publishing
        domain_exists = await self._check_typosquat_domain_exists(match.cert_domain, program_name)
        
        if domain_exists:
            logger.debug(
                f"⏭️  Skipping alert for {match.cert_domain} - domain already exists in database "
                f"(program={program_name})"
            )
            self._stats.skipped_existing += 1
            return
        
        logger.info(
            f"   Certificate: issuer={cert_info.issuer}, "
            f"domains={len(cert_info.domains)}, "
            f"fingerprint={cert_info.fingerprint[:16] if cert_info.fingerprint else 'N/A'}..."
        )
        
        if self.publisher:
            success = await self.publisher.publish_alert(
                match_result=match,
                cert_info=cert_info,
                program_name=program_name
            )
            if success:
                self._stats.alerts_published += 1
    
    async def _stats_reporter(self):
        """Periodically report processing statistics"""
        while self._running:
            try:
                interval = max(1, int(self._runtime_overlay["stats_interval"]))
                await asyncio.sleep(interval)
                if self._running:
                    self._log_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stats reporter: {e}")
    
    def _log_stats(self):
        """Log current processing statistics"""
        # Get stats from either poller or consumer
        source_stats = None
        if self.poller:
            source_stats = self.poller.get_stats()
        elif self.consumer:
            source_stats = self.consumer.get_stats()
        
        if source_stats:
            stats_dict = source_stats.to_dict()
            
            # Include variation generator stats
            var_count = self.variation_generator.get_variation_count()
            protected_count = self.variation_generator.get_protected_domain_count()
            
            logger.info(
                f"📊 CT Stats: "
                f"received={stats_dict['total_received']:,}, "
                f"processed={stats_dict['processed']:,}, "
                f"filtered={stats_dict['filtered_by_tld']:,}, "
                f"matches={self._stats.matches_found}, "
                f"alerts={self._stats.alerts_published}, "
                f"skipped={self._stats.skipped_existing}, "
                f"cache_hits={self._stats.cache_hits}, "
                f"cache_misses={self._stats.cache_misses}, "
                f"errors={stats_dict['errors']}, "
                f"rate={stats_dict['certs_per_second']:.1f}/s, "
                f"variations={var_count:,} (from {protected_count} domains)"
            )
            
            # Log CT log states if using direct polling
            if self.poller:
                log_states = self.poller.get_log_states()
                for url, state in log_states.items():
                    logger.debug(
                        f"  📜 {state['name']}: "
                        f"tree_size={state['tree_size']:,}, "
                        f"last_index={state['last_index']:,}, "
                        f"errors={state['errors']}"
                    )


# Global service instance
_service_instance: Optional[CTMonitorService] = None

def get_service() -> CTMonitorService:
    """Get or create the global service instance"""
    global _service_instance
    if _service_instance is None:
        _service_instance = CTMonitorService()
    return _service_instance


async def _auto_start_ct_monitor_if_needed() -> None:
    """Wait for API readiness, then start monitoring (always on when auto-start enabled)."""
    service = get_service()
    cfg = service.config
    if not cfg.ct_monitor_auto_start:
        logger.info("CT_MONITOR_AUTO_START disabled; monitoring idle until POST /start")
        return
    headers = {}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    url = f"{cfg.api_url.rstrip('/')}/programs/ct-monitoring/any-enabled"
    max_attempts = 30
    delay_sec = 2.0
    for attempt in range(max_attempts):
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 403:
                        logger.warning(
                            "CT auto-start: API returned 403 for any-enabled (check INTERNAL_SERVICE_API_KEY)"
                        )
                        return
                    if resp.status != 200:
                        logger.warning(
                            "CT auto-start: any-enabled HTTP %s (attempt %s/%s)",
                            resp.status,
                            attempt + 1,
                            max_attempts,
                        )
                        await asyncio.sleep(delay_sec)
                        continue
                    try:
                        await service.start()
                    except Exception as e:
                        logger.error("CT auto-start: service.start failed: %s", e)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "CT auto-start: API not ready (%s), retry %s/%s",
                e,
                attempt + 1,
                max_attempts,
            )
            await asyncio.sleep(delay_sec)
    logger.error("CT auto-start: exhausted retries waiting for API")


@asynccontextmanager
async def _http_app_lifespan(app: FastAPI):
    task = asyncio.create_task(_auto_start_ct_monitor_if_needed())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        svc = get_service()
        if svc.is_running():
            await svc.stop()


# Create FastAPI app for HTTP endpoints
http_app = FastAPI(
    title="CT Monitor Control API",
    version="1.0.0",
    lifespan=_http_app_lifespan,
)

@http_app.get("/status")
async def get_status():
    """Get current status and statistics"""
    service = get_service()
    return JSONResponse(content=service.get_status())

@http_app.post("/start")
async def start_monitoring():
    """Start the CT monitoring service"""
    service = get_service()
    if service.is_running():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Service is already running"}
        )
    
    try:
        await service.start()
        return JSONResponse(content={
            "status": "success",
            "message": "CT monitoring started"
        })
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@http_app.post("/refresh-domains")
async def refresh_domains():
    """Reload program CT config from the API (running service only)."""
    service = get_service()
    if not service.is_running():
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service is not running"},
        )
    try:
        await service.refresh_domains_now()
        return JSONResponse(
            content={"status": "success", "message": "Protected domains reloaded from API"}
        )
    except Exception as e:
        logger.error(f"Error refreshing domains: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@http_app.post("/reload-runtime-settings")
async def reload_runtime_settings():
    """Reload global CT runtime from API (intervals / poll sizing); may restart CT ingestion."""
    service = get_service()
    if not service.is_running():
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service is not running"},
        )
    try:
        await service.reload_runtime_settings_now()
        return JSONResponse(
            content={
                "status": "success",
                "message": "Runtime settings reloaded from API",
                "runtime_overlay": dict(service._runtime_overlay),
            }
        )
    except Exception as e:
        logger.error(f"Error reloading runtime settings: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@http_app.post("/stop")
async def stop_monitoring():
    """Stop the CT monitoring service"""
    service = get_service()
    if not service.is_running():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Service is not running"}
        )
    
    try:
        await service.stop()
        return JSONResponse(content={
            "status": "success",
            "message": "CT monitoring stopped"
        })
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@http_app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(content={"status": "healthy"})


async def run_http_server(service: CTMonitorService):
    """Run the HTTP server"""
    config = service.config
    logger.info(f"Starting HTTP server on {config.http_host}:{config.http_port}")
    
    # Store service instance for HTTP endpoints
    global _service_instance
    _service_instance = service
    
    # Create server config
    server_config = uvicorn.Config(
        app=http_app,
        host=config.http_host,
        port=config.http_port,
        log_level=config.log_level.lower(),
        access_log=False
    )
    server = uvicorn.Server(server_config)
    await server.serve()


async def main():
    """Main entry point"""
    service = get_service()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(service.stop())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        # HTTP server + lifespan auto-start (see CT_MONITOR_AUTO_START)
        await run_http_server(service)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await service.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await service.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

