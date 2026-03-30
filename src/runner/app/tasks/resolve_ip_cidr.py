import json
import logging
from typing import Dict, List, Any, Optional
import base64
import ipaddress
from .base import Task, AssetType, CommandSpec
from models.assets import Domain, Ip
import redis
import os
import requests

logger = logging.getLogger(__name__)

class ResolveIPCIDR(Task):
    name = "resolve_ip_cidr"
    description = "Resolves IP addresses from CIDR blocks using orchestrator pattern with batch job spawning for both DNS resolution and port scanning"
    input_type = AssetType.STRING
    output_types = [AssetType.SUBDOMAIN, AssetType.IP, AssetType.SERVICE]

    # Task parameters:
    # - force_ip (bool): Skip last execution check for individual IPs (default: False)
    #   When True, all IPs from CIDR expansion will be processed regardless of recent execution history
    # - enable_port_scan (bool): Enable port scanning alongside DNS resolution (default: True)
    # - port_scan_timeout (int): Timeout for port scan jobs in seconds (default: 300)

    def __init__(self):
        super().__init__()
        # Initialize Redis connection for offset tracking
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        self.redis_client = redis.from_url(redis_url)

        # Configuration for job management
        self.chunk_size = int(os.getenv('CIDR_CHUNK_SIZE', '25'))  # IPs per spawned job
        self.batch_size = int(os.getenv('CIDR_BATCH_SIZE', '10'))  # Jobs per batch spawn
        self.job_timeout = int(os.getenv('CIDR_JOB_TIMEOUT', '600'))  # Seconds per job
        self.total_timeout = int(os.getenv('CIDR_TOTAL_TIMEOUT', '3600'))  # Total timeout
        
        # Adaptive chunking configuration
        self.adaptive_chunking_enabled = os.getenv('CIDR_ADAPTIVE_CHUNKING', 'true').lower() == 'true'

        # Port scan configuration
        self.enable_port_scan = os.getenv('CIDR_ENABLE_PORT_SCAN', 'true').lower() == 'true'
        self.port_scan_timeout = int(os.getenv('CIDR_PORT_SCAN_TIMEOUT', '300'))  # 5 minutes for quick scans

        # Batch API configuration for IP checking
        # API_BATCH_SIZE: Number of IPs to check per API call (default: 1000)
        # API_BATCH_TIMEOUT: Timeout in seconds for each batch API call (default: 30)

    def _calculate_adaptive_chunk_size(self, total_hosts: int, ip_limit: int) -> int:
        """
        Calculate optimal chunk size based on CIDR size and processing limits.

        Args:
            total_hosts: Total number of hosts in the CIDR
            ip_limit: Maximum IPs to process

        Returns:
            Optimal chunk size for processing
        """
        if not self.adaptive_chunking_enabled:
            return self.chunk_size

        # Adaptive sizing based on CIDR magnitude
        if total_hosts <= 256:  # /24 or smaller
            return max(1, min(self.chunk_size, ip_limit))
        elif total_hosts <= 1024:  # /22
            return min(5, ip_limit)
        elif total_hosts <= 4096:  # /20
            return min(10, ip_limit)
        elif total_hosts <= 16384:  # /18
            return min(25, ip_limit)
        elif total_hosts <= 65536:  # /16
            return min(50, ip_limit)
        else:  # Larger than /16
            return min(100, ip_limit)

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        # For individual IP checking - this will be called per IP by the executor
        # If target is a CIDR, we shouldn't use this method directly
        if '/' in str(target):
            # This is a CIDR - we'll handle IP-level checking in get_command
            return ""
        
        # For individual IPs, create standard hash
        hash_dict = {
            "task": self.name,
            "target": target
        }
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def _get_next_offset(self, cidr: str, params: Optional[Dict] = None) -> int:
        """Get the next offset position for this CIDR"""
        offset_key = f"cidr_offset:{cidr}"
        try:
            stored_offset = self.redis_client.get(offset_key)
            if stored_offset:
                logger.debug(f"stored_offset: {stored_offset}")
                # Decode bytes to string before converting to int
                stored_offset_str = stored_offset.decode('utf-8') if isinstance(stored_offset, bytes) else str(stored_offset)
                return int(stored_offset_str)
        except Exception as e:
            logger.warning(f"Error getting offset for CIDR {cidr}: {e}")
        return 0
    
    def _update_offset(self, cidr: str, new_offset: int, params: Optional[Dict] = None):
        """Update the offset position for this CIDR"""
        offset_key = f"cidr_offset:{cidr}"
        
        try:
            # Check if we've reached the end of the CIDR
            network = ipaddress.ip_network(cidr, strict=False)
            max_hosts = len(list(network.hosts()))
            
            if new_offset >= max_hosts:
                # Reset to 0 for next full cycle
                self.redis_client.set(offset_key, "0")
                logger.info(f"CIDR {cidr} completed ({max_hosts} IPs), reset offset to 0")
            else:
                self.redis_client.set(offset_key, str(new_offset))
                logger.info(f"CIDR {cidr} offset updated to {new_offset}/{max_hosts}")
        except Exception as e:
            logger.error(f"Error updating offset for CIDR {cidr}: {e}")
    
    def _expand_cidr_with_offset(self, cidr: str, offset: int, limit: int) -> List[str]:
        """Expand CIDR starting from offset position"""
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            hosts = list(network.hosts())
            
            # Get slice from offset to offset+limit
            end_pos = min(offset + limit, len(hosts))
            selected_ips = [str(ip) for ip in hosts[offset:end_pos]]
            
            logger.info(f"CIDR {cidr}: extracted {len(selected_ips)} IPs from offset {offset} to {end_pos-1}")
            return selected_ips
            
        except Exception as e:
            logger.error(f"Error expanding CIDR {cidr}: {e}")
            return []
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """This method is no longer used for actual work - just return empty for orchestrator"""
        return ""

    async def generate_commands(
        self,
        input_data: List[Any],
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[CommandSpec]:
        """
        Generate resolve_ip and port_scan commands (interleaved by batch_group).
        Expands CIDRs, filters via API, chunks into resolve_ip and port_scan jobs.
        """
        if not input_data:
            return []

        cidrs_to_process = input_data if isinstance(input_data, list) else [input_data]
        program_name = context.get('program_name', os.getenv('PROGRAM_NAME', 'default'))
        task_def = context.get('task_def')

        force_ip = params.get('force_ip', False)
        ip_limit = params.get('ip_limit', 500)
        max_cidr_size = params.get('max_cidr_size', 65536)
        enable_port_scan = params.get('enable_port_scan', self.enable_port_scan)
        port_scan_timeout = params.get('port_scan_timeout', self.port_scan_timeout)
        if task_def and hasattr(task_def, 'params') and task_def.params:
            force_ip = task_def.params.get('force_ip', force_ip)
            ip_limit = task_def.params.get('ip_limit', ip_limit)
            max_cidr_size = task_def.params.get('max_cidr_size', max_cidr_size)
            enable_port_scan = task_def.params.get('enable_port_scan', enable_port_scan)
            port_scan_timeout = task_def.params.get('port_scan_timeout', port_scan_timeout)

        all_ips = self._prepare_ip_chunks_from_cidrs(
            cidrs_to_process, force_ip, program_name, ip_limit, max_cidr_size
        )
        if not all_ips:
            return []

        resolve_ip_chunks = [
            self.resolve_ip_candidates[i:i + self.chunk_size]
            for i in range(0, len(self.resolve_ip_candidates), self.chunk_size)
        ]
        port_scan_chunks = [
            self.port_scan_candidates[i:i + self.chunk_size]
            for i in range(0, len(self.port_scan_candidates), self.chunk_size)
        ]

        from .resolve_ip import ResolveIP
        from .port_scan import PortScan
        resolve_ip_task = ResolveIP()
        port_scan_task = PortScan()

        resolve_params = {**params, 'timeout': self.job_timeout}
        port_scan_params = {**params, 'timeout': port_scan_timeout}

        command_specs = []
        max_chunks = max(len(resolve_ip_chunks), len(port_scan_chunks) if enable_port_scan else 0)
        for batch_num in range(max_chunks):
            if batch_num < len(resolve_ip_chunks):
                cmd = resolve_ip_task.get_command(resolve_ip_chunks[batch_num], resolve_params)
                if cmd:
                    command_specs.append(
                        CommandSpec(
                            task_name="resolve_ip",
                            command=cmd,
                            params=resolve_params,
                            batch_group=batch_num
                        )
                    )
            if enable_port_scan and batch_num < len(port_scan_chunks):
                cmd = port_scan_task.get_command(port_scan_chunks[batch_num], port_scan_params)
                if cmd:
                    command_specs.append(
                        CommandSpec(
                            task_name="port_scan",
                            command=cmd,
                            params=port_scan_params,
                            batch_group=batch_num
                        )
                    )

        logger.info(f"📦 Generated {len(command_specs)} commands ({len(resolve_ip_chunks)} resolve_ip, {len(port_scan_chunks) if enable_port_scan else 0} port_scan)")
        return command_specs

    def _determine_task_type_from_output(self, task_id: str, output: Any) -> str:
        """Determine the task type from the output or task_id"""
        # Try to determine from task_id first
        if "resolve_ip" in task_id.lower():
            return "resolve_ip"
        elif "port_scan" in task_id.lower():
            return "port_scan"
        
        # Try to determine from output content
        if isinstance(output, str):
            if "dnsx" in output.lower() or "ptr" in output.lower():
                return "resolve_ip"
            elif "nmap" in output.lower() or "port" in output.lower():
                return "port_scan"
        elif isinstance(output, dict) and 'output' in output:
            inner_output = output['output']
            if isinstance(inner_output, str):
                if "dnsx" in inner_output.lower() or "ptr" in inner_output.lower():
                    return "resolve_ip"
                elif "nmap" in inner_output.lower() or "port" in inner_output.lower():
                    return "port_scan"
        
        # Default to resolve_ip if we can't determine
        logger.warning(f"Could not determine task type for {task_id}, defaulting to resolve_ip")
        return "resolve_ip"

    def _aggregate_port_scan_results(self, outputs: Dict[str, Any]) -> Dict[AssetType, List[Any]]:
        """
        Aggregate results from WorkerJobManager port_scan job outputs.
        
        Args:
            outputs: Dict mapping task_id to raw command output (string or dict)
            
        Returns:
            Dict mapping AssetType to list of assets
        """
        all_services = []

        logger.info(f"🔍 Aggregating port_scan results from {len(outputs)} WorkerJobManager jobs")

        for task_id, raw_output in outputs.items():
            try:
                logger.debug(f"Processing port_scan output from task {task_id}, type: {type(raw_output)}")
                
                # Import port_scan task for output parsing
                from .port_scan import PortScan
                port_scan_task = PortScan()
                
                # Parse the output from each spawned job
                if isinstance(raw_output, str):
                    parsed = port_scan_task.parse_output(raw_output)
                elif isinstance(raw_output, dict) and 'output' in raw_output:
                    inner_output = raw_output['output']
                    if isinstance(inner_output, str):
                        parsed = port_scan_task.parse_output(inner_output)
                    else:
                        parsed = port_scan_task.parse_output(str(inner_output))
                else:
                    parsed = port_scan_task.parse_output(str(raw_output))

                if parsed and AssetType.SERVICE in parsed:
                    all_services.extend(parsed[AssetType.SERVICE])
                    logger.debug(f"Added {len(parsed[AssetType.SERVICE])} services from task {task_id}")

            except Exception as e:
                logger.error(f"Error processing port_scan output from WorkerJobManager job {task_id}: {e}")
                logger.exception(f"Full error details for task {task_id}")
                continue

        logger.info(f"✅ WorkerJobManager port_scan aggregated: {len(all_services)} services from {len(outputs)} jobs")

        return {
            AssetType.SERVICE: all_services
        }
    
    def _aggregate_worker_job_manager_results(self, outputs: Dict[str, Any]) -> Dict[AssetType, List[Any]]:
        """
        Aggregate results from WorkerJobManager resolve_ip job outputs.
        
        Args:
            outputs: Dict mapping task_id to raw command output (string or dict)
            
        Returns:
            Dict mapping AssetType to list of assets
        """
        all_domains = []
        all_ips = set()
        all_processed_ips = []

        #logger.info(f"🔍 Aggregating results from {len(outputs)} WorkerJobManager jobs")

        for task_id, raw_output in outputs.items():
            try:
                logger.debug(f"Processing output from task {task_id}, type: {type(raw_output)}")
                
                # Handle different output formats from WorkerJobManager
                if raw_output is None:
                    logger.debug(f"None output from task {task_id}")
                    continue
                
                # Handle string output (raw command output)
                if isinstance(raw_output, str):
                    if not raw_output.strip():
                        logger.debug(f"Empty string output from task {task_id}")
                        continue
                    
                    # Parse the raw dnsx output
                    try:
                        output_json = json.loads(raw_output)
                        logger.debug(f"Successfully parsed JSON from task {task_id} with {len(output_json)} entries")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON from task {task_id}: {e}")
                        logger.debug(f"Raw output preview: {raw_output[:200]}...")
                        continue
                
                # Handle dict output (already parsed or wrapped)
                elif isinstance(raw_output, dict):
                    # Check if it's wrapped output format (output inside wrapper dict)
                    if 'output' in raw_output:
                        inner_output = raw_output['output']

                        # Debug the inner output
                        if isinstance(inner_output, str):
                            # Check for common JSON parsing issues
                            if inner_output.strip().startswith('Error'):
                                logger.warning(f"Inner output contains error message: {inner_output[:500]}")
                                # Try to extract JSON after the error message
                                lines = inner_output.split('\n')
                                json_lines = []
                                found_json_start = False
                                for line in lines:
                                    if line.strip().startswith('{') or line.strip().startswith('['):
                                        found_json_start = True
                                    if found_json_start:
                                        json_lines.append(line)

                                if json_lines:
                                    json_content = '\n'.join(json_lines)
                                    logger.debug(f"Extracted JSON content after error: {json_content[:200]}...")
                                    try:
                                        output_json = json.loads(json_content)
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Failed to parse extracted JSON from task {task_id}: {e}")
                                        continue
                                else:
                                    logger.error(f"No JSON found after error message in task {task_id}")
                                    continue
                            else:
                                try:
                                    output_json = json.loads(inner_output)
                                except json.JSONDecodeError as e:
                                    logger.error(f"Failed to parse wrapped JSON from task {task_id}: {e}")
                                    logger.error(f"Raw inner output: {repr(inner_output[:500])}")
                                    continue
                        else:
                            output_json = inner_output
                    else:
                        # Direct dict output (already parsed)
                        output_json = raw_output
                
                else:
                    logger.warning(f"Unexpected output type from task {task_id}: {type(raw_output)}")
                    continue
                
                # Process the parsed JSON using existing method
                parsed = self._parse_dnsx_json(output_json)
                if parsed:
                    logger.debug(f"Parsed {len(parsed.get(AssetType.IP, []))} IPs and {len(parsed.get(AssetType.SUBDOMAIN, []))} domains from task {task_id}")
                    all_domains.extend(parsed.get(AssetType.SUBDOMAIN, []))
                    all_ips.update(parsed.get(AssetType.IP, []))

                    # Track IPs that were processed for timestamp updates
                    for ip in parsed.get(AssetType.IP, []):
                        if hasattr(ip, 'ip'):
                            all_processed_ips.append(ip.ip)

            except Exception as e:
                logger.error(f"Error processing output from WorkerJobManager job {task_id}: {e}")
                logger.exception(f"Full error details for task {task_id}")
                continue

        # Convert IPs set to list
        ip_list = list(all_ips)
        logger.info(f"✅ WorkerJobManager aggregated: {len(all_domains)} domains, {len(ip_list)} unique IPs from {len(outputs)} jobs")

        return {
            AssetType.SUBDOMAIN: all_domains,
            AssetType.IP: ip_list
        }
    
    def _filter_recently_executed_ips(self, ips: List[str], force: bool = False) -> List[str]:
        """Filter out IPs that were recently executed"""
        if force:
            logger.info("Force flag is true, skipping last execution check for IPs")
            return ips
        
        from datetime import datetime, timedelta
        
        filtered_ips = []
        threshold_hours = self.get_last_execution_threshold()
        
        for ip in ips:
            # Generate timestamp hash for this individual IP
            timestamp_hash = self.get_timestamp_hash(ip)
            if not timestamp_hash:
                # If no hash (shouldn't happen for IPs), include it
                filtered_ips.append(ip)
                continue
            
            try:
                last_execution = self.redis_client.get(timestamp_hash)
                if last_execution:
                    # Decode bytes to string before converting to float
                    last_execution_str = last_execution.decode('utf-8') if isinstance(last_execution, bytes) else str(last_execution)
                    last_execution_time = datetime.fromtimestamp(float(last_execution_str))
                    time_since_last = datetime.now() - last_execution_time
                    
                    if time_since_last < timedelta(hours=threshold_hours):
                        logger.debug(f"IP {ip} was executed {time_since_last.total_seconds()/3600:.1f} hours ago, skipping")
                        continue
                
                # IP is eligible for processing
                filtered_ips.append(ip)
                
            except Exception as e:
                logger.debug(f"Error checking last execution for IP {ip}: {e}")
                # If there's an error, include the IP to be safe
                filtered_ips.append(ip)
        
        logger.info(f"Filtered {len(ips)} candidate IPs to {len(filtered_ips)} eligible IPs")
        return filtered_ips

    def _prepare_ip_chunks_from_cidrs(self, cidrs_to_process: List[str], force_ip: bool = False, program_name: str = "", ip_limit: int = 500, max_cidr_size: int = 65536) -> List[str]:
        """Prepare IP chunks from CIDR blocks using the original expansion logic"""

        force = force_ip  # Use the configurable force_ip parameter

        all_ips = []
        total_cidrs = len(cidrs_to_process)
        logger.info(f"Starting CIDR processing: {total_cidrs} CIDRs, ip_limit={ip_limit}, force={force}")

        for idx, cidr in enumerate(cidrs_to_process):
            cidr = str(cidr).strip()

            try:
                # Validate CIDR
                network = ipaddress.ip_network(cidr, strict=False)
                total_hosts = len(list(network.hosts()))

                # Safety check for very large CIDRs
                if total_hosts > max_cidr_size:
                    logger.warning(f"CIDR {cidr} too large ({total_hosts} IPs), skipping")
                    continue

                logger.info(f"Processing CIDR {idx + 1}/{total_cidrs}: {cidr} ({total_hosts} IPs)")
                # Get current offset for this CIDR
                offset = self._get_next_offset(cidr)

                # Calculate how many IPs we can potentially process from this CIDR
                remaining_limit = ip_limit - len(all_ips)
                if remaining_limit <= 0:
                    break

                # Progressive processing for large CIDRs to manage memory usage
                large_cidr_threshold = int(os.getenv('CIDR_LARGE_THRESHOLD', '10000'))  # 10k IPs
                if total_hosts > large_cidr_threshold:
                    logger.info(f"Large CIDR detected: {cidr} ({total_hosts} IPs), using progressive processing")
                    processed_ips, remaining_limit = self._process_large_cidr_progressively(
                        cidr, offset, remaining_limit, force, program_name, total_hosts
                    )
                    all_ips.extend(processed_ips)
                    continue  # Skip normal processing for large CIDRs

                # Expand CIDR from current offset with a larger batch to filter from
                # We expand more than the limit to account for filtering out recently executed IPs
                # For large CIDRs, use adaptive batch sizing to avoid memory issues
                max_expand_size = int(os.getenv('CIDR_MAX_EXPAND_SIZE', '5000'))  # Configurable max
                adaptive_expand = min(remaining_limit * 3, max_expand_size)
                expand_batch_size = max(adaptive_expand, 100)  # Minimum 100 IPs for efficiency
                candidate_ips = self._expand_cidr_with_offset(cidr, offset, expand_batch_size)

                if not candidate_ips:
                    logger.warning(f"No IPs extracted from CIDR {cidr} at offset {offset}")
                    continue

                # Filter out recently executed IPs
                filtered_ips = candidate_ips #self._filter_recently_executed_ips(candidate_ips, force)

                # Take only what we need up to the remaining limit
                ips_to_use = filtered_ips[:remaining_limit]

                if ips_to_use:
                    all_ips.extend(ips_to_use)
                    logger.info(f"Added {len(ips_to_use)} IPs from CIDR {cidr} (filtered {len(candidate_ips) - len(filtered_ips)} recently executed)")

                    # Update offset based on how many candidate IPs we processed (not just used)
                    # This ensures we move forward through the CIDR even if some IPs were filtered
                    new_offset = offset + len(candidate_ips)
                    self._update_offset(cidr, new_offset)
                else:
                    # All IPs in this batch were recently executed
                    logger.info(f"All {len(candidate_ips)} IPs from CIDR {cidr} were recently executed, advancing offset")
                    new_offset = offset + len(candidate_ips)
                    self._update_offset(cidr, new_offset)

            except ValueError as e:
                logger.error(f"Invalid CIDR block: {cidr} - {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing CIDR {cidr}: {e}")
                continue

        # Check which IPs are already resolved using the API (for resolve_ip jobs only)
        resolve_ip_candidates = all_ips.copy()
        logger.debug(f"Program name for API checks: '{program_name}' (type: {type(program_name)})")
        logger.debug(f"Force flag: {force}, will check API: {program_name and not force}")
        if program_name and not force:
            logger.info(f"Checking API for already resolved IPs (with PTR records) for resolve_ip jobs (program: {program_name})")
            logger.debug(f"Calling _check_resolved_ips_api with {len(all_ips)} IPs and program '{program_name}'")
            resolved_ips = self._check_resolved_ips_api(all_ips, program_name)
            logger.debug(f"_check_resolved_ips_api returned {len(resolved_ips)} resolved IPs")

            if resolved_ips:
                # Filter out already resolved IPs (with PTR records) for resolve_ip jobs only
                original_count = len(resolve_ip_candidates)
                resolve_ip_candidates = [ip for ip in all_ips if ip not in resolved_ips]
                filtered_count = original_count - len(resolve_ip_candidates)
                logger.info(f"Filtered out {filtered_count} already resolved IPs (with PTR records) for resolve_ip jobs, {len(resolve_ip_candidates)} IPs remain")
            else:
                logger.info("No already resolved IPs (with PTR records) found in API for resolve_ip jobs")
        elif force:
            logger.info(f"Force IP mode enabled: skipping API check for resolve_ip jobs, will process all {len(all_ips)} IPs")
        else:
            logger.info(f"No program name available: skipping API check for resolve_ip jobs, will process all {len(all_ips)} IPs")
        
        logger.debug(f"Resolve IP candidates after API check: {len(resolve_ip_candidates)} IPs")

        # Check which IPs already have services using the API (for port_scan jobs only)
        port_scan_candidates = all_ips.copy()
        logger.debug(f"Force flag for port_scan: {force}, will check API: {program_name and not force}")
        if program_name and not force:
            logger.info(f"Checking API for IPs with existing services for port_scan jobs (program: {program_name})")
            logger.debug(f"Calling _check_ips_with_services_api with {len(all_ips)} IPs and program '{program_name}'")
            ips_with_services = self._check_ips_with_services_api(all_ips, program_name)
            logger.debug(f"_check_ips_with_services_api returned {len(ips_with_services)} IPs with services")

            if ips_with_services:
                # Filter out IPs that already have services for port_scan jobs only
                original_count = len(port_scan_candidates)
                port_scan_candidates = [ip for ip in all_ips if ip not in ips_with_services]
                filtered_count = original_count - len(port_scan_candidates)
                logger.info(f"Filtered out {filtered_count} IPs with existing services for port_scan jobs, {len(port_scan_candidates)} IPs remain")
            else:
                logger.info("No IPs with existing services found in API for port_scan jobs")
        elif force:
            logger.info(f"Force IP mode enabled: skipping API check for port_scan jobs, will process all {len(all_ips)} IPs")
        else:
            logger.info(f"No program name available: skipping API check for port_scan jobs, will process all {len(all_ips)} IPs")
        
        logger.debug(f"Port scan candidates after API check: {len(port_scan_candidates)} IPs")

        # Final progress summary
        logger.info("CIDR processing complete:")
        logger.info(f"  - Total IPs from {len(cidrs_to_process)} CIDR blocks: {len(all_ips)}")
        logger.info(f"  - IPs for resolve_ip jobs: {len(resolve_ip_candidates)}")
        logger.info(f"  - IPs for port_scan jobs: {len(port_scan_candidates)}")
        
        if ip_limit > 0:
            resolve_ip_progress = (len(resolve_ip_candidates) / ip_limit * 100)
            port_scan_progress = (len(port_scan_candidates) / ip_limit * 100)
            logger.info(f"Progress: resolve_ip {len(resolve_ip_candidates)}/{ip_limit} IPs ({resolve_ip_progress:.1f}%), port_scan {len(port_scan_candidates)}/{ip_limit} IPs ({port_scan_progress:.1f}%)")

        # Store the candidate lists for use in job spawning
        self.resolve_ip_candidates = resolve_ip_candidates
        self.port_scan_candidates = port_scan_candidates

        return all_ips

    def _process_large_cidr_progressively(self, cidr: str, offset: int, ip_limit: int,
                                         force: bool, program_name: str, total_hosts: int) -> tuple:
        """
        Process large CIDRs using progressive chunking to manage memory usage.

        Args:
            cidr: The CIDR block to process
            offset: Current processing offset
            ip_limit: Maximum IPs to process
            force: Force processing flag
            program_name: Program name for API lookups
            total_hosts: Total number of hosts in the CIDR

        Returns:
            Tuple of (processed_ips_list, remaining_ip_limit)
        """
        logger.info(f"Processing large CIDR {cidr} progressively: {total_hosts} total IPs")

        # Use smaller chunks for large CIDRs to manage memory
        progressive_chunk_size = int(os.getenv('CIDR_PROGRESSIVE_CHUNK_SIZE', '1000'))
        max_chunks_per_iteration = int(os.getenv('CIDR_MAX_CHUNKS_PER_ITERATION', '10'))

        processed_this_cidr = 0
        remaining_limit = ip_limit
        processed_ips = []
        iteration_count = 0

        logger.info(f"Starting progressive processing: chunk_size={progressive_chunk_size}, "
                   f"max_iterations={max_chunks_per_iteration}")

        # Process in progressive chunks
        while remaining_limit > 0 and offset < total_hosts:
            # Calculate how many IPs to process in this iteration
            chunk_size = min(progressive_chunk_size, remaining_limit)
            min(offset + (progressive_chunk_size * max_chunks_per_iteration), total_hosts)
            candidate_ips = self._expand_cidr_with_offset(cidr, offset, chunk_size)

            if not candidate_ips:
                logger.warning(f"No more IPs in CIDR {cidr} at offset {offset}")
                break

            # Filter out recently executed IPs
            filtered_ips = candidate_ips #self._filter_recently_executed_ips(candidate_ips, force)
            ips_to_use = filtered_ips[:remaining_limit]

            iteration_count += 1
            progress_percent = (offset / total_hosts * 100) if total_hosts > 0 else 0

            if ips_to_use:
                # Add processed IPs to our collection
                processed_ips.extend(ips_to_use)
                logger.info(f"Progressive iteration {iteration_count}: processed {len(ips_to_use)} IPs "
                          f"(offset {offset}-{offset + len(candidate_ips) - 1}, {progress_percent:.1f}% complete)")
                processed_this_cidr += len(ips_to_use)
                remaining_limit -= len(ips_to_use)

                # Update offset for next iteration
                new_offset = offset + len(candidate_ips)
                self._update_offset(cidr, new_offset)
            else:
                # All IPs in this chunk were filtered out
                logger.info(f"Progressive iteration {iteration_count}: all {len(candidate_ips)} IPs filtered "
                          f"(offset {offset}-{offset + len(candidate_ips) - 1}, {progress_percent:.1f}% complete)")
                new_offset = offset + len(candidate_ips)
                self._update_offset(cidr, new_offset)

            offset = new_offset

            # Safety check to prevent infinite loops
            if offset >= total_hosts:
                logger.info(f"Reached end of CIDR {cidr} at offset {offset}")
                break

        # Final summary for progressive processing
        completion_percent = (offset / total_hosts * 100) if total_hosts > 0 else 100
        logger.info(f"Progressive processing complete for CIDR {cidr}:")
        logger.info(f"  - Processed: {processed_this_cidr} IPs")
        logger.info(f"  - Iterations: {iteration_count}")
        logger.info(f"  - Progress: {completion_percent:.1f}% of CIDR ({offset}/{total_hosts} IPs)")
        logger.info(f"  - Remaining IP limit: {remaining_limit}")

        return processed_ips, remaining_limit

    def update_ip_timestamps(self, processed_ips: List[str]):
        """Update last execution timestamps for individual IPs that were processed"""
        from datetime import datetime

        current_time = datetime.now().timestamp()

        for ip in processed_ips:
            timestamp_hash = self.get_timestamp_hash(ip)
            if timestamp_hash:
                try:
                    self.redis_client.set(timestamp_hash, str(current_time))
                    #logger.debug(f"Updated last execution timestamp for IP {ip}")
                except Exception as e:
                    logger.warning(f"Error updating timestamp for IP {ip}: {e}")
    
    def parse_output(self, output: str, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse dnsx output into Domain and IP assets (for individual spawned jobs)"""
        domains = []
        ips = set()  # Use set to deduplicate IPs

        try:
            output_json = json.loads(output)
            for ip, data in output_json.items():
                if ip and data.get("dnsx", None):
                    self._process_data(ip, data, domains, ips)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing dnsx output: {e}")
            return {AssetType.SUBDOMAIN: [], AssetType.IP: []}
        except Exception as e:
            logger.error(f"Error processing dnsx output: {e}")
            return {AssetType.SUBDOMAIN: [], AssetType.IP: []}

        # Convert IPs set to list
        ip_list = list(ips)
        logger.info(f"Found {len(domains)} domains and {len(ip_list)} unique IPs")

        return {
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: ip_list
        }

    def _parse_dnsx_json(self, output_json: Dict[str, Any]) -> Dict[AssetType, List[Any]]:
        """
        Parse dnsx JSON output (already parsed dict) into Domain and IP assets.
        This is used by the orchestrator to process outputs from spawned jobs.
        """
        domains = []
        ips = set()  # Use set to deduplicate IPs

        try:
            #logger.info(f"🔍 DEBUG: _parse_dnsx_json processing {len(output_json)} IP entries")
            # Process each IP entry in the JSON
            for ip, data in output_json.items():
                if ip and data.get("dnsx", None):
                    self._process_data(ip, data, domains, ips)
        except Exception as e:
            logger.error(f"Error processing dnsx JSON data: {e}")
            return {AssetType.SUBDOMAIN: [], AssetType.IP: []}

        # Convert sets to lists for return
        ip_list = list(ips)
        #logger.info(f"🔍 DEBUG: _parse_dnsx_json returning {len(domains)} domains and {len(ip_list)} unique IPs")
        return {
            AssetType.SUBDOMAIN: domains,
            AssetType.IP: ip_list
        }

    def _check_resolved_ips_api(self, ips: List[str], program_name: str) -> set:
        """
        Check which IPs are already resolved by fetching all resolved IPs (with PTR records) 
        for the program using the search endpoint with pagination and filtering locally.

        Args:
            ips: List of IP addresses to check
            program_name: Program name to filter by

        Returns:
            Set of IPs that are already resolved (have PTR records)
        """
        resolved_ips = set()

        if not ips:
            return resolved_ips

        try:
            # Get API configuration
            api_url = os.getenv('API_URL', 'http://api:8000')
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')

            if not api_url:
                logger.warning("API_URL not configured, cannot check resolved IPs")
                return resolved_ips

            if not internal_api_key:
                logger.warning("INTERNAL_SERVICE_API_KEY not configured, cannot check resolved IPs")
                return resolved_ips

            # Use search endpoint to get all resolved IPs (IPs with PTR records) for the program
            search_api_url = f"{api_url.rstrip('/')}/assets/ip/search"
            headers = {
                'Authorization': f'Bearer {internal_api_key}',
                'Content-Type': 'application/json'
            }

            logger.info(f"Fetching all resolved IPs (with PTR records) for program '{program_name}' to check against {len(ips)} CIDR IPs")

            page = 1
            page_size = 1000  # Use larger page size for efficiency
            all_fetched_ips = []

            try:
                while True:
                    # Prepare search request for IPs with PTR records
                    request_data = {
                        "program": program_name,
                        "has_ptr": True,  # Only get IPs that have PTR records (resolved IPs)
                        "sort_by": "ip_address",
                        "sort_dir": "asc",
                        "page": page,
                        "page_size": page_size
                    }

                    response = requests.post(search_api_url, json=request_data, headers=headers, timeout=60)

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("status") == "success":
                            # Extract IP addresses from the items
                            items = result.get("items", [])
                            page_ips = [item.get("ip_address") for item in items if item.get("ip_address")]
                            all_fetched_ips.extend(page_ips)

                            # Check if we have more pages
                            pagination = result.get("pagination", {})
                            total_pages = pagination.get("total_pages", 1)
                            current_page = pagination.get("current_page", 1)

                            if current_page >= total_pages:
                                break  # No more pages

                            page += 1  # Next page
                        else:
                            logger.warning(f"Search API response not successful: {result}")
                            break
                    else:
                        logger.warning(f"Search API request failed with status {response.status_code}: {response.text}")
                        break

                # Update resolved_ips set with all fetched IPs
                resolved_ips.update(all_fetched_ips)
                logger.info(f"Found {len(all_fetched_ips)} total resolved IPs (with PTR records) in program '{program_name}' across {page} pages")

            except requests.exceptions.Timeout:
                logger.warning("Timeout fetching resolved IPs from search API")
                return set()
            except Exception as e:
                logger.error(f"Error fetching resolved IPs from search API: {e}")
                return set()

            # Now filter the CIDR IPs against the resolved IPs locally
            cidr_resolved_ips = set()
            for ip in ips:
                if ip in resolved_ips:
                    cidr_resolved_ips.add(ip)

            logger.info(f"Local filtering completed: {len(cidr_resolved_ips)} already resolved IPs (with PTR records) found out of {len(ips)} CIDR IPs")
            return cidr_resolved_ips

        except Exception as e:
            logger.error(f"Error in _check_resolved_ips_api: {e}")
            return set()

    def _check_ips_with_services_api(self, ips: List[str], program_name: str) -> set:
        """
        Check which IPs already have services by fetching all services for the program
        using the search endpoint with pagination and filtering locally.

        Args:
            ips: List of IP addresses to check
            program_name: Program name to filter by

        Returns:
            Set of IPs that already have services
        """
        ips_with_services = set()

        if not ips:
            return ips_with_services

        try:
            # Get API configuration
            api_url = os.getenv('API_URL', 'http://api:8000')
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')

            if not api_url:
                logger.warning("API_URL not configured, cannot check IPs with services")
                return ips_with_services

            if not internal_api_key:
                logger.warning("INTERNAL_SERVICE_API_KEY not configured, cannot check IPs with services")
                return ips_with_services

            # Use search endpoint to get all services for the program
            search_api_url = f"{api_url.rstrip('/')}/assets/service/search"
            headers = {
                'Authorization': f'Bearer {internal_api_key}',
                'Content-Type': 'application/json'
            }

            logger.info(f"Fetching all services for program '{program_name}' to check against {len(ips)} CIDR IPs")

            page = 1
            page_size = 1000  # Use larger page size for efficiency
            all_fetched_services = []

            try:
                while True:
                    # Prepare search request for all services in the program
                    request_data = {
                        "program": program_name,
                        "sort_by": "ip",
                        "sort_dir": "asc",
                        "page": page,
                        "page_size": page_size
                    }

                    response = requests.post(search_api_url, json=request_data, headers=headers, timeout=60)

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("status") == "success":
                            # Extract services from the items
                            items = result.get("items", [])
                            all_fetched_services.extend(items)

                            # Check if we have more pages
                            pagination = result.get("pagination", {})
                            total_pages = pagination.get("total_pages", 1)
                            current_page = pagination.get("current_page", 1)

                            if current_page >= total_pages:
                                break  # No more pages

                            page += 1  # Next page
                        else:
                            logger.warning(f"Search API response not successful: {result}")
                            break
                    else:
                        logger.warning(f"Search API request failed with status {response.status_code}: {response.text}")
                        break

                # Extract unique IPs from all fetched services
                all_service_ips = set()
                for service in all_fetched_services:
                    ip = service.get("ip")
                    if ip:
                        all_service_ips.add(ip)

                logger.info(f"Found {len(all_fetched_services)} total services with {len(all_service_ips)} unique IPs in program '{program_name}' across {page} pages")

            except requests.exceptions.Timeout:
                logger.warning("Timeout fetching services from search API")
                return set()
            except Exception as e:
                logger.error(f"Error fetching services from search API: {e}")
                return set()

            # Now filter the CIDR IPs against the service IPs locally
            cidr_ips_with_services = set()
            for ip in ips:
                if ip in all_service_ips:
                    cidr_ips_with_services.add(ip)

            logger.info(f"Local filtering completed: {len(cidr_ips_with_services)} IPs with existing services found out of {len(ips)} CIDR IPs")
            return cidr_ips_with_services

        except Exception as e:
            logger.error(f"Error in _check_ips_with_services_api: {e}")
            return set()

    def parse_output_for_orchestrator(self, aggregated_outputs: Dict[str, Any]) -> Dict[AssetType, List[Any]]:
        """
        Parse aggregated outputs from multiple spawned resolve_ip jobs.
        This method is called by the base class aggregate_job_results method.
        """
        all_domains = []
        all_ips = set()
        all_processed_ips = []

        logger.info(f"Parsing aggregated outputs from {len(aggregated_outputs)} spawned jobs")

        # Debug: Log what outputs we received
        #logger.info(f"🔍 DEBUG: Received outputs from task_ids: {list(aggregated_outputs.keys())}")

        for task_id, output in aggregated_outputs.items():
            try:
                # Parse the output from each spawned job
                # The output is a wrapper dict with metadata, actual data is in 'output' key
                if isinstance(output, dict) and 'output' in output:
                    # Extract the actual dnsx data from the wrapper
                    dnsx_data = output['output']
                    if isinstance(dnsx_data, str):
                        try:
                            output_json = json.loads(dnsx_data)
                            #logger.info(f"🔍 DEBUG: Successfully parsed JSON with {len(output_json)} IPs")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON string for {task_id}: {e}")
                            logger.debug(f"dnsx_data: {dnsx_data}")
                            continue
                    else:
                        output_json = dnsx_data
                else:
                    # Fallback for unexpected formats
                    output_json = output

                parsed = self._parse_dnsx_json(output_json)
                if parsed:
                    #logger.info(f"🔍 DEBUG: Parsed {len(parsed.get(AssetType.IP, []))} IPs and {len(parsed.get(AssetType.SUBDOMAIN, []))} domains from {task_id}")
                    all_domains.extend(parsed.get(AssetType.SUBDOMAIN, []))
                    all_ips.update(parsed.get(AssetType.IP, []))

                    # Track IPs that were processed for timestamp updates
                    for ip in parsed.get(AssetType.IP, []):
                        if hasattr(ip, 'ip'):
                            all_processed_ips.append(ip.ip)

            except Exception as e:
                logger.error(f"Error parsing output from spawned job {task_id}: {e}")
                continue

        # Update timestamps for all processed IPs
        if all_processed_ips:
            logger.info(f"Updating timestamps for {len(all_processed_ips)} processed IPs")
            self.update_ip_timestamps(all_processed_ips)

        # Convert IPs set to list
        ip_list = list(all_ips)
        logger.info(f"Orchestrator aggregated: {len(all_domains)} domains, {len(ip_list)} unique IPs from {len(aggregated_outputs)} jobs")

        return {
            AssetType.SUBDOMAIN: all_domains,
            AssetType.IP: ip_list
        }
    
    def _process_data(self, input_ip, data, domains, ips):
        """Process a single data entry and add to domains and IPs collections"""
        dnsx_data = data.get("dnsx")

        # Extract IP information
        ip_address = dnsx_data.get('host', '')
        if ip_address:
            # Extract PTR records (domain names) for the IP
            ptr_records = dnsx_data.get('ptr', [])

            # Only create IP object if PTR records exist
            if ptr_records:
                # Create IP object with PTR records
                service_provider = data.get('provider', None)
                ip_obj = Ip(
                    ip=ip_address,
                    ptr=ptr_records[0] if len(ptr_records) > 0 else None,
                    service_provider=service_provider
                )
                ips.add(ip_obj)

            # Create Domain objects for each PTR record
            for domain_name in ptr_records:
                domain = Domain(
                    name=domain_name,
                    cname=None
                )
                domains.append(domain)

    def _aggregate_parsed_worker_job_manager_results(self, parsed_outputs: Dict[str, Dict[AssetType, List[Any]]]) -> Dict[AssetType, List[Any]]:
        """
        Aggregate parsed results from WorkerJobManager resolve_ip jobs.

        Args:
            parsed_outputs: Dict mapping task_id to parsed assets from resolve_ip.parse_output()

        Returns:
            Dict mapping AssetType to list of assets
        """
        all_domains = []
        all_ips = set()
        all_processed_ips = []

        #logger.info(f"🔍 Aggregating parsed results from {len(parsed_outputs)} WorkerJobManager jobs")

        for task_id, parsed_result in parsed_outputs.items():
            try:
                logger.debug(f"Processing parsed result from task {task_id}: {len(parsed_result)} asset types")

                # Extract domains and IPs from parsed result
                if AssetType.SUBDOMAIN in parsed_result:
                    domains = parsed_result[AssetType.SUBDOMAIN]
                    all_domains.extend(domains)
                    logger.debug(f"Added {len(domains)} domains from task {task_id}")

                if AssetType.IP in parsed_result:
                    ips = parsed_result[AssetType.IP]
                    all_ips.update(ips)
                    logger.debug(f"Added {len(ips)} IPs from task {task_id}")

                    # Track IPs that were processed for timestamp updates
                    for ip in ips:
                        if hasattr(ip, 'ip'):
                            all_processed_ips.append(ip.ip)

            except Exception as e:
                logger.error(f"Error processing parsed result from task {task_id}: {e}")
                logger.exception(f"Full error details for task {task_id}")
                continue

        # Convert IPs set to list
        ip_list = list(all_ips)
        logger.info(f"✅ Parsed aggregation: {len(all_domains)} domains, {len(ip_list)} unique IPs from {len(parsed_outputs)} jobs")

        return {
            AssetType.SUBDOMAIN: all_domains,
            AssetType.IP: ip_list
        }