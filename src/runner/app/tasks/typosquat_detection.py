"""
Refactored TyposquatDetection task following Single Responsibility Principle

This version breaks down the monolithic class into focused components and demonstrates
the architectural improvements.
"""

import logging
from typing import Dict, List, Any, Optional
import json
import base64
import os
import asyncio

from .base import Task, FindingType, AssetType
from utils import normalize_url_for_storage
from .typosquat_components import (
    VariationGenerator,
    VariationCacheManager,
    TyposquatAnalyzer,
    SubdomainWorkflowOrchestrator,
    ScreenshotProcessor,
    ApiClient
)

logger = logging.getLogger(__name__)


class TyposquatDetection(Task):
    """
    Refactored typosquat detection task with component-based architecture
    
    This class now focuses on:
    - Task orchestration and coordination
    - Input/output handling 
    - Component lifecycle management
    - Workflow state management
    
    Heavy lifting is delegated to specialized components.
    """
    
    name = "typosquat_detection"
    description = "Detect typosquatting domains using dnstwist and risk analysis. Supports both variation generation and direct input domain analysis modes."
    input_type = AssetType.SUBDOMAIN
    output_types = []  # We return findings directly to API, not as asset types
    chunk_size = 20  # Default chunk size for domain variations

    def __init__(self):
        super().__init__()

        # Initialize cache manager first (it has Redis client)
        self.variation_cache = VariationCacheManager()

        # Initialize variation generator with Redis client for offset tracking
        self.variation_generator = VariationGenerator(
            redis_client=self.variation_cache.redis_client if self.variation_cache.cache_enabled else None
        )

        # Initialize other components
        self.screenshot_processor = ScreenshotProcessor()
        self.workflow_orchestrator = SubdomainWorkflowOrchestrator()
        self.typosquat_analyzer = TyposquatAnalyzer()
        self.api_client = None
        
        # Task management state
        self.spawned_job_names = []
        self.spawned_task_ids = []
        self.spawned_task_outputs = {}
        self.task_queue_client = None
        self.program_name = os.getenv('PROGRAM_NAME', 'default')
        self.has_spawned_screenshot_jobs = False
        
        # Set up component integration
        self._integrate_components()
    
    def _integrate_components(self):
        """Set up shared state and cross-component communication"""
        # Share task tracking state with workflow orchestrator
        self.phase2_task_ids = self.workflow_orchestrator.phase2_task_ids
        self.phase3_task_ids = self.workflow_orchestrator.phase3_task_ids
        self.apex_to_original_mapping = self.workflow_orchestrator.apex_to_original_mapping
    
    def _ensure_api_client(self):
        """Ensure API client is initialized"""
        if self.api_client is None:
            api_url = os.getenv('API_URL', 'http://api:8000')
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
            self.api_client = ApiClient(api_url, internal_api_key)
        return self.api_client

    def prepare_input_data(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[Any]:
        """
        Prepare input data by generating and filtering variations before chunking
        
        This method handles:
        1. Domain variation generation (standard mode)
        2. Input domain analysis mode setup
        3. Deduplication against already-tested domains
        4. Chunking preparation
        """
        # Handle both single domain and list of domains
        domains_to_process = input_data if isinstance(input_data, list) else [input_data]
        
        # Check if this is already a subdomain discovery task
        if isinstance(domains_to_process, list) and len(domains_to_process) > 0:
            first_item = domains_to_process[0]
            if isinstance(first_item, dict) and first_item.get("_is_subdomain_discovery"):
                logger.info("Detected subdomain discovery mode in prepare_input_data - passing through")
                return domains_to_process
        
        # Extract parameters
        max_variations = params.get("max_variations", 100) if params else 100
        fuzzers = params.get("fuzzers", []) if params else []
        exclude_tested = params.get("exclude_tested", True) if params else True
        include_subdomains = params.get("include_subdomains", False) if params else False
        analyze_input_as_variations = params.get("analyze_input_as_variations", False) if params else False
        
        logger.info(f"Preparing variations for domains: {domains_to_process}")
        logger.info(f"Parameters: max_variations={max_variations}, exclude_tested={exclude_tested}, include_subdomains={include_subdomains}, analyze_input_as_variations={analyze_input_as_variations}")
        
        # Handle input analysis mode
        if analyze_input_as_variations:
            return self._prepare_input_analysis_mode(domains_to_process, include_subdomains)
        
        # Standard variation generation mode
        return self._prepare_standard_mode(domains_to_process, max_variations, fuzzers, exclude_tested, include_subdomains)
    
    def _prepare_input_analysis_mode(self, domains: List[str], include_subdomains: bool) -> List[Dict]:
        """Prepare input domains for direct analysis as typosquat variations"""
        logger.info("🔍 ANALYZE INPUT AS VARIATIONS MODE ENABLED 🔍")
        logger.info("Input domains will be treated as typosquat variations for analysis")
        
        all_variations = []
        for domain in domains:
            if not domain or not isinstance(domain, str):
                logger.error(f"Invalid domain format: {domain}")
                continue
            
            # Treat input domain as a variation with "input_domain" fuzzer type
            variation = {
                "domain": domain,
                "fuzzers": ["input_domain"],
                "_is_input_domain_analysis": True
            }
            
            if include_subdomains:
                variation["_subdomain_discovery_enabled"] = True
                
            all_variations.append(variation)
            logger.info(f"Added input domain '{domain}' as typosquat variation for analysis")
        
        logger.info(f"Total input domains prepared for analysis: {len(all_variations)}")
        
        if include_subdomains:
            logger.info("Subdomain discovery enabled - Phase 2 will be triggered after Phase 1 completes")
        
        return all_variations
    
    def _prepare_standard_mode(self, domains: List[str], max_variations: int, fuzzers: List[str], 
                             exclude_tested: bool, include_subdomains: bool) -> List[Dict]:
        """Prepare domains using standard variation generation"""
        logger.info("Using standard variation generation mode")
        
        all_variations = []
        
        # Get already tested domains if exclusion is enabled
        already_tested = set()
        if exclude_tested:
            try:
                api_client = self._ensure_api_client()
                for domain in domains:
                    tested_for_domain = api_client.get_already_tested_domains(
                        program_name=self.program_name
                    )
                    already_tested.update(tested_for_domain)
                logger.info(f"Found {len(already_tested)} already tested domains to exclude")
            except Exception as e:
                logger.warning(f"Could not retrieve already tested domains: {e}")
                already_tested = set()
        
        # Generate variations for each domain
        exhausted_domains = []
        for domain in domains:

            if not domain or not isinstance(domain, str):
                logger.error(f"Invalid domain format: {domain}")
                continue
            logger.info(f"Generating variations for domain: {domain}")
            # Generate variations with deduplication retry logic
            domain_variations = self._generate_variations_with_retry(
                domain, max_variations, fuzzers, already_tested, exclude_tested
            )

            # Track exhausted domains
            if not domain_variations:
                exhausted_domains.append(domain)
                logger.warning(f"⚠️ Skipping {domain} - no untested variations available")
                continue

            # Convert to variation format
            for variation_domain, fuzzer_types in domain_variations.items():
                variation = {
                    "domain": variation_domain,
                    "fuzzers": fuzzer_types
                }

                if include_subdomains:
                    variation["_subdomain_discovery_enabled"] = True

                all_variations.append(variation)

        # Summary logging
        logger.info(f"Total variations prepared for chunking: {len(all_variations)}")
        if exhausted_domains:
            logger.error(f"🚫 {len(exhausted_domains)} EXHAUSTED DOMAINS (no untested variations): {exhausted_domains}")
            logger.error("🚫 These domains should be excluded from future runs until cache TTL expires")
        
        if include_subdomains:
            logger.info("Subdomain discovery enabled - Phase 2 will be triggered after Phase 1 completes")
        
        return all_variations
    
    def _generate_variations_with_retry(self, domain: str, max_variations: int, fuzzers: List[str],
                                      already_tested: set, exclude_tested: bool) -> Dict[str, List[str]]:
        """Generate variations with retry logic for deduplication using Redis cache and API"""
        current_max_variations = max_variations
        domain_to_fuzzers = {}
        attempt = 0
        max_attempts = 5
        logger.debug(f"Generating variations with retry logic for {domain}")

        # Track total variations generated to detect exhaustion
        total_variations_generated = 0
        all_variations_exhausted = False

        while len(domain_to_fuzzers) == 0 and attempt < max_attempts:
            attempt += 1
            logger.info(f"Attempt {attempt}/{max_attempts}: Generating up to {current_max_variations} variations for {domain}")
            logger.debug(f"Fuzzers: {fuzzers}")
            logger.debug(f"API already tested: {len(already_tested)}")
            logger.debug(f"Exclude tested: {exclude_tested}")

            # Generate variations using component (with offset-based rotation)
            all_domain_variations = self.variation_generator.generate_variations_with_fuzzers(
                domain, current_max_variations, fuzzers=fuzzers, program_name=self.program_name
            )

            generated_count = len(all_domain_variations)
            logger.info(f"Generated {generated_count} variations for {domain} before filtering")

            # Track if we're hitting the generation ceiling
            if generated_count == total_variations_generated and attempt > 1:
                logger.warning(f"⚠️ DOMAIN EXHAUSTED: dnstwist generated same {generated_count} variations again for {domain}")
                logger.warning("⚠️ No new variations possible - domain variation space fully explored")
                all_variations_exhausted = True

            total_variations_generated = generated_count

            # Apply filtering if exclusion is enabled
            if exclude_tested:
                redis_filtered = 0
                api_filtered = 0

                # Step 1: Filter using Redis cache (fast, recent tests within TTL)
                if self.variation_cache.cache_enabled:
                    before_redis = len(all_domain_variations)
                    logger.debug(f"Filtering with Redis cache for {domain}")
                    all_domain_variations = self.variation_cache.filter_untested_variations(
                        all_domain_variations, self.program_name
                    )
                    redis_filtered = before_redis - len(all_domain_variations)
                    logger.debug(f"After Redis cache filter: {len(all_domain_variations)} variations remain")

                # Step 2: Filter using API data (comprehensive, all historical tests)
                if already_tested:
                    before_api = len(all_domain_variations)
                    all_domain_variations = {d: f for d, f in all_domain_variations.items() if d not in already_tested}
                    api_filtered = before_api - len(all_domain_variations)
                    if api_filtered > 0:
                        logger.info(f"API filter: Excluded {api_filtered} already tested domains for {domain}")

                domain_to_fuzzers = all_domain_variations

                # If we filtered out all variations, check if we should retry
                if len(domain_to_fuzzers) == 0:
                    if all_variations_exhausted:
                        logger.error(f"🚫 FULLY EXHAUSTED: All {total_variations_generated} possible variations for {domain} have been tested")
                        logger.error(f"🚫 Redis cache filtered: {redis_filtered}, API filtered: {api_filtered}")
                        logger.error(f"🚫 Skipping {domain} - no new variations available until cache expires (TTL: 30 days)")
                        break

                    if attempt < max_attempts:
                        current_max_variations = min(current_max_variations * 2, 1000)
                        logger.info(f"All variations already tested, increasing limit to {current_max_variations} for next attempt")
                        continue
            else:
                domain_to_fuzzers = all_domain_variations

            # Break if we have variations or if we're not excluding tested domains
            if len(domain_to_fuzzers) > 0 or not exclude_tested:
                break

        variations = list(domain_to_fuzzers.keys())

        # Enhanced final logging
        if variations:
            logger.info(f"✅ SUCCESS: Found {len(variations)} untested variations for {domain} after {attempt} attempts")
            logger.info(f"Sample variations: {variations[:5]}")
        else:
            if all_variations_exhausted:
                logger.error(f"❌ EXHAUSTED: Domain {domain} has NO untested variations remaining (all {total_variations_generated} tested)")
                logger.error("❌ This domain should be skipped in future runs until cache TTL expires")
            else:
                logger.warning(f"⚠️ NO VARIATIONS: Could not find untested variations for {domain} after {attempt} attempts")

        return domain_to_fuzzers

    def get_timeout(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> int:
        """Calculate timeout based on chunk size and task parameters"""
        chunk_size = len(input_data) if isinstance(input_data, list) else 1

        # Use API parameter timeout if available, otherwise calculate based on input size
        api_timeout = None
        if params and isinstance(params, dict):
            api_timeout = params.get('timeout')

        if api_timeout and isinstance(api_timeout, int) and api_timeout > 0:
            # Use the API parameter, but ensure it's reasonable for the input size
            # For large inputs, we might need more time than the API default
            calculated_timeout = min(1800, 60 * chunk_size)  # 1 minute per domain, max 30 minutes
            return max(api_timeout, calculated_timeout)
        else:
            # Fall back to calculated timeout
            return min(1800, 60 * chunk_size)  # 1 minute per domain, max 30 minutes

    def get_last_execution_threshold(self) -> int:
        """Re-run typosquat detection weekly"""
        return 0  # 7 days * 24 hours

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate timestamp hash for caching"""
        hash_dict = {
            "task": self.name,
            "target": target,
            "params": params
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()

    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """
        Generate typosquat detection command

        This method focuses on command generation while delegating
        the heavy lifting to helper methods.
        """
        # Check if this is a recalculate risk score operation
        recalculate_risk = params.get("recalculate_risk", False) if params else False

        if recalculate_risk:
            logger.info("Recalculating risk scores for stored typosquat domains")
            return self._handle_risk_recalculation(input_data, params)

        # Check analyze_input_as_variations parameter
        analyze_input_as_variations = params.get("analyze_input_as_variations", False) if params else False

        # Process input data based on mode
        if analyze_input_as_variations:
            # Input analysis mode: treat input domains as variations
            logger.info("🔍 ANALYZE INPUT AS VARIATIONS MODE ENABLED 🔍")
            logger.info("Input domains will be treated as typosquat variations for analysis")
            variations_to_process = input_data if isinstance(input_data, list) else [input_data]
            all_variations = self._ensure_variation_format_for_input_analysis(variations_to_process, params)
        else:
            # Standard mode: generate variations from input domains
            logger.info("Using standard variation generation mode")
            # Use prepare_input_data to generate actual variations
            prepared_input = self.prepare_input_data(input_data, params)
            variations_to_process = prepared_input if isinstance(prepared_input, list) else [prepared_input]
            all_variations = self._ensure_variation_format(variations_to_process, params)

        logger.info(f"Processing {len(all_variations)} domain variations in this chunk")

        if not all_variations:
            logger.error("🚫 NO VARIATIONS TO TEST - All domains exhausted or filtered")
            logger.error("🚫 Possible reasons:")
            logger.error("   1. All variations have been tested (cached in Redis)")
            logger.error("   2. All variations already exist in API (already tested)")
            logger.error("   3. Domain variation space fully explored")
            logger.error("🚫 Returning empty command - task will be skipped")
            return []

        # --- Pre-flight filtering: ask the API which domains pass filtering ---
        # Cache ALL variations (including filtered) so they aren't re-generated
        self.current_tested_variations = list(all_variations)

        include_subdomains = params.get("include_subdomains", False) if params else False
        if not include_subdomains:
            try:
                api_client = self._ensure_api_client()
                unique_domains = list({v.get("domain") for v in all_variations if v.get("domain")})
                if unique_domains:
                    filter_result = api_client.check_domain_filtering(unique_domains, self.program_name)
                    filtered_set = set(filter_result.get("filtered", []))
                    if filtered_set:
                        before_count = len(all_variations)
                        all_variations = [v for v in all_variations if v.get("domain") not in filtered_set]
                        logger.info(
                            f"Pre-flight filter removed {before_count - len(all_variations)} variations "
                            f"({len(filtered_set)} domains filtered), {len(all_variations)} remaining"
                        )
                        if not all_variations:
                            logger.info("All variations filtered out by pre-flight check - skipping worker")
                            return []
            except Exception as e:
                logger.warning(f"Pre-flight filter check failed ({e}), proceeding with all variations")
        else:
            logger.info("include_subdomains=true: bypassing pre-flight check (subdomains may match program filtering)")

        # Build worker command
        max_workers = params.get("max_workers", 5) if params else 5
        active_checks = params.get("active_checks", True) if params else True
        geoip_checks = params.get("geoip_checks", True) if params else True
        
        commands = self._build_worker_command_with_stdin(
            all_variations, active_checks, geoip_checks, max_workers
        )
        final_commands = []
        for command in commands:
        # Add subdomain discovery marker if needed
            subdomain_discovery_enabled = any(
            variation.get("_subdomain_discovery_enabled", False) 
            for variation in all_variations
            )
            
            if subdomain_discovery_enabled:
                command += " --subdomain-discovery-enabled"
            final_commands.append(command)
        
        return final_commands
    
    def _ensure_variation_format_for_input_analysis(self, variations_to_process: List[Any], params: Optional[Dict[Any, Any]]) -> List[Dict]:
        """Ensure input is in proper variation format for input analysis mode"""
        all_variations = []
        include_subdomains = params.get("include_subdomains", False) if params else False

        for item in variations_to_process:
            if isinstance(item, dict):
                # Already in variation format; ensure subdomain discovery flag if needed
                variation = dict(item)
                if include_subdomains:
                    variation["_subdomain_discovery_enabled"] = True
                all_variations.append(variation)
            else:
                # Plain domain string - convert to variation format for analysis
                variation = {
                    "domain": item,
                    "fuzzers": ["input_domain"],
                    "_is_input_domain_analysis": True
                }
                if include_subdomains:
                    variation["_subdomain_discovery_enabled"] = True
                all_variations.append(variation)

        return all_variations

    def _ensure_variation_format(self, variations_to_process: List[Any], params: Optional[Dict[Any, Any]]) -> List[Dict]:
        """Ensure input is in proper variation format for standard mode"""
        all_variations = []

        for item in variations_to_process:
            if isinstance(item, dict):
                # Already in variation format
                all_variations.append(item)
            else:
                # Plain domain string - convert to variation format
                all_variations.append({
                    "domain": item,
                    "fuzzers": ["original"]
                })

        return all_variations
    
    def _build_worker_command_with_stdin(self, variations: List[Dict], active_checks: bool,
                                       geoip_checks: bool, max_workers: int) -> str:
        """Build worker command that receives variations via stdin"""
        logger.debug(f"Variation count: {len(variations)}")
        # Split into multiple chunks
        variations_chunks = []
        for i in range(0, len(variations), 50):
            variations_chunks.append(variations[i:i+50])
        logger.debug(f"Variation chunks count: {len(variations_chunks)}")
        # Convert variations to JSON string for stdin
        commands = []
        for variations_chunk in variations_chunks:
            variations_json = json.dumps(variations_chunk)
            encoded_json = base64.b64encode(variations_json.encode('utf-8')).decode('utf-8')
            command_parts = [
                f"echo '{encoded_json}' | base64 -d",
                "|",
                "python3 typosquat_worker.py",
                "--variations-stdin",
                f"--workers {max_workers}",
                "--output-json",
                "--no-store"
            ]
            if active_checks:
                command_parts.append("--active")

            if geoip_checks:
                command_parts.append("--geoip")
            command = " ".join(command_parts)
            logger.debug(f"command: {command}")
            commands.append(command)
        logger.debug(f"commands: {commands}")
        # Use base64 encoding to safely pass JSON data through shell
        return commands

        # command_parts = [
        #     f"echo '{encoded_json}' | base64 -d",
        #     "|",
        #     "python3 typosquat_worker.py",
        #     "--variations-stdin",
        #     f"--workers {max_workers}",
        #     "--output-json",
        #     "--no-store"
        # ]

        # if active_checks:
        #     command_parts.append("--active")

        # if geoip_checks:
        #     command_parts.append("--geoip")

        # command = " ".join(command_parts)
        # return f"{command} 2>&1"  # Redirect stderr to stdout
    
    def _handle_risk_recalculation(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Handle risk recalculation for stored typosquat domains"""
        logger.warning("Risk recalculation not fully implemented")
        return "echo 'Risk recalculation completed'"

    def parse_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> Dict[str, Any]:
        """
        Parse typosquat detection JSON output into TyposquatDomain findings
        
        This method now delegates the heavy parsing to the analyzer component
        and focuses on orchestrating the workflow phases.
        """
        # Use the analyzer component for parsing
        result, subdomain_discovery_enabled, findings, subdomains_for_phase3 = self.typosquat_analyzer.parse_worker_output(output, params)
        
        # Get program name for screenshot and subdomain triggering
        program_name = os.getenv('PROGRAM_NAME', '')
        
        # Extract typosquat URLs from result for screenshot processing
        typosquat_urls = result.get(FindingType.TYPOSQUAT_URL, [])
        
        # Trigger screenshot jobs if needed
        if typosquat_urls and not getattr(self, 'has_spawned_screenshot_jobs', False):
           logger.info(f"Triggering screenshot jobs for {len(typosquat_urls)} typosquat URLs")
           asyncio.create_task(self._trigger_screenshot_jobs_for_typosquat_urls_async(typosquat_urls, program_name))
        
        # Handle subdomain discovery: trigger Phase 3 directly with subdomains from worker output
        if subdomain_discovery_enabled and subdomains_for_phase3:
            logger.info("🚀 PHASE 2/3: SUBDOMAIN ANALYSIS TRIGGERED 🚀")
            logger.info(f"📋 Starting workflow to analyze {len(subdomains_for_phase3)} subdomains from worker")
            asyncio.create_task(
                self.workflow_orchestrator.start_phase3_workflow_async(subdomains_for_phase3, program_name)
            )
        elif subdomain_discovery_enabled and not subdomains_for_phase3:
            logger.info("⚠️ Phase 2: Subdomain discovery enabled but no subdomains found - skipping Phase 3")
        else:
            # Simple logging when subdomain discovery is disabled
            if findings:
                logger.info(f"✅ Phase 1 complete: Processed {len(findings)} typosquat findings")
            else:
                logger.info("ℹ️ Phase 1 complete: No typosquat findings detected")

        # Handle fuzzing trigger (Phase 4 - optional)
        if findings:
            logger.info("🔍 Checking if fuzzing should be triggered for typosquat domains...")
            self._trigger_fuzzing_for_typosquat_domains(findings, params)
        
        # Log information about input domain analysis mode if enabled
        analyze_input_as_variations = params.get("analyze_input_as_variations", False) if params else False
        if analyze_input_as_variations:
            logger.info("🔍 INPUT DOMAIN ANALYSIS MODE: Input domains were analyzed as typosquat variations")
            logger.info(f"📊 Found {len(findings)} findings from input domain analysis")
            if findings:
                input_domains = [f.typo_domain for f in findings if f.typo_domain]
                logger.info(f"🎯 Input domains analyzed: {input_domains}")
        
        # Store typosquat URLs for later processing
        if typosquat_urls:
            self.pending_typosquat_urls = typosquat_urls
            logger.info(f"📋 Stored {len(typosquat_urls)} URLs for later processing (screenshots handled separately)")

        # Update Redis cache with ALL tested variations (not just registered ones)
        if self.variation_cache.cache_enabled and hasattr(self, 'current_tested_variations'):
            variations_to_cache = self.current_tested_variations
            if variations_to_cache:
                logger.info(f"🔄 Updating Redis cache with {len(variations_to_cache)} tested variations (registered and unregistered)")

                cached_count = 0
                for variation_entry in variations_to_cache:
                    variation_domain = variation_entry.get('domain')

                    if variation_domain:
                        success = self.variation_cache.mark_variation_as_tested(
                            variation_domain=variation_domain,
                            program_name=program_name
                        )
                        if success:
                            cached_count += 1

                logger.info(f"✅ Redis cache updated with {cached_count}/{len(variations_to_cache)} tested variations")

                # Don't clear here - other jobs from the same chunk may need it for subdomain discovery.
                # It gets overwritten on the next get_command (next input chunk).
                # Re-caching the same variations is idempotent for Redis.

        logger.info(f"✅ Returning {len(result.get(FindingType.TYPOSQUAT_DOMAIN, []))} typosquat domain findings")

        return result
    
    async def _trigger_screenshot_jobs_for_typosquat_urls_async(self, typosquat_urls: List[Dict[str, Any]], program_name: str):
        """Trigger screenshot jobs for typosquat URLs using the generic spawning capability"""
        try:
            # Extract and normalize URLs for screenshots (normalization ensures gowitness
            # produces consistent filenames we can decode for correct screenshot-to-URL mapping)
            urls_for_screenshots = []
            for url_data in typosquat_urls:
                url = url_data.get('url', '')
                if url and url.startswith(('http://', 'https://')):
                    normalized = normalize_url_for_storage(url)
                    if normalized and normalized not in urls_for_screenshots:
                        urls_for_screenshots.append(normalized)

            if not urls_for_screenshots:
                logger.info("No URLs found for screenshot processing")
                return

            logger.info(f"Spawning screenshot job for {len(urls_for_screenshots)} typosquat URLs")

            # Spawn screenshot job using the generic base class method
            task_id = await self.spawn_screenshot_job(urls_for_screenshots, program_name)

            if task_id:
                logger.info(f"Successfully spawned screenshot job with task_id: {task_id}")

                # Mark that we've spawned screenshot jobs to prevent duplication
                self.has_spawned_screenshot_jobs = True

                # Store context for parsing the output later
                screenshot_context = {
                    'is_typosquat_screenshots': True,
                    'task_id': task_id,
                    'program_name': program_name,
                    'workflow_id': os.getenv('WORKFLOW_ID', 'unknown'),
                    'step_name': 'typosquat_detection',
                    'original_urls': urls_for_screenshots,
                    'typosquat_urls': typosquat_urls
                }

                # Store the context for later output processing
                if not hasattr(self, 'spawned_job_contexts'):
                    self.spawned_job_contexts = {}
                self.spawned_job_contexts[task_id] = screenshot_context

                # Register output handler for the screenshot job immediately
                logger.info(f"🔗 Registering output handler for screenshot job {task_id}")
                self._register_output_handlers_for_spawned_tasks([task_id])

            else:
                logger.error("❌ Failed to spawn screenshot job")

        except Exception as e:
            logger.error(f"Error triggering screenshot jobs for typosquat URLs: {e}")
            logger.exception("Full traceback:")

    def _trigger_fuzzing_for_typosquat_domains(self, typosquat_findings, params: Optional[Dict[Any, Any]] = None):
        """
        Trigger fuzzing jobs for registered typosquat domains.

        This enables Phase 4 of typosquat detection: URL fuzzing on typosquat domains
        to discover additional suspicious paths.
        """
        # Check if fuzzing is enabled in params
        enable_fuzzing = params.get("enable_fuzzing", False) if params else False

        if not enable_fuzzing:
            logger.info("Fuzzing disabled - skipping fuzzing phase")
            return

        try:
            logger.debug(f"Triggering fuzzing for {len(typosquat_findings)} typosquat findings")

            # Extract domains that should be fuzzed
            domains_for_fuzzing = []
            for finding in typosquat_findings:
                if finding.typo_domain and finding.domain_registered:
                    # Build base URLs for fuzzing (http and https)
                    base_urls = [
                        f"https://{finding.typo_domain}",
                        f"http://{finding.typo_domain}"
                    ]
                    domains_for_fuzzing.append({
                        'urls': base_urls,
                        'typo_domain': finding.typo_domain,
                        'risk_factors': {
                            'total_score': finding.risk_analysis_total_score,
                            'risk_level': finding.risk_analysis_risk_level,
                            'domain_registered': finding.domain_registered
                        }
                    })

            if not domains_for_fuzzing:
                logger.info("No registered domains found for fuzzing")
                return

            logger.info("🔍 PHASE 4: FUZZING TRIGGERED 🔍")
            logger.info(f"📋 Spawning fuzzing jobs for {len(domains_for_fuzzing)} typosquat domains")

            # Get program name from environment
            program_name = os.getenv('PROGRAM_NAME', 'default')

            # Get wordlist from params
            wordlist = params.get("fuzzer_wordlist", "/workspace/files/webcontent_test.txt") if params else "/workspace/files/webcontent_test.txt"

            # Use asyncio.create_task to spawn fuzzing jobs asynchronously
            asyncio.create_task(
                self._spawn_fuzzing_jobs_async(domains_for_fuzzing, program_name, wordlist, typosquat_findings)
            )

        except Exception as e:
            logger.error(f"Error triggering fuzzing for typosquat domains: {e}")
            logger.exception("Full traceback:")

    async def _spawn_fuzzing_jobs_async(self, domains_data: List[Dict[str, Any]], program_name: str,
                                       wordlist: str, typosquat_findings):
        """
        Async method to spawn fuzzing jobs for typosquat domains.

        Args:
            domains_data: List of domain data dicts with URLs, typo_domain, risk_factors
            program_name: Program name for context
            wordlist: Wordlist to use for fuzzing
            typosquat_findings: Original typosquat findings for context
        """
        try:
            # Import FuzzWebsite to generate commands
            from .fuzz_website import FuzzWebsite
            fuzz_task = FuzzWebsite()

            for domain_data in domains_data:
                urls = domain_data['urls']
                typo_domain = domain_data['typo_domain']
                risk_factors = domain_data.get('risk_factors', {})

                # Generate fuzzing command for each URL
                for url in urls:
                    # Build ffuf command
                    command = (
                        f"python ffuf_wrapper.py "
                        f"-u {url}/FUZZ "
                        f"-w {wordlist} "
                        f"-s "  # Silent mode
                        f"-json "  # JSON output
                        f"-mc 200,204,301,302,307,401,403,405 "  # Match status codes
                        f"-t 50 "  # Threads
                        f"-timeout 10"  # Timeout per request
                    )

                    # Spawn fuzzing job using the base class method
                    task_id = await self.spawn_worker_job(
                        task_name="fuzz_website",
                        command=command,
                        program_name=program_name,
                        timeout=1200  # 20 minutes for fuzzing jobs
                    )

                    if task_id:
                        logger.info(f"✅ Successfully spawned fuzzing job for {url} with task_id: {task_id}")

                        # Store context for parsing the output later
                        fuzzing_context = {
                            'is_typosquat_fuzzing': True,
                            'task_id': task_id,
                            'typo_domain': typo_domain,
                            'base_url': url,
                            'risk_factors': risk_factors,
                            'fuzzer_wordlist': wordlist,
                            'program_name': program_name,
                            'workflow_id': os.getenv('WORKFLOW_ID', 'unknown'),
                            'step_name': 'typosquat_detection',
                            'typosquat_findings': typosquat_findings
                        }

                        # Store the context for later output processing
                        if not hasattr(self, 'spawned_job_contexts'):
                            self.spawned_job_contexts = {}
                        self.spawned_job_contexts[task_id] = fuzzing_context

                        # Register output handler for the fuzzing job immediately
                        logger.info(f"🔗 Registering output handler for fuzzing job {task_id}")
                        self._register_output_handlers_for_spawned_tasks([task_id])

                    else:
                        logger.error(f"❌ Failed to spawn fuzzing job for {url}")

        except Exception as e:
            logger.error(f"Error spawning fuzzing jobs: {e}")
            logger.exception("Full traceback:")
    
    def _register_output_handlers_for_spawned_tasks(self, task_ids: List[str]):
        """Register output handlers immediately after spawning tasks"""
        if not self.task_queue_client:
            logger.error("❌ No task_queue_client available - cannot register output handlers for spawned tasks")
            return
            
        logger.info(f"🔗 Registering output handlers for {len(task_ids)} spawned tasks immediately after spawning")
        
        for task_id in task_ids:
            def make_output_handler(tid):
                def output_handler(output):
                    logger.info(f"📥 *** RECEIVED OUTPUT FROM SPAWNED TASK {tid} ***")
                    self.spawned_task_outputs[tid] = output
                    logger.info(f"📥 Stored output for task {tid}")
                return output_handler
            
            self.task_queue_client.output_handlers[task_id] = make_output_handler(task_id)
            logger.info(f"✅ Registered output handler for task {task_id}")

    async def wait_for_spawned_jobs(self, timeout: int = 3600, task_queue_client=None) -> Dict[str, str]:
        """Wait for all spawned subdomain discovery jobs to complete and collect their outputs"""
        max_phases = 5  # Maximum number of phases to prevent infinite loops
        phase_count = 0
        all_job_statuses = {}
        
        while phase_count < max_phases:
            phase_count += 1
            
            if not self.spawned_job_names:
                logger.info(f"📋 Phase {phase_count}: No spawned jobs to wait for")
                break
            
            logger.info(f"🔄 Phase {phase_count}: Waiting for {len(self.spawned_job_names)} spawned jobs to complete")
            
            try:
                # Import kubernetes service
                from services.kubernetes import KubernetesService
                k8s_service = KubernetesService()
                
                # Wait for all jobs to complete
                job_statuses = await k8s_service.wait_for_jobs_completion(
                    self.spawned_job_names, 
                    timeout=timeout,
                    check_interval=30
                )
                
                # Merge job statuses
                all_job_statuses.update(job_statuses)
                
                # Log final status
                succeeded = sum(1 for status in job_statuses.values() if status == 'succeeded')
                failed = sum(1 for status in job_statuses.values() if status == 'failed')
                logger.info(f"✅ Phase {phase_count} jobs completed: {succeeded} succeeded, {failed} failed")
                
                # Check if new jobs were spawned during output processing
                initial_job_count = len(self.spawned_job_names)
                await asyncio.sleep(2)  # Allow time for any new jobs to be spawned
                
                if len(self.spawned_job_names) > initial_job_count:
                    logger.info(f"🚀 Phase {phase_count} spawned new jobs, continuing to next phase")
                    continue
                else:
                    logger.info(f"✅ Phase {phase_count} completed with no new jobs spawned")
                    break
                
            except Exception as e:
                logger.error(f"Error waiting for spawned jobs in phase {phase_count}: {e}")
                for job_name in self.spawned_job_names:
                    if job_name not in all_job_statuses:
                        all_job_statuses[job_name] = 'unknown'
                break
        
        logger.info(f"🏁 All phases completed after {phase_count} phases")
        return all_job_statuses

    def process_spawned_task_outputs(self) -> Dict[AssetType, List[Any]]:
        """Process and merge outputs from spawned tasks (screenshots and subdomain discovery)"""
        if not self.spawned_task_outputs:
            logger.info("No spawned task outputs to process")
            return {}

        logger.info(f"🔄 Processing outputs from {len(self.spawned_task_outputs)} spawned tasks")
        
        # Use workflow orchestrator and screenshot processor for output handling
        all_findings = []
        
        for task_id, output in self.spawned_task_outputs.items():
            if not output:
                logger.warning(f"⚠️ Empty output from task {task_id}")
                continue
                
            try:
                # Check if we have context for this job to determine its type
                if hasattr(self, 'spawned_job_contexts') and task_id in self.spawned_job_contexts:
                    context = self.spawned_job_contexts[task_id]
                    
                    # Handle screenshot jobs
                    if context.get('is_typosquat_screenshots', False):
                        logger.info(f"Processing screenshot output from task {task_id}")
                        asyncio.create_task(self.screenshot_processor.process_and_upload_screenshots(output, context))
                    
                    # Handle fuzzing jobs (Phase 4)
                    elif context.get('is_typosquat_fuzzing', False):
                        logger.info(f"🔍 Phase 4: Processing fuzz_website output from task {task_id}")

                        # Parse fuzzing output and transform to findings
                        typosquat_url_findings = self._parse_fuzzing_output_to_findings(output, context)

                        if typosquat_url_findings:
                            all_findings.extend(typosquat_url_findings)
                            logger.info(f"✅ Phase 4: Created {len(typosquat_url_findings)} TyposquatURL findings from fuzzing")
                
            except Exception as e:
                logger.error(f"❌ Error processing output from task {task_id}: {e}")
        
        # Return any findings we collected
        # Separate TyposquatURL findings from TyposquatDomain findings
        typosquat_domains = [f for f in all_findings if hasattr(f, 'typo_domain') and not hasattr(f, 'path')]
        typosquat_urls = [f for f in all_findings if hasattr(f, 'path')]

        result = {}
        if typosquat_domains:
            result[FindingType.TYPOSQUAT_DOMAIN] = typosquat_domains
            logger.info(f"Returning {len(typosquat_domains)} TyposquatDomain findings")
        if typosquat_urls:
            result[FindingType.TYPOSQUAT_URL] = typosquat_urls
            logger.info(f"Returning {len(typosquat_urls)} TyposquatURL findings")

        return result if result else {}
    
    def parse_spawned_job_output(self, task_name: str, output: Any, context: Optional[Dict[str, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse output from spawned jobs using the appropriate task's parse_output method"""
        try:
            # Handle different output formats
            if isinstance(output, dict) and "output" in output:
                actual_output = output["output"]
            else:
                actual_output = output

            # Route to the appropriate component
            if task_name == "screenshot_website":
                # Process screenshot data and upload to API
                task_id = context.get('task_id', 'unknown') if context else 'unknown'
                logger.info(f"Processing screenshot output for task {task_id}")
                asyncio.create_task(self.screenshot_processor.process_and_upload_screenshots(actual_output, context))
                return {}
            else:
                logger.error(f"Unknown task type for parsing: {task_name}")
                return {}

        except Exception as e:
            logger.error(f"Error parsing spawned job output for {task_name}: {e}")
            return {}

    def _parse_fuzzing_output_to_findings(self, output: Any, context: Dict[str, Any]) -> List[Any]:
        """
        Parse fuzzing output and transform URL assets to TyposquatURL findings.

        This demonstrates the dual-purpose task pattern where:
        1. FuzzWebsite.parse_output() parses raw output to URL assets
        2. FuzzWebsite.transform_to_findings() transforms assets to findings using context

        Args:
            output: Raw output from fuzz_website job
            context: Fuzzing context with typo_domain, risk_factors, etc.

        Returns:
            List of TyposquatURL findings
        """
        try:
            # Import FuzzWebsite to use its parsing logic
            from .fuzz_website import FuzzWebsite

            fuzz_task = FuzzWebsite()

            # Step 1: Parse output to URL assets (normal mode)
            parsed_assets = fuzz_task.parse_output(output)

            if not parsed_assets or AssetType.URL not in parsed_assets:
                logger.info("No URL assets found in fuzzing output")
                return []

            url_assets = parsed_assets[AssetType.URL]
            logger.info(f"Parsed {len(url_assets)} URL assets from fuzzing output")

            # Step 2: Transform URL assets to TyposquatURL findings using context
            transformation_context = {
                'typo_domain': context.get('typo_domain', ''),
                'risk_factors': context.get('risk_factors', {}),
                'fuzzer_wordlist': context.get('fuzzer_wordlist', 'unknown'),
                'program_name': context.get('program_name', '')
            }

            findings_dict = fuzz_task.transform_to_findings(parsed_assets, transformation_context)

            if FindingType.TYPOSQUAT_URL in findings_dict:
                findings = findings_dict[FindingType.TYPOSQUAT_URL]
                logger.info(f"Transformed {len(findings)} URL assets to TyposquatURL findings")
                return findings
            else:
                logger.warning("No TyposquatURL findings produced from transformation")
                return []

        except Exception as e:
            logger.error(f"Error parsing fuzzing output to findings: {e}")
            logger.exception("Full traceback:")
            return []

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'api_client') and self.api_client:
            self.api_client.cleanup()
        if hasattr(self, 'variation_cache') and self.variation_cache:
            self.variation_cache.cleanup()
    
    def process_pending_typosquat_urls(self):
        """Process pending typosquat URLs after the typosquat domains have been sent to the API"""
        if not hasattr(self, 'pending_typosquat_urls') or not self.pending_typosquat_urls:
            logger.info("No pending typosquat URLs to process")
            return

        logger.info(f"🔄 Processing {len(self.pending_typosquat_urls)} pending typosquat URLs")

        try:
            # Use the analyzer component to store URLs
            self.typosquat_analyzer.store_typosquat_urls(self.pending_typosquat_urls)
            
            # Clear the pending list after successful processing
            self.pending_typosquat_urls = []
            logger.info("✅ Successfully processed all pending typosquat URLs")

        except Exception as e:
            logger.error(f"Failed to process pending typosquat URLs: {e}")
            logger.warning("Pending typosquat URLs will be retried on next attempt")
    
    @classmethod
    def get_usage_examples(cls) -> Dict[str, Any]:
        """Get usage examples for the typosquat detection task"""
        return {
            "standard_mode": {
                "description": "Generate variations and detect typosquatting domains",
                "parameters": {
                    "max_variations": 100,
                    "fuzzers": ["insertion", "replacement", "omission"],
                    "exclude_tested": True,
                    "include_subdomains": False
                },
                "input": ["example.com", "test.org"]
            },
            "input_analysis_mode": {
                "description": "Analyze input domains as typosquat variations (no variation generation)",
                "parameters": {
                    "analyze_input_as_variations": True,
                    "include_subdomains": True,
                    "active_checks": True,
                    "geoip_checks": True
                },
                "input": ["suspicious-domain.com", "potential-typo.net"],
                "note": "Input domains are treated as potential typosquat domains and analyzed directly"
            },
            "subdomain_discovery_mode": {
                "description": "Enable multi-phase workflow with subdomain discovery",
                "parameters": {
                    "include_subdomains": True,
                    "max_workers": 5,
                    "active_checks": True,
                    "geoip_checks": True
                },
                "input": ["target-domain.com"]
            }
        }