import logging
import os
import tempfile
import subprocess
from typing import Dict, List, Any, Optional
import base64
import requests

from .base import Task, AssetType, CommandSpec

logger = logging.getLogger(__name__)

class SubdomainPermutations(Task):
    """
    Orchestrator task that generates subdomain permutations using gotator
    and spawns resolve_domain jobs to validate them.
    
    Workflow:
    1. Receives input subdomains (e.g., ["domain1.com", "www.domain1.com"])
    2. Runs gotator to generate permutations
    3. Chunks permutations for batch processing
    4. Spawns resolve_domain worker jobs using WorkerJobManager
    5. Aggregates and returns resolved subdomains and IPs
    
    Task parameters:
    - permutation_limit (int): Maximum number of permutations to process (default: None)
    - chunk_size (int): Number of permutations per resolve_domain job (default: 100)
    - batch_size (int): Number of jobs to spawn per batch (default: 10)
    """
    
    name = "subdomain_permutations"
    description = "Generate subdomain permutations using gotator and resolve them"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN, AssetType.IP]

    def __init__(self):
        super().__init__()

        # Configuration for job management
        self.chunk_size = int(os.getenv('PERMUTATIONS_CHUNK_SIZE', '100'))  # Permutations per resolve_domain job
        self.batch_size = int(os.getenv('PERMUTATIONS_BATCH_SIZE', '10'))  # Jobs per batch spawn
        self.job_timeout = int(os.getenv('PERMUTATIONS_JOB_TIMEOUT', '300'))  # 5 minutes per job
        self.total_timeout = int(os.getenv('PERMUTATIONS_TOTAL_TIMEOUT', '1800'))  # 30 minutes total
        
        # Gotator configuration
        self.permutations_file = os.getenv('PERMUTATIONS_FILE', 'files/permutations.txt')
        self.gotator_depth = int(os.getenv('GOTATOR_DEPTH', '1'))
        self.gotator_numbers = int(os.getenv('GOTATOR_NUMBERS', '10'))
        self.gotator_timeout = int(os.getenv('GOTATOR_TIMEOUT', '300'))  # 5 minutes for gotator execution

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """
        Generate hash for caching.
        Note: Orchestrator tasks typically don't use individual hashing.
        """
        hash_dict = {
            "task": self.name,
            "target": target
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()

    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """
        This method is not used for orchestrator tasks - return empty.
        Orchestrator tasks use generate_commands instead.
        """
        return ""

    async def generate_commands(
        self,
        input_data: List[Any],
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[CommandSpec]:
        """
        Generate resolve_domain commands for permutation chunks.
        Uses gotator for permutation generation, wildcard filtering, then chunks for resolve_domain.
        """
        if not input_data:
            return []

        # Set job_manager and task_queue_client from context for _filter_wildcard_domains
        # (which may call _resolve_unknown_domains for domains not in API)
        self.job_manager = context.get('job_manager')
        self.task_queue_client = context.get('task_queue_client')

        subdomains_to_process = input_data if isinstance(input_data, list) else [input_data]
        logger.info(f"📋 Processing {len(subdomains_to_process)} input subdomains for permutation generation")

        program_name = context.get('program_name', os.getenv('PROGRAM_NAME', 'default'))
        task_def = context.get('task_def')
        permutation_limit = None
        permutation_list = None
        if task_def and hasattr(task_def, 'params') and task_def.params:
            permutation_limit = task_def.params.get('permutation_limit', None)
            permutation_list = task_def.params.get('permutation_list', None)
            self.chunk_size = task_def.params.get('chunk_size', self.chunk_size)
            self.batch_size = task_def.params.get('batch_size', self.batch_size)

        if permutation_list:
            permutation_list = self._resolve_permutation_list_path(permutation_list)

        # Step 1: Check for wildcard domains and filter them out
        logger.info("🔍 Checking for wildcard domains and hierarchy...")
        non_wildcard_subdomains, wildcard_hierarchy_map = await self._filter_wildcard_domains(
            subdomains_to_process, program_name
        )

        if not non_wildcard_subdomains:
            logger.warning("⚠️ All input subdomains are wildcards - skipping permutation generation")
            return []

        # Step 2: Run gotator to generate permutations
        logger.info(f"🔧 Generating permutations using gotator for {len(non_wildcard_subdomains)} domain(s)...")
        permutations = self._generate_permutations_with_gotator(non_wildcard_subdomains, permutation_list)

        if not permutations:
            logger.warning("⚠️ No permutations generated by gotator")
            return []

        # Step 3: Filter permutations based on wildcard hierarchy
        if wildcard_hierarchy_map:
            permutations = self._filter_permutations_by_wildcard_hierarchy(
                permutations, wildcard_hierarchy_map
            )
            if not permutations:
                return []

        # Step 4: Apply permutation limit if specified
        if permutation_limit and len(permutations) > permutation_limit:
            permutations = permutations[:permutation_limit]

        # Step 5: Chunk permutations and generate CommandSpec for each chunk
        from .resolve_domain import ResolveDomain
        resolve_domain_task = ResolveDomain()

        command_specs = []
        for i in range(0, len(permutations), self.chunk_size):
            chunk = permutations[i : i + self.chunk_size]
            command = resolve_domain_task.get_command(chunk, params)
            if command and command != "echo ''":
                command_specs.append(
                    CommandSpec(task_name="resolve_domain", command=command, params=params)
                )

        logger.info(f"📦 Generated {len(command_specs)} resolve_domain commands")
        return command_specs

    def _get_domain_hierarchy(self, domain: str) -> List[str]:
        """
        Extract all domain levels from a domain.
        
        Example:
            "sub.api.example.com" -> ["sub.api.example.com", "api.example.com", "example.com"]
        
        Args:
            domain: Domain name
            
        Returns:
            List of domain levels from most specific to least specific
        """
        parts = domain.split('.')
        hierarchy = []
        
        # Build hierarchy from most specific to least specific
        for i in range(len(parts)):
            level = '.'.join(parts[i:])
            # Skip single-part domains and TLDs
            if '.' in level:
                hierarchy.append(level)
        
        return hierarchy

    def _check_wildcard_hierarchy(self, domain: str, program_name: str) -> tuple:
        """
        Check wildcard status for all levels of a domain hierarchy.
        
        Example:
            Input: "sub.domain.com"
            Output: (
                {"sub.domain.com": False, "domain.com": True},  # wildcard_status
                ["sub.domain.com"]  # unknown_domains (not found in API)
            )
        
        Args:
            domain: Domain to check
            program_name: Program name for API query
            
        Returns:
            Tuple of (wildcard_status dict, list of unknown domains)
        """
        hierarchy = self._get_domain_hierarchy(domain)
        wildcard_status = {}
        unknown_domains = []
        
        # Get API configuration
        api_url = os.getenv('API_URL', 'http://api:8000')
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
        
        if not api_url or not internal_api_key:
            # If API not configured, assume no wildcards
            return {level: False for level in hierarchy}, []
        
        search_url = f"{api_url.rstrip('/')}/assets/subdomain/search"
        headers = {
            'Authorization': f'Bearer {internal_api_key}',
            'Content-Type': 'application/json'
        }
        
        for level in hierarchy:
            try:
                request_data = {
                    "exact_match": level.strip().lower(),
                    "program": program_name,
                    "page": 1,
                    "page_size": 1
                }
                
                response = requests.post(
                    search_url,
                    json=request_data,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    items = result.get("items", [])
                    
                    if items:
                        domain_data = items[0]
                        is_wildcard = domain_data.get("is_wildcard", False)
                        wildcard_status[level] = is_wildcard
                        logger.debug(f"Domain level {level}: is_wildcard={is_wildcard}")
                    else:
                        # Not found in API - mark as unknown
                        wildcard_status[level] = None  # None means unknown
                        unknown_domains.append(level)
                        logger.debug(f"Domain level {level} not found in API - needs resolution")
                else:
                    wildcard_status[level] = False
                    logger.debug(f"API error for {level}, assuming not wildcard")
                    
            except Exception as e:
                logger.debug(f"Error checking {level}: {e}, assuming not wildcard")
                wildcard_status[level] = False
        
        return wildcard_status, unknown_domains

    async def _wait_for_domains_in_api(self, domains: List[str], program_name: str, max_attempts: int = 5, initial_delay: float = 2.0) -> bool:
        """
        Poll the API to check if domains are now available after resolution.
        Uses exponential backoff.
        
        Args:
            domains: List of domains to check for
            program_name: Program name for API query
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay between attempts in seconds
            
        Returns:
            True if all domains found, False otherwise
        """
        import asyncio
        
        api_url = os.getenv('API_URL', 'http://api:8000')
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
        
        if not api_url or not internal_api_key:
            return False
        
        search_url = f"{api_url.rstrip('/')}/assets/subdomain/search"
        headers = {
            'Authorization': f'Bearer {internal_api_key}',
            'Content-Type': 'application/json'
        }
        
        for attempt in range(max_attempts):
            found_count = 0
            
            for domain in domains:
                try:
                    request_data = {
                        "exact_match": domain.strip().lower(),
                        "program": program_name,
                        "page": 1,
                        "page_size": 1
                    }
                    
                    response = requests.post(
                        search_url,
                        json=request_data,
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        items = result.get("items", [])
                        if items:
                            found_count += 1
                except Exception as e:
                    logger.debug(f"Error checking {domain} in attempt {attempt + 1}: {e}")
            
            if found_count == len(domains):
                logger.info(f"✅ All {len(domains)} domain(s) now available in API")
                return True
            
            if attempt < max_attempts - 1:
                delay = initial_delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"⏳ {found_count}/{len(domains)} domain(s) found, waiting {delay:.1f}s before retry {attempt + 2}/{max_attempts}...")
                await asyncio.sleep(delay)
        
        logger.warning(f"⚠️ Only {found_count}/{len(domains)} domain(s) found after {max_attempts} attempts")
        return found_count > 0  # Return True if at least some domains were found
    
    async def _resolve_unknown_domains(self, unknown_domains: List[str], program_name: str) -> bool:
        """
        Resolve unknown domains using resolve_domain worker jobs.
        This determines their wildcard status before permutation generation.
        
        Args:
            unknown_domains: List of domains not found in API
            program_name: Program name for context
            
        Returns:
            True if domains were resolved successfully, False otherwise
        """
        if not unknown_domains:
            return True
        
        if not hasattr(self, 'job_manager') or not self.job_manager:
            logger.warning("WorkerJobManager not available, cannot resolve unknown domains")
            return False
        
        try:
            logger.info(f"🔍 Resolving {len(unknown_domains)} unknown domain(s) to determine wildcard status...")
            
            # Import resolve_domain task
            from .resolve_domain import ResolveDomain
            resolve_domain_task = ResolveDomain()
            
            # Track sent assets
            assets_sent = [0]  # Use list for mutability in nested function
            
            # Define callback to process and send results to API
            def process_resolution_results(outputs: Dict[str, Any], batch_num: int):
                """Process resolve_domain outputs and send to API"""
                logger.info(f"🔄 CALLBACK INVOKED: Processing resolution results from batch {batch_num}")
                logger.debug(f"Received {len(outputs)} outputs: {list(outputs.keys())}")
                batch_assets = {}
                
                for task_id, output in outputs.items():
                    if not output or output == "":
                        logger.warning(f"Skipping empty output for task {task_id}")
                        continue
                    
                    try:
                        logger.debug(f"Parsing output from task {task_id} (type: {type(output)}, length: {len(str(output)) if output else 0})")
                        logger.debug(f"Output preview: {str(output)[:200]}")
                        
                        # Parse the resolve_domain output
                        parsed_assets = resolve_domain_task.parse_output(output)
                        
                        logger.info(f"✅ Parsed {sum(len(v) for v in parsed_assets.values())} total assets from task {task_id}")
                        logger.debug(f"Asset types breakdown: {[(k, len(v)) for k, v in parsed_assets.items()]}")
                        
                        # Merge assets from this job into batch
                        for asset_type, assets in parsed_assets.items():
                            if asset_type not in batch_assets:
                                batch_assets[asset_type] = []
                            batch_assets[asset_type].extend(assets)
                        
                    except Exception as e:
                        logger.error(f"❌ Error parsing output from resolution task {task_id}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # Send batch assets to API if we have any
                if batch_assets and hasattr(self, 'task_queue_client') and self.task_queue_client:
                    total_assets = sum(len(assets) for assets in batch_assets.values())
                    if total_assets > 0:
                        logger.info(f"🚀 Sending {total_assets} resolved assets to API")
                        logger.debug(f"Asset breakdown: {[(k, len(v)) for k, v in batch_assets.items()]}")
                        
                        # Convert AssetType keys to string values for API compatibility
                        converted_assets = {}
                        for asset_type, assets in batch_assets.items():
                            if hasattr(asset_type, 'value'):
                                converted_assets[asset_type.value] = assets
                            else:
                                converted_assets[str(asset_type)] = assets
                        
                        # Send to API
                        try:
                            success = self.task_queue_client.task_executor.data_api_client.send_assets(
                                "wildcard_check_resolution",
                                program_name,
                                self.task_queue_client.task_executor.execution_id or "",
                                converted_assets,
                                self.task_queue_client.task_executor.asset_processor
                            )
                            
                            if success:
                                logger.info(f"✅ Successfully sent {total_assets} resolved assets to API")
                                assets_sent[0] += total_assets
                            else:
                                logger.warning("❌ Failed to send resolved assets to API")
                        except Exception as e:
                            logger.error(f"❌ Error sending resolved assets to API: {e}")
            
            # Spawn resolve_domain job for unknown domains
            batch_result = await self.job_manager.spawn_task_batch(
                task_name="resolve_domain",
                input_data_list=[unknown_domains],  # All domains in one job
                batch_size=1,
                timeout=60,  # Short timeout for simple resolution
                process_incrementally=True,  # Enable incremental processing
                parse_output=False,  # We handle parsing in callback
                result_processor=process_resolution_results,  # ✅ CORRECT parameter name!
                sequential_batches=False,
                step_name="wildcard_check_resolution"
            )
            
            # Wait for completion
            logger.info("⏳ Waiting for domain resolution to complete...")
            await self.job_manager.wait_for_batch(
                batch_result,
                timeout=120  # 2 minutes max
            )
            
            # Get job statistics
            stats = self.job_manager.get_job_statistics(batch_result)
            logger.info(f"✅ Domain resolution completed: {stats}")
            
            # Report how many assets were sent
            if assets_sent[0] > 0:
                logger.info(f"📊 Sent {assets_sent[0]} total assets to API from resolution")
            else:
                logger.warning("⚠️ No assets were sent to API from resolution - resolution may have failed")
            
            # Cleanup
            self.job_manager.cleanup_batch(batch_result)
            
            # If no assets were sent, resolution failed
            if assets_sent[0] == 0:
                logger.error("❌ Resolution completed but no assets were generated or sent to API")
                return False
            
            # Wait for domains to be available in API with retry logic
            logger.info("⏳ Waiting for resolved domains to be available in API...")
            domains_available = await self._wait_for_domains_in_api(unknown_domains, program_name)
            
            if not domains_available:
                logger.warning("⚠️ Resolved domains not yet fully available in API after polling, but will proceed with re-check")
            
            return True  # Return success if we sent assets, even if polling timed out
            
        except Exception as e:
            logger.error(f"❌ Error resolving unknown domains: {e}")
            return False
    
    async def _filter_wildcard_domains(self, subdomains: List[str], program_name: str) -> tuple:
        """
        Check domains via API and filter out wildcard domains.
        Also builds wildcard hierarchy information for intelligent permutation filtering.
        
        If domains are not found in API, resolves them first to determine wildcard status.
        
        Wildcard domains resolve any subdomain, so generating permutations is wasteful.
        
        Args:
            subdomains: List of subdomain names to check
            program_name: Program name for API query
            
        Returns:
            Tuple of (non_wildcard_subdomains, wildcard_hierarchy_map)
            - non_wildcard_subdomains: List of domains to process
            - wildcard_hierarchy_map: Dict mapping domain to its deepest non-wildcard level
        """
        try:
            # Get API configuration
            api_url = os.getenv('API_URL', 'http://api:8000')
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
            
            if not api_url or not internal_api_key:
                logger.warning("API configuration not available, skipping wildcard check")
                return subdomains, {}
            
            # First pass: Check all domains and collect unknown ones
            all_unknown_domains = set()
            hierarchy_results = {}  # Cache hierarchy checks
            
            for subdomain in subdomains:
                try:
                    hierarchy_status, unknown_domains = self._check_wildcard_hierarchy(subdomain, program_name)
                    hierarchy_results[subdomain] = hierarchy_status
                    all_unknown_domains.update(unknown_domains)
                except Exception as e:
                    logger.warning(f"Error checking hierarchy for {subdomain}: {e}")
                    hierarchy_results[subdomain] = {}
            
            # If we found unknown domains, resolve them first
            if all_unknown_domains:
                logger.info(f"📍 Found {len(all_unknown_domains)} unknown domain(s) in hierarchy, resolving them first...")
                logger.debug(f"Unknown domains to resolve: {list(all_unknown_domains)}")
                
                resolved = await self._resolve_unknown_domains(list(all_unknown_domains), program_name)
                
                # Re-check hierarchy regardless of resolution success
                # This ensures we get the latest data from API
                logger.info("🔄 Re-checking wildcard status for all domains...")
                recheck_count = 0
                still_unknown = set()
                
                for subdomain in subdomains:
                    if subdomain in hierarchy_results:
                        # Check if this subdomain had any unknowns
                        had_unknowns = any(
                            hierarchy_results[subdomain].get(level) is None 
                            for level in hierarchy_results[subdomain]
                        )
                        if had_unknowns:
                            # Re-check this hierarchy
                            logger.debug(f"Re-checking hierarchy for {subdomain}...")
                            hierarchy_status, new_unknowns = self._check_wildcard_hierarchy(subdomain, program_name)
                            hierarchy_results[subdomain] = hierarchy_status
                            recheck_count += 1
                            
                            if new_unknowns:
                                still_unknown.update(new_unknowns)
                                logger.debug(f"Domain {subdomain} still has {len(new_unknowns)} unknown level(s): {new_unknowns}")
                
                logger.info(f"✅ Re-checked {recheck_count} domain hierarchies")
                
                if still_unknown:
                    logger.warning(f"⚠️ {len(still_unknown)} domain(s) still unknown after resolution: {list(still_unknown)[:5]}{'...' if len(still_unknown) > 5 else ''}")
                    if resolved:
                        logger.warning("⚠️ Resolution succeeded but domains not yet available in API - may need more processing time")
                    else:
                        logger.warning("⚠️ Resolution failed - proceeding with partial data")
            
            # Second pass: Build results based on hierarchy status
            non_wildcard_subdomains = []
            wildcard_domains = []
            wildcard_hierarchy_map = {}  # Maps domain to deepest non-wildcard level
            
            # Check each subdomain and its hierarchy
            for subdomain in subdomains:
                try:
                    # Get cached hierarchy status
                    hierarchy_status = hierarchy_results.get(subdomain, {})
                    
                    # Find the deepest non-wildcard level
                    # Skip unknown (None) values - treat as not wildcard if still unknown after resolution attempt
                    deepest_non_wildcard = None
                    for level in self._get_domain_hierarchy(subdomain):
                        level_status = hierarchy_status.get(level, False)
                        # Treat None (unknown) as False (not wildcard) if still present
                        if level_status is None:
                            level_status = False
                        if not level_status:
                            deepest_non_wildcard = level
                            break  # Found deepest (most specific) non-wildcard level
                    
                    # Check if the subdomain itself is wildcard
                    subdomain_is_wildcard = hierarchy_status.get(subdomain, False)
                    # Treat None (unknown) as False (not wildcard)
                    if subdomain_is_wildcard is None:
                        subdomain_is_wildcard = False
                    
                    if subdomain_is_wildcard:
                        logger.info(f"🚫 Skipping wildcard domain: {subdomain}")
                        wildcard_domains.append(subdomain)
                    else:
                        logger.debug(f"✅ Non-wildcard domain: {subdomain}")
                        non_wildcard_subdomains.append(subdomain)
                        
                        # Store wildcard hierarchy info if ANY parent is wildcard
                        # Check all levels except the subdomain itself
                        hierarchy = self._get_domain_hierarchy(subdomain)
                        has_wildcard_parent = any(
                            hierarchy_status.get(level, False) is True  # Explicitly check for True (not None or False)
                            for level in hierarchy 
                            if level != subdomain
                        )
                        
                        if has_wildcard_parent and deepest_non_wildcard:
                            wildcard_hierarchy_map[subdomain] = deepest_non_wildcard
                            logger.info(f"📍 Domain {subdomain} has wildcard parent, deepest non-wildcard: {deepest_non_wildcard}")
                        
                except Exception as e:
                    logger.warning(f"Error checking wildcard hierarchy for {subdomain}: {e}, including it")
                    non_wildcard_subdomains.append(subdomain)
            
            if wildcard_domains:
                logger.info(f"🚫 Filtered out {len(wildcard_domains)} wildcard domain(s): {', '.join(wildcard_domains[:5])}{'...' if len(wildcard_domains) > 5 else ''}")
            
            return non_wildcard_subdomains, wildcard_hierarchy_map
            
        except Exception as e:
            logger.error(f"Error filtering wildcard domains: {e}")
            # On error, return all subdomains to avoid blocking permutation generation
            logger.warning("Continuing with all subdomains due to wildcard check error")
            return subdomains, {}

    def _filter_permutations_by_wildcard_hierarchy(self, permutations: List[str], 
                                                   wildcard_hierarchy_map: Dict[str, str]) -> List[str]:
        """
        Filter permutations based on wildcard hierarchy information.
        
        If a parent domain is wildcard, only keep permutations that end with the
        deepest non-wildcard level.
        
        Example:
            Input permutations: ["perm.sub.domain.com", "permsub.domain.com"]
            Hierarchy: {"sub.domain.com": "sub.domain.com"} (domain.com is wildcard)
            Output: ["perm.sub.domain.com"] (removed "permsub.domain.com")
        
        Args:
            permutations: List of generated permutations
            wildcard_hierarchy_map: Maps domain to its deepest non-wildcard level
            
        Returns:
            Filtered list of permutations
        """
        if not wildcard_hierarchy_map:
            # No wildcard hierarchy issues, return all permutations
            return permutations
        
        filtered_permutations = []
        removed_count = 0
        
        for permutation in permutations:
            should_keep = True
            permutation_lower = permutation.lower()
            
            # Check against each domain's wildcard hierarchy
            for original_domain, deepest_non_wildcard in wildcard_hierarchy_map.items():
                # Check if this permutation was generated from this domain
                # Permutations should end with the deepest non-wildcard level (exact suffix match)
                if permutation_lower.endswith(f".{deepest_non_wildcard}") or permutation_lower == deepest_non_wildcard:
                    # This permutation is under the safe non-wildcard level - keep it
                    continue
                else:
                    # Check if permutation ends with a wildcard parent level
                    # Get all parent levels that are wildcards
                    hierarchy = self._get_domain_hierarchy(original_domain)
                    for level in hierarchy:
                        if level != deepest_non_wildcard:
                            # This is a wildcard parent level
                            if permutation_lower.endswith(f".{level}") or permutation_lower == level:
                                # Permutation is under wildcard parent but not under safe level
                                should_keep = False
                                removed_count += 1
                                logger.debug(f"🚫 Removing permutation {permutation} (under wildcard {level}, not under safe {deepest_non_wildcard})")
                                break
                    
                if not should_keep:
                    break
            
            if should_keep:
                filtered_permutations.append(permutation)
        
        if removed_count > 0:
            logger.info(f"🧹 Filtered out {removed_count} permutations due to wildcard hierarchy (would resolve via wildcard parent)")
            logger.info(f"📊 Kept {len(filtered_permutations)} permutations under non-wildcard levels")
        
        return filtered_permutations

    def _download_permutation_list(self, url: str) -> str:
        """
        Download a remote permutation list to a temporary file.
        
        Args:
            url: URL to download from
            
        Returns:
            Path to the downloaded temporary file
            
        Raises:
            Exception: If download fails
        """
        import tempfile
        
        try:
            logger.info(f"📥 Downloading permutation list from: {url}")
            
            # Create temporary file for downloaded content
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', prefix='permutations_')
            temp_path = temp_file.name
            
            # Prepare headers with authentication for API downloads
            headers = {}
            
            # If downloading from internal API, add authorization
            if 'api:' in url or '/wordlists/' in url:
                internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
                if internal_api_key:
                    headers['Authorization'] = f'Bearer {internal_api_key}'
                    logger.debug("🔑 Using internal service API key for authentication")
                else:
                    logger.warning("⚠️ No INTERNAL_SERVICE_API_KEY found - API call may fail")
            
            # Download the wordlist
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Write to temporary file
            temp_file.write(response.text)
            temp_file.close()
            
            # Get file size for logging
            file_size = os.path.getsize(temp_path)
            line_count = response.text.count('\n')
            
            logger.info(f"✅ Downloaded permutation list: {file_size} bytes, ~{line_count} lines")
            logger.info(f"📁 Saved to temporary file: {temp_path}")
            
            return temp_path
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to download permutation list from {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error saving permutation list: {e}")
            raise
    
    def _resolve_permutation_list_path(self, permutation_list: str) -> str:
        """
        Resolve permutation list parameter to actual file path.
        Handles database wordlist IDs, URLs, and local file paths.
        Downloads remote lists to temporary files for gotator.
        
        Args:
            permutation_list: Permutation list identifier (UUID, URL, or file path)
            
        Returns:
            Local file path to use with gotator
        """
        import re
        
        # Check if it's a database wordlist ID (UUID format)
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(permutation_list):
            # Convert wordlist ID to API download URL and download it
            api_url = os.getenv("API_URL", "http://api:8000")
            download_url = f"{api_url}/wordlists/{permutation_list}/download"
            logger.info(f"📋 Converted wordlist ID '{permutation_list}' to API URL")
            # Download to local file
            return self._download_permutation_list(download_url)
        elif permutation_list.startswith('http'):
            logger.info("📋 Remote permutation list URL detected")
            # Download to local file
            return self._download_permutation_list(permutation_list)
        elif permutation_list.startswith('/'):
            logger.info(f"📋 Using absolute path permutation list: {permutation_list}")
            return permutation_list
        else:
            # Relative path - assume it's relative to current directory
            logger.info(f"📋 Using relative path permutation list: {permutation_list}")
            return permutation_list
    
    def _generate_permutations_with_gotator(self, subdomains: List[str], permutation_list: str = None) -> List[str]:
        """
        Run gotator on input subdomains to generate permutations.
        
        Gotator command:
        gotator -sub tmp-target-file -perm <permutation_list> -depth 1 -numbers 10 -mindup -adv
        
        Args:
            subdomains: List of input subdomains
            permutation_list: Path to permutation list file (optional, defaults to self.permutations_file)
            
        Returns:
            List of generated permutations (deduplicated, excluding original inputs)
        """
        # Use provided permutation list or fall back to default
        perm_file = permutation_list or self.permutations_file
        
        tmp_file_path = None
        downloaded_perm_file = None  # Track if we downloaded the permutation file
        
        try:
            # Create temporary file for subdomain inputs
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_file:
                tmp_file_path = tmp_file.name
                # Write subdomains to temp file
                for subdomain in subdomains:
                    tmp_file.write(f"{subdomain.strip()}\n")
            
            logger.info(f"📝 Wrote {len(subdomains)} subdomains to temporary file: {tmp_file_path}")
            
            # Check if we need to track this as a downloaded file for cleanup
            # If perm_file starts with /tmp/ or contains 'permutations_', it was likely downloaded
            if perm_file.startswith('/tmp/') and 'permutations_' in perm_file:
                downloaded_perm_file = perm_file
                logger.debug(f"📌 Tracking downloaded permutation file for cleanup: {perm_file}")
            
            if not os.path.exists(perm_file):
                logger.error(f"❌ Permutations file not found: {perm_file}")
                return []
            
            # Construct gotator command
            gotator_cmd = [
                'gotator',
                '-sub', tmp_file_path,
                '-perm', perm_file,
                '-depth', str(self.gotator_depth),
                '-numbers', str(self.gotator_numbers),
                '-mindup',  # Minimize duplicates
                '-adv',     # Advanced mode
                '2> /dev/null'
            ]
            
            logger.info(f"🚀 Running gotator: {' '.join(gotator_cmd)}")
            
            # Run gotator
            result = subprocess.run(
                gotator_cmd,
                capture_output=True,
                text=True,
                timeout=self.gotator_timeout
            )
            
            # Check for errors
            if result.returncode != 0:
                logger.error(f"❌ Gotator failed with return code {result.returncode}")
                if result.stderr:
                    logger.error(f"stderr: {result.stderr}")
                return []
            
            # Parse gotator output (one permutation per line)
            permutations = []
            original_subdomains_set = set(s.strip().lower() for s in subdomains)
            
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                # Exclude empty lines and original inputs
                if line and line.lower() not in original_subdomains_set:
                    permutations.append(line)
            
            # Deduplicate while preserving order
            seen = set()
            unique_permutations = []
            for perm in permutations:
                perm_lower = perm.lower()
                if perm_lower not in seen:
                    seen.add(perm_lower)
                    unique_permutations.append(perm)
            
            logger.info(f"✅ Gotator generated {len(unique_permutations)} unique permutations")
            
            #if result.stderr:
            #    logger.debug(f"Gotator stderr (may contain warnings): {result.stderr[:500]}")
            
            return unique_permutations
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Gotator timed out after {self.gotator_timeout} seconds")
            return []
        except FileNotFoundError:
            logger.error("❌ Gotator command not found. Ensure gotator is installed in the container.")
            logger.error("   Install with: go install github.com/Josue87/gotator@latest")
            return []
        except Exception as e:
            logger.error(f"❌ Error running gotator: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            # Clean up temp subdomain file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    logger.debug(f"🧹 Cleaned up temporary subdomain file: {tmp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {tmp_file_path}: {e}")
            
            # Clean up downloaded permutation file
            if downloaded_perm_file and os.path.exists(downloaded_perm_file):
                try:
                    os.unlink(downloaded_perm_file)
                    logger.debug(f"🧹 Cleaned up downloaded permutation file: {downloaded_perm_file}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup downloaded permutation file {downloaded_perm_file}: {e}")

    def parse_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """
        Parse output (not typically used for orchestrator tasks).
        This is here for completeness and testing purposes.
        
        Orchestrator tasks spawn worker jobs instead of executing commands directly,
        so this method should not be called in production workflows.
        """
        logger.warning("parse_output() called on orchestrator task - this shouldn't happen in production")
        return {
            AssetType.SUBDOMAIN: [],
            AssetType.IP: []
        }

