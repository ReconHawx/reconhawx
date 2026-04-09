from typing import Dict, List, Optional, Any, Union
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import os
import requests
import asyncio
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# Asset models
class Ip:
    def __init__(self, ip: str, ptr: Optional[List[str]] = None):
        self.ip = ip
        self.ptr = ptr or []
    
    def to_dict(self):
        return {
            "ip": self.ip,
            "ptr": self.ptr
        }
    
    def __hash__(self):
        return hash(self.ip)  # Hash based on IP address only
    
    def __eq__(self, other):
        if not isinstance(other, Ip):
            return False
        return self.ip == other.ip  # Compare based on IP address only

class Service:
    def __init__(self, ip: str, port: int, protocol: str, service: str, banner: Optional[str] = None, program_name: Optional[str] = None):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.service = service
        self.banner = banner
        self.program_name = program_name
    
    def to_dict(self):
        return {
            "ip": self.ip,
            "port": self.port,
            "protocol": self.protocol,
            "service": self.service,
            "banner": self.banner,
            "program_name": self.program_name
        }

# Input/Output types for tasks
class AssetType(Enum):
    SUBDOMAIN = "subdomain"
    IP = "ip"
    STRING = "string"  # For simple string inputs/outputs
    SERVICE = "service"
    URL = "url"
    CERTIFICATE = "certificate"
    SCREENSHOT = "screenshot"
    APEX_DOMAIN = "apex_domain"

class FindingType(Enum):
    NUCLEI = "nuclei"
    TYPOSQUAT_DOMAIN = "typosquat_domain"
    TYPOSQUAT_URL = "typosquat_url"
    TYPOSQUAT_SCREENSHOT = "typosquat_screenshot"
    BROKEN_LINK = "broken_link"
    WPSCAN = "wpscan"


@dataclass
class CommandSpec:
    """Specification for a command to be executed by a worker job."""
    task_name: str
    command: str
    params: Optional[Dict[str, Any]] = None
    batch_group: Optional[int] = None  # For interleaved spawning (e.g. resolve_ip_cidr)


class TaskParameterManager:
    """Centralized parameter management for tasks"""
    
    def __init__(self):
        self.api_url = os.getenv("API_URL", "http://data-api:8000")
        self.internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
        
        # Debug: Log TaskParameterManager initialization
        logger.info("=== TaskParameterManager Debug ===")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Internal API key present: {bool(self.internal_api_key)}")
        if self.internal_api_key:
            logger.info(f"Internal API key length: {len(self.internal_api_key)}")
            logger.info(f"Internal API key first 10 chars: {self.internal_api_key[:10]}...")
        logger.info("=== End TaskParameterManager Debug ===")
        
        self._parameter_cache = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._cache_timestamps = {}
    
    def _get_cached_parameters(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get parameters from cache if still valid"""
        if task_name in self._parameter_cache:
            timestamp = self._cache_timestamps.get(task_name)
            if timestamp and (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return self._parameter_cache[task_name]
        return None
    
    def _set_cached_parameters(self, task_name: str, parameters: Dict[str, Any]):
        """Cache parameters with timestamp"""
        self._parameter_cache[task_name] = parameters
        self._cache_timestamps[task_name] = datetime.now()
    
    def get_task_parameters(self, task_name: str) -> Dict[str, Any]:
        """
        Fetch task parameters from the API with caching
        
        Args:
            task_name: Name of the recon task
            
        Returns:
            Dictionary containing task parameters with defaults if not found
        """
        # Check cache first
        cached_params = self._get_cached_parameters(task_name)
        if cached_params:
            return cached_params
        
        try:
            # Fetch from API with internal service authentication
            headers = {}
            if self.internal_api_key:
                headers['Authorization'] = f'Bearer {self.internal_api_key}'
                #logger.debug(f"Using internal API key for task {task_name} (key length: {len(self.internal_api_key)})")
            else:
                logger.warning(f"No internal API key found for task {task_name}")
            
            #logger.debug(f"Making API request to: {self.api_url}/admin/public/recon-tasks/{task_name}/parameters")
            #logger.debug(f"Request headers: {headers}")
            
            response = requests.get(
                f"{self.api_url}/admin/public/recon-tasks/{task_name}/parameters",
                headers=headers,
                timeout=10
            )
            
            #logger.debug(f"API response status: {response.status_code}")
            #if response.status_code != 200:
            #    logger.debug(f"API response text: {response.text[:200]}...")
            
            if response.status_code == 200:
                data = response.json()
                parameters = data.get("parameters", {})
                self._set_cached_parameters(task_name, parameters)
                logger.info(f"Fetched parameters for task {task_name}: {parameters}")
                return parameters
            elif response.status_code == 404:
                # Task parameters not configured, use defaults
                default_params = self._get_default_parameters(task_name)
                logger.info(f"Using default parameters for task {task_name}: {default_params}")
                return default_params
            else:
                logger.warning(f"Failed to fetch parameters for task {task_name}: {response.status_code}")
                return self._get_default_parameters(task_name)
                
        except Exception as e:
            logger.warning(f"Error fetching parameters for task {task_name}: {str(e)}")
            return self._get_default_parameters(task_name)

    def get_last_execution_threshold(self, task_name: str) -> int:
        """
        Get the last execution threshold for a specific task

        Args:
            task_name: Name of the recon task

        Returns:
            Last execution threshold in whole hours (API may store 1d, 1w, etc.)
        """
        from last_execution_threshold import last_execution_threshold_to_hours

        parameters = self.get_task_parameters(task_name)
        raw = parameters.get("last_execution_threshold", 24)
        return last_execution_threshold_to_hours(raw, default_hours=24)
    
    def get_timeout(self, task_name: str) -> int:
        """
        Get the timeout for a specific task
        
        Args:
            task_name: Name of the recon task
            
        Returns:
            Timeout in seconds
        """
        parameters = self.get_task_parameters(task_name)
        return parameters.get("timeout", 300)  # Default 5 minutes
    
    def get_max_retries(self, task_name: str) -> int:
        """
        Get the max retries for a specific task
        
        Args:
            task_name: Name of the recon task
            
        Returns:
            Maximum number of retries
        """
        parameters = self.get_task_parameters(task_name)
        return parameters.get("max_retries", 3)  # Default 3 retries
    
    def get_chunk_size(self, task_name: str) -> int:
        """
        Get the chunk size for a specific task
        
        Args:
            task_name: Name of the recon task
            
        Returns:
            Chunk size (number of items per chunk)
        """
        parameters = self.get_task_parameters(task_name)
        return parameters.get("chunk_size", 10)  # Default 10 items per chunk
    
    def _get_default_parameters(self, task_name: str) -> Dict[str, Any]:
        """
        Offline fallback when the API is unavailable or returns an error.

        Must stay aligned with src/api/app/recon_task_builtin_defaults.yaml (loaded by recon_task_defaults.py).
        """
        defaults = {
            "resolve_domain": {
                "last_execution_threshold": 24,
                "timeout": 120,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "whois_domain_check": {
                "last_execution_threshold": 24,
                "timeout": 600,
                "max_retries": 3,
                "chunk_size": 1,
            },
            "resolve_ip": {
                "last_execution_threshold": 24,
                "timeout": 120,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "resolve_ip_cidr": {
                "last_execution_threshold": 1,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 1,
                "ip_limit": 500,
                "max_cidr_size": 65536,
                "ips_per_worker": 50,
                "enable_port_scan": True,
                "port_scan_timeout": 300,
                "force_ip": False,
            },
            "subdomain_finder": {
                "last_execution_threshold": 24,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "subdomain_permutations": {
                "last_execution_threshold": 24,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 100,
                "permutation_list": "files/permutations.txt",
                "permutation_limit": None,
                "batch_size": 10,
            },
            "dns_bruteforce": {
                "last_execution_threshold": 24,
                "timeout": 600,
                "max_retries": 3,
                "chunk_size": 10,
                "wordlist": "/workspace/files/subdomains.txt",
                "batch_size": 5,
            },
            "port_scan": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 5,
            },
            "nuclei_scan": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 10,
                "template": {"official": [], "custom": []},
                "cmd_args": [],
            },
            "wpscan": {
                "last_execution_threshold": 24,
                "timeout": 1800,
                "max_retries": 3,
                "chunk_size": 5,
                "api_token": "",
                "enumerate": [],
            },
            "test_http": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "typosquat_detection": {
                "last_execution_threshold": "1w",
                "timeout": 1800,
                "max_retries": 3,
                "chunk_size": 20,
                "analyze_input_as_variations": False,
                "source": "",
                "max_variations": 100,
                "max_workers": 5,
                "domains_per_worker": 20,
                "fuzzers": [],
                "active_checks": True,
                "geoip_checks": True,
                "exclude_tested": True,
                "include_subdomains": False,
                "recalculate_risk": False,
                "enable_fuzzing": False,
                "fuzzer_wordlist": "/workspace/files/webcontent_test.txt",
            },
            "detect_broken_links": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "screenshot_website": {
                "last_execution_threshold": 24,
                "timeout": 60,
                "max_retries": 3,
                "chunk_size": 10,
            },
            "crawl_website": {
                "last_execution_threshold": 24,
                "timeout": 1800,
                "max_retries": 3,
                "chunk_size": 1,
                "depth": 5,
            },
            "fuzz_website": {
                "last_execution_threshold": 24,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 5,
                "wordlist": "/workspace/files/webcontent_test.txt",
            },
            "shell_command": {
                "last_execution_threshold": 24,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 10,
                "command": [],
            },
            "asset_batch_generator": {
                "last_execution_threshold": 1,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 50,
                "batch_size": 100,
            },
        }
        return defaults.get(task_name, {
            "last_execution_threshold": 24,
            "timeout": 300,
            "max_retries": 3,
            "chunk_size": 10,
        })

# Global parameter manager instance
parameter_manager = TaskParameterManager()

# Base Task class
class Task(ABC):
    name: str
    description: str
    input_type: Union[AssetType, List[AssetType]]
    output_types: List[AssetType]
    
    # Optional attributes for tasks that spawn additional jobs
    spawned_job_names: List[str] = []
    task_queue_client: Any = None
    
    @abstractmethod
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate the command to run with the given input"""
        pass

    async def generate_commands(
        self,
        input_data: List[Any],
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List["CommandSpec"]:
        """
        Generate commands for execution. Default: chunk input and call get_command per chunk.
        Override for orchestrators that need pre-processing (wildcard detection, gotator, etc.).
        """
        chunk_size = self.get_chunk_size(input_data, params)
        commands = []
        for i in range(0, len(input_data), chunk_size):
            chunk = input_data[i : i + chunk_size]
            cmd = self.get_command(chunk, params)
            if isinstance(cmd, list):
                for c in cmd:
                    if c:
                        commands.append(
                            CommandSpec(task_name=self.name, command=c, params=params)
                        )
            elif cmd:
                commands.append(
                    CommandSpec(task_name=self.name, command=cmd, params=params)
                )
        return commands

    async def get_synthetic_assets(
        self, context: Dict[str, Any]
    ) -> Optional[Dict[AssetType, List[Any]]]:
        """
        Return synthetic assets (e.g. wildcard parent domains) that are not from job output.
        Override for orchestrators; default returns None. May be async for DNS/API lookups.
        """
        return None

    @abstractmethod
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse the command output into assets"""
        pass

    def transform_to_findings(self, assets: Dict[AssetType, List[Any]], context: Dict[str, Any]) -> Dict[Any, List[Any]]:
        """
        Transform assets to findings for dual-purpose tasks.

        This method enables tasks to work in two modes:
        1. Asset Discovery Mode (default): Tasks produce assets for normal workflows
        2. Finding Generation Mode: Tasks produce findings for security workflows (e.g., typosquat detection)

        The transformation is context-aware and uses additional metadata to enrich findings.

        Pattern for Dual-Purpose Tasks:
        -------------------------------
        1. Keep parse_output() focused on parsing raw output to assets (default behavior)
        2. Override this method to implement asset-to-finding transformation
        3. Use context parameter to pass metadata (e.g., risk_factors)
        4. Return findings using FindingType enum keys

        Example Implementation in FuzzWebsite:
        ```python
        def transform_to_findings(self, assets, context):
            urls = assets.get(AssetType.URL, [])
            findings = []
            for url in urls:
                finding = TyposquatURL(
                    url=url.url,
                    typo_domain=context.get('typo_domain'),
                    # ... additional finding fields
                )
                findings.append(finding)
            return {FindingType.TYPOSQUAT_URL: findings}
        ```

        Args:
            assets: Parsed assets from parse_output()
            context: Additional context for transformation (domain info, risk factors, etc.)

        Returns:
            Dict mapping FindingType to list of finding objects
            Default implementation returns empty dict (no transformation)
        """
        # Default: no transformation, tasks must override to implement
        return {}

    def process_output_for_typosquat_mode(self, output: Any, params: Optional[Dict[Any, Any]] = None) -> Dict[Any, List[Any]]:
        """
        Process task output in typosquat findings mode.

        This is a workflow-driven method that automatically handles the two-step process:
        1. Parse output to assets using parse_output()
        2. Transform assets to findings using transform_to_findings()

        This method is called automatically by the task executor when the workflow
        specifies output_mode="typosquat_findings" for a task.

        Context Extraction:
        -------------------
        The method extracts transformation context from params. Tasks should receive
        context in their params, for example:
        - typo_domain: The typosquat domain being analyzed
        - risk_factors: Risk analysis data
        - program_name: Program name

        Args:
            output: Raw output from task execution
            params: Task parameters including context for transformation

        Returns:
            Dict mapping FindingType to list of finding objects
            Empty dict if task doesn't support transformation

        Example Workflow Configuration:
        ```yaml
        - name: fuzz_typosquat_domain
          task_type: fuzz_website
          output_mode: typosquat_findings
          params:
            typo_domain: "{{ workflow.inputs.typo_domain }}"
            risk_factors: "{{ workflow.inputs.risk_factors }}"
            wordlist: "common-paths.txt"
        ```
        """
        logger.info(f"🔄 Processing output in typosquat findings mode for task {self.name}")

        # Step 1: Parse output to assets (normal mode)
        try:
            assets = self.parse_output(output, params)
            logger.info(f"✓ Parsed output to {sum(len(v) for v in assets.values())} assets")
        except Exception as e:
            logger.error(f"Error parsing output to assets: {e}")
            return {}

        if not assets:
            logger.info("No assets parsed from output")
            return {}

        # Step 2: Extract context from params
        context = self._extract_transformation_context(params)
        logger.info(f"✓ Extracted transformation context: {list(context.keys())}")

        # Step 3: Transform assets to findings
        try:
            findings = self.transform_to_findings(assets, context)
            if findings:
                total_findings = sum(len(v) for v in findings.values())
                logger.info(f"✓ Transformed {sum(len(v) for v in assets.values())} assets to {total_findings} findings")
            else:
                logger.warning("Task does not support transformation to findings (transform_to_findings returned empty)")
            return findings
        except Exception as e:
            logger.error(f"Error transforming assets to findings: {e}")
            logger.exception("Full traceback:")
            return {}

    def _extract_transformation_context(self, params: Optional[Dict[Any, Any]] = None) -> Dict[str, Any]:
        """
        Extract transformation context from task parameters.

        This method looks for common context fields in params:
        - typo_domain
        - risk_factors
        - program_name
        - fuzzer_wordlist / wordlist
        - ... other context fields

        Args:
            params: Task parameters

        Returns:
            Dict containing transformation context
        """
        if not params:
            return {}

        # Extract common context fields
        context = {}

        # Domain information
        if 'typo_domain' in params:
            context['typo_domain'] = params['typo_domain']

        # Risk analysis
        if 'risk_factors' in params:
            context['risk_factors'] = params['risk_factors']

        # Program context
        if 'program_name' in params:
            context['program_name'] = params['program_name']

        # Fuzzer context
        if 'fuzzer_wordlist' in params:
            context['fuzzer_wordlist'] = params['fuzzer_wordlist']
        elif 'wordlist' in params:
            context['fuzzer_wordlist'] = params['wordlist']

        # Any other context fields (prefixed with context_)
        for key, value in params.items():
            if key.startswith('context_'):
                context_key = key.replace('context_', '')
                context[context_key] = value

        return context

    def normalize_output_for_parsing(self, output) -> str:
        """
        Normalize output format for parsing, handling both string and dict inputs.

        This method centralizes the logic for handling different output formats
        that may come from WorkerJobManager vs direct task execution.

        Args:
            output: Raw output from job execution (string or dict)

        Returns:
            Normalized string output ready for parsing
        """
        # Handle string input (direct from task execution)
        if isinstance(output, str):
            return output

        # Handle dict input (from WorkerJobManager)
        elif isinstance(output, dict):

            # Check if this is a wrapper dict with task metadata that contains 'output' field
            if 'output' in output and isinstance(output['output'], str):
                return output['output']
            else:
                # Try to convert the whole dict to JSON string as fallback
                try:
                    return json.dumps(output)
                except Exception as e:
                    logger.error(f"Failed to convert dict to JSON string: {e}")
                    return ""
        else:
            logger.error(f"Unsupported output type for normalization: {type(output)}")
            return str(output) if output is not None else ""

    def get_last_execution_threshold(self) -> int:
        """Return the number of hours to wait before re-executing this task on the same target"""
        #logger.debug(f"Task {self.name} requesting last_execution_threshold")
        return parameter_manager.get_last_execution_threshold(self.name)

    @abstractmethod
    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate a unique hash for the task execution based on target and params"""
        pass

    def get_timeout(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> int:
        """Return the timeout in seconds for this task
        
        Checks params first, then falls back to database/API default.
        
        Args:
            input_data: Task input data (may be used by subclasses for dynamic timeout calculation)
            params: Optional task parameters dict that may contain 'timeout' override
            
        Returns:
            Timeout in seconds
        """
        # Check if timeout is provided in params (from workflow/task definition)
        if params and isinstance(params, dict):
            timeout_override = params.get('timeout')
            if timeout_override is not None and isinstance(timeout_override, (int, float)) and timeout_override > 0:
                return int(timeout_override)
        
        # Fall back to database/API default
        return parameter_manager.get_timeout(self.name)
    
    def get_max_retries(self) -> int:
        """Return the maximum number of retries for this task"""
        #logger.debug(f"Task {self.name} requesting max_retries")
        return parameter_manager.get_max_retries(self.name)
    
    def get_chunk_size(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> int:
        """Return the chunk size for this task (params override, then API default)."""
        if params and isinstance(params, dict):
            cs = params.get("chunk_size")
            if cs is not None:
                try:
                    n = int(cs)
                    if n > 0:
                        return n
                except (TypeError, ValueError):
                    pass
        return parameter_manager.get_chunk_size(self.name)
    
    async def wait_for_spawned_jobs(self, timeout: int = 3600, task_queue_client: Any = None) -> Dict[str, str]:
        """Wait for spawned jobs to complete (optional method for tasks that spawn jobs)"""
        return {}

    def process_spawned_task_outputs(self) -> Optional[Dict[AssetType, List[Any]]]:
        """Process outputs from spawned tasks (optional method for tasks that spawn jobs)"""
        return None

    # ============================================================================
    # PROXY SUPPORT METHODS - Optional methods for tasks that support proxy
    # ============================================================================

    def supports_proxy(self) -> bool:
        """
        Indicate if this task supports AWS API Gateway proxying via FireProx.

        Tasks that support proxying should override this method to return True.
        By default, tasks do not support proxying.

        Returns:
            bool: True if task supports proxying, False otherwise
        """
        return False

    def extract_proxy_targets(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> List[str]:
        """
        Extract URLs that need proxying from input data.

        This method is called when a task has proxy support enabled and is used
        to determine which URLs should have API Gateway proxies created for them.

        Args:
            input_data: Task input data (list or single value)
            params: Task parameters

        Returns:
            List of URLs to create proxies for
        """
        return []

    def replace_targets_with_proxies(self, command: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace original URLs with proxy URLs in command string.

        This method is called before sending commands to worker pods to replace
        target URLs with their corresponding API Gateway proxy URLs.

        Args:
            command: Original command string
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified command with proxied URLs
        """
        # Default implementation: replace all occurrences
        modified_command = command
        for original_url, proxy_url in url_mapping.items():
            # Replace both with and without trailing slash
            modified_command = modified_command.replace(original_url.rstrip('/'), proxy_url.rstrip('/'))
            modified_command = modified_command.replace(original_url, proxy_url)
        return modified_command

    def replace_proxies_in_output(self, output: str, url_mapping: Dict[str, str]) -> str:
        """
        Replace proxy URLs back to original URLs in task output.

        This method is called after receiving output from worker pods to restore
        original URLs in place of proxy URLs before parsing results.

        Args:
            output: Raw output string from worker
            url_mapping: Dict mapping original URLs to proxy URLs

        Returns:
            Modified output with original URLs restored
        """
        # Default implementation: reverse the mapping and replace
        modified_output = output
        for original_url, proxy_url in url_mapping.items():
            # Replace both with and without trailing slash
            modified_output = modified_output.replace(proxy_url.rstrip('/'), original_url.rstrip('/'))
            modified_output = modified_output.replace(proxy_url, original_url)
        return modified_output

    # ============================================================================
    # ORCHESTRATOR PATTERN METHODS - Reusable for any task that spawns jobs
    # ============================================================================

    async def spawn_worker_jobs_batch(self, task_name: str, input_chunks: List[List[Any]],
                                   program_name: str, batch_size: int = 20,
                                   timeout: int = 1800, primary_asset_type: AssetType = None,
                                   step_name: str = None, workflow_id: str = None,
                                   process_assets_incrementally: bool = True, **job_kwargs) -> List[str]:
        """
        Spawn multiple worker jobs in batches for orchestrator patterns.

        Args:
            task_name: Name of the task to spawn (e.g., 'resolve_ip', 'port_scan')
            input_chunks: List of input chunks, each chunk becomes a separate job
            program_name: Program name for context
            batch_size: Number of jobs to spawn in each batch
            timeout: Timeout per job in seconds
            primary_asset_type: Main asset type for result parsing
            step_name: Step name for asset context
            workflow_id: Workflow ID for asset context
            process_assets_incrementally: Whether to parse and send assets after each batch
            **job_kwargs: Additional parameters for job creation

        Returns:
            List of spawned task IDs
        """
        if not self.task_queue_client:
            logger.error("No task_queue_client available - cannot spawn worker jobs")
            return []

        if not hasattr(self, 'spawned_task_ids'):
            self.spawned_task_ids = []
        if not hasattr(self, 'spawned_job_names'):
            self.spawned_job_names = []

        all_task_ids = []
        total_batches = (len(input_chunks) + batch_size - 1) // batch_size  # Ceiling division
        logger.info(f"Spawning {len(input_chunks)} {task_name} jobs in {total_batches} sequential batches of {batch_size}")

        # Process in sequential batches to avoid overwhelming Kueue
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(input_chunks))
            batch_chunks = input_chunks[start_idx:end_idx]

            logger.info(f"Processing batch {batch_num + 1}/{total_batches}: {len(batch_chunks)} jobs")

            # Create job parameters for this batch
            job_params_list = []
            for j, chunk in enumerate(batch_chunks):
                # Generate command based on task type and input chunk
                command = self._generate_orchestrator_command(task_name, chunk, job_kwargs)
                if not command:
                    continue

                batch_job_kwargs = job_kwargs.copy()
                batch_job_kwargs.update({
                    "step_num": 0,
                    "step_name": f"{task_name.replace('_', '-')}-chunk-{start_idx + j}",
                    "job_name": f"{task_name.replace('_', '-')}-chunk-{start_idx + j}",
                    "args": [command],
                    "timeout": timeout
                })

                job_params = self._build_job_params(task_name, command, program_name, **batch_job_kwargs)
                job_params_list.append(job_params)

            # Spawn current batch using existing Kubernetes service
            batch_task_ids = []
            if job_params_list:
                try:
                    # Use the existing queue_worker_tasks method from KubernetesService
                    task_ids = await self._queue_worker_tasks_batch(job_params_list)
                    if task_ids:
                        # Track spawned jobs
                        for task_id in task_ids:
                            job_name = f"worker-{task_id}"
                            self.spawned_job_names.append(job_name)
                            self.spawned_task_ids.append(task_id)
                            all_task_ids.append(task_id)
                            batch_task_ids.append(task_id)

                        logger.info(f"Successfully spawned batch {batch_num + 1} of {len(task_ids)} {task_name} jobs")
                    else:
                        logger.error(f"Failed to spawn {task_name} job batch {batch_num + 1}")

                except Exception as e:
                    logger.error(f"Error spawning {task_name} job batch {batch_num + 1}: {e}")
                    continue

            # Wait for current batch to complete before starting next batch
            if batch_task_ids:
                logger.info(f"Waiting for batch {batch_num + 1} to complete before starting next batch...")
                batch_stats = await self.wait_for_batch_task_ids(batch_task_ids, timeout)

                if not batch_stats["success"]:
                    logger.warning(f"Batch {batch_num + 1} had failures: {batch_stats['failed']} failed out of {batch_stats['total']}")

                logger.info(f"Batch {batch_num + 1} completed in {batch_stats['completion_time']:.1f}s")

                # Process and send assets from this batch immediately if enabled
                if process_assets_incrementally and primary_asset_type and step_name:
                    logger.info(f"Processing and sending assets from batch {batch_num + 1}...")
                    asset_success = await self.process_and_send_batch_assets(
                        batch_task_ids, primary_asset_type, program_name, step_name, workflow_id
                    )
                    if asset_success:
                        logger.info(f"Successfully processed and sent assets from batch {batch_num + 1}")
                    else:
                        logger.warning(f"Failed to process/send assets from batch {batch_num + 1}")

            # Small delay between batches to be gentle on Kueue
            if batch_num + 1 < total_batches:
                await asyncio.sleep(0.5)

        logger.info(f"Total spawned {len(all_task_ids)} {task_name} jobs from {len(input_chunks)} chunks")
        return all_task_ids

    async def wait_for_batch_completion(self, timeout: int = 3600,
                                     progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Wait for batch job completion with progress tracking.

        Args:
            timeout: Total timeout in seconds
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with completion statistics
        """
        if not hasattr(self, 'spawned_task_ids') or not self.spawned_task_ids:
            return {"completed": 0, "total": 0, "success": True}

        total_jobs = len(self.spawned_task_ids)
        completed_jobs = set()
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Waiting for {total_jobs} spawned jobs to complete (timeout: {timeout}s)")

        # Initialize output tracking
        if not hasattr(self, 'spawned_task_outputs'):
            self.spawned_task_outputs = {}

        # Set up output handlers if not already done
        self._register_batch_output_handlers()

        while len(completed_jobs) < total_jobs:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time

            if elapsed > timeout:
                logger.warning(f"Timeout waiting for batch completion after {timeout} seconds")
                break

            # Check for newly completed jobs
            newly_completed = []
            for task_id in self.spawned_task_ids:
                if task_id in completed_jobs:
                    continue
                if task_id in self.spawned_task_outputs:
                    completed_jobs.add(task_id)
                    newly_completed.append(task_id)

            if newly_completed:
                logger.info(f"Batch progress: {len(completed_jobs)}/{total_jobs} jobs completed")
                if progress_callback:
                    progress_callback(len(completed_jobs), total_jobs)

            # Wait before checking again
            await asyncio.sleep(1)

        # Calculate final statistics
        stats = {
            "completed": len(completed_jobs),
            "total": total_jobs,
            "failed": total_jobs - len(completed_jobs),
            "success": len(completed_jobs) == total_jobs,
            "completion_time": asyncio.get_event_loop().time() - start_time
        }

        logger.info(f"Batch completion stats: {stats}")
        return stats

    async def process_and_send_batch_assets(self, task_ids: List[str], primary_asset_type: AssetType,
                                           program_name: str, step_name: str, workflow_id: str = None) -> bool:
        """
        Process completed batch results and send assets to API immediately using existing infrastructure.

        Args:
            task_ids: List of task IDs from the completed batch
            primary_asset_type: The main asset type for this task
            program_name: Program name for asset context
            step_name: Step name for asset context
            workflow_id: Workflow ID (optional)

        Returns:
            True if assets were processed and sent successfully
        """
        try:
            # Collect outputs from completed batch tasks
            batch_outputs = {}
            for task_id in task_ids:
                if task_id in self.spawned_task_outputs:
                    batch_outputs[task_id] = self.spawned_task_outputs[task_id]

            if not batch_outputs:
                logger.info(f"No outputs available for batch {task_ids}")
                return False

            # Parse the batch results using orchestrator parsing logic
            if hasattr(self, 'parse_output_for_orchestrator'):
                parsed_assets = self.aggregate_job_results(batch_outputs, primary_asset_type,
                                                         self.parse_output_for_orchestrator)
            else:
                parsed_assets = self.aggregate_job_results(batch_outputs, primary_asset_type)

            if not parsed_assets:
                logger.info(f"No assets parsed from batch {task_ids}")
                return False

            total_assets = sum(len(assets) for assets in parsed_assets.values())
            logger.info(f"Parsed {total_assets} assets from batch: {dict((k.value if hasattr(k, 'value') else str(k), len(v)) for k, v in parsed_assets.items())}")

            # Use the existing task components infrastructure to send assets
            success = await self._send_assets_via_task_components(parsed_assets, program_name, step_name, workflow_id)
            if success:
                logger.info(f"Successfully sent {total_assets} assets from batch")
                return True

            logger.warning(f"Failed to send assets from batch {task_ids}")
            return False

        except Exception as e:
            logger.error(f"Error processing and sending batch assets: {e}")
            return False

    async def _send_assets_via_task_components(self, assets: Dict[AssetType, List[Any]],
                                             program_name: str, step_name: str, workflow_id: str = None) -> bool:
        """
        Send assets using the existing task components infrastructure.

        Args:
            assets: Parsed assets to send
            program_name: Program name for context
            step_name: Step name for context
            workflow_id: Workflow ID for context

        Returns:
            True if assets were sent successfully
        """
        try:
            # Try to access task components through various paths

            # 1. Check if task components are available directly on the task
            if hasattr(self, 'task_components') and self.task_components:
                if hasattr(self.task_components, 'data_api_client') and self.task_components.data_api_client:
                    logger.info("Using data API client from task components")
                    # SyncDataApiClient uses synchronous send_assets method
                    # We need to get the asset_processor from task_components
                    asset_processor = getattr(self.task_components, 'asset_processor', None)
                    if asset_processor:
                        success = self.task_components.data_api_client.send_assets(
                            step_name, program_name, workflow_id or "unknown",
                            assets, asset_processor
                        )
                        return success
                    else:
                        logger.warning("No asset processor available in task components")

            # 2. Check if we can access through task_queue_client -> task_executor
            if hasattr(self, 'task_queue_client') and self.task_queue_client:
                if hasattr(self.task_queue_client, 'task_executor'):
                    task_executor = self.task_queue_client.task_executor
                    if hasattr(task_executor, 'data_api_client') and task_executor.data_api_client:
                        logger.info("Using data API client from task executor")
                        # SyncDataApiClient uses synchronous send_assets method
                        # We need to get the asset_processor from the task_executor
                        asset_processor = getattr(task_executor, 'asset_processor', None)
                        if asset_processor:
                            success = task_executor.data_api_client.send_assets(
                                step_name, program_name, workflow_id or "unknown",
                                assets, asset_processor
                            )
                            return success
                        else:
                            logger.warning("No asset processor available in task executor")

            # 3. Try to create a temporary DataAPIClient if we have the necessary config
            api_url = os.getenv("API_URL", "http://api:8000")
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')

            if api_url and internal_api_key:
                logger.info("Creating temporary DataAPIClient for asset sending")
                # Import and use the existing DataAPIClient
                from data_api_client import DataAPIClient

                async with DataAPIClient(api_url, internal_api_key) as client:
                    result = await client.post_assets(assets, program_name)
                    return result.get("status") == "success"

            logger.warning("No available method to send assets - all infrastructure access paths failed")
            return False

        except Exception as e:
            logger.error(f"Error sending assets via task components: {e}")
            return False

    async def wait_for_batch_task_ids(self, task_ids: List[str], timeout: int = 3600) -> Dict[str, Any]:
        """
        Wait for a specific set of task IDs to complete.

        Args:
            task_ids: List of task IDs to wait for
            timeout: Timeout in seconds

        Returns:
            Dict with completion statistics for this batch
        """
        if not task_ids:
            return {"completed": 0, "total": 0, "success": True}

        total_jobs = len(task_ids)
        completed_jobs = set()
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Waiting for {total_jobs} specific jobs to complete (timeout: {timeout}s)")

        # Initialize output tracking
        if not hasattr(self, 'spawned_task_outputs'):
            self.spawned_task_outputs = {}

        # Set up output handlers if not already done
        self._register_batch_output_handlers()

        while len(completed_jobs) < total_jobs:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time

            if elapsed > timeout:
                logger.warning(f"Timeout waiting for batch task IDs after {timeout} seconds")
                break

            # Check for newly completed jobs
            newly_completed = []
            for task_id in task_ids:
                if task_id in completed_jobs:
                    continue
                if task_id in self.spawned_task_outputs:
                    completed_jobs.add(task_id)
                    newly_completed.append(task_id)

            if newly_completed:
                logger.info(f"Batch progress: {len(completed_jobs)}/{total_jobs} jobs completed")

            # Wait before checking again
            await asyncio.sleep(1)

        # Calculate statistics for this batch
        stats = {
            "completed": len(completed_jobs),
            "total": total_jobs,
            "failed": total_jobs - len(completed_jobs),
            "success": len(completed_jobs) == total_jobs,
            "completion_time": asyncio.get_event_loop().time() - start_time
        }

        logger.info(f"Batch task IDs completion stats: {stats}")
        return stats

    def collect_batch_outputs(self) -> Dict[str, Any]:
        """
        Collect outputs from all completed batch jobs.

        Returns:
            Dict mapping task_id to output data
        """
        if not hasattr(self, 'spawned_task_outputs'):
            return {}

        outputs = {}
        for task_id, output in self.spawned_task_outputs.items():
            outputs[task_id] = output

        logger.info(f"Collected outputs from {len(outputs)} completed jobs")
        return outputs

    def aggregate_job_results(self, outputs: Dict[str, Any], primary_asset_type: AssetType,
                           result_processor: Optional[callable] = None) -> Dict[AssetType, List[Any]]:
        """
        Aggregate results from multiple spawned jobs.

        Args:
            outputs: Dict of task_id -> output data
            primary_asset_type: The main asset type to aggregate
            result_processor: Optional custom processor function

        Returns:
            Aggregated results by asset type
        """
        if result_processor:
            return result_processor(outputs)

        # Default aggregation logic
        aggregated = {primary_asset_type: []}
        processed_count = 0
        error_count = 0

        for task_id, output in outputs.items():
            try:
                # Parse job output based on format
                if isinstance(output, dict) and "output" in output:
                    output_str = output["output"]
                else:
                    output_str = str(output)

                # Use the task's custom orchestrator parse method if available, otherwise use standard parse_output
                if hasattr(self, 'parse_output_for_orchestrator'):
                    try:
                        # For orchestrator tasks, parse individual job outputs
                        # First try to parse the output_str as JSON if it's a string
                        if isinstance(output_str, str):
                            try:
                                output_json = json.loads(output_str)
                            except json.JSONDecodeError:
                                # If it's not valid JSON, use the original output
                                output_json = output
                        else:
                            output_json = output_str

                        # Create a single-output dict for the orchestrator parser
                        single_output = {task_id: output_json}
                        parsed = self.parse_output_for_orchestrator(single_output)
                        if parsed and primary_asset_type in parsed:
                            aggregated[primary_asset_type].extend(parsed[primary_asset_type])
                            processed_count += 1
                    except Exception as e:
                        logger.error(f"Error parsing output from task {task_id}: {e}")
                        error_count += 1
                elif hasattr(self, 'parse_output'):
                    try:
                        parsed = self.parse_output(output_str)
                        if parsed and primary_asset_type in parsed:
                            aggregated[primary_asset_type].extend(parsed[primary_asset_type])
                            processed_count += 1
                    except Exception as e:
                        logger.error(f"Error parsing output from task {task_id}: {e}")
                        error_count += 1
                else:
                    logger.warning(f"No parse_output method available for task {task_id}")

            except Exception as e:
                logger.error(f"Error processing output from task {task_id}: {e}")
                error_count += 1

        logger.info(f"Aggregation complete: {processed_count} successful, {error_count} errors, "
                   f"total {len(aggregated[primary_asset_type])} {primary_asset_type.value} assets")

        return aggregated

    def handle_batch_errors(self, outputs: Dict[str, Any], failed_task_ids: List[str]) -> Dict[str, Any]:
        """
        Handle partial failures in batch operations.

        Args:
            outputs: Dict of task_id -> output data
            failed_task_ids: List of task IDs that failed

        Returns:
            Error handling report
        """
        error_report = {
            "total_failed": len(failed_task_ids),
            "total_successful": len(outputs) - len(failed_task_ids),
            "failed_tasks": failed_task_ids,
            "can_continue": True,  # Default: continue with partial results
            "recommendations": []
        }

        # Analyze failure patterns
        if failed_task_ids:
            error_report["recommendations"].append(
                f"Consider retrying {len(failed_task_ids)} failed tasks"
            )

        # Check if we have enough successful results to continue
        success_rate = error_report["total_successful"] / (error_report["total_successful"] + error_report["total_failed"])
        if success_rate < 0.5:  # Less than 50% success
            error_report["can_continue"] = False
            error_report["recommendations"].append("Low success rate - consider aborting operation")

        logger.warning(f"Batch error report: {error_report}")
        return error_report

    def _register_batch_output_handlers(self):
        """Set up output handlers for batch jobs"""
        if not self.task_queue_client or not hasattr(self, 'spawned_task_ids'):
            return

        logger.info(f"Setting up output handlers for {len(self.spawned_task_ids)} batch jobs")

        for task_id in self.spawned_task_ids:
            def make_output_handler(tid):
                def output_handler(output):
                    logger.info(f"Received output from batch job {tid}")
                    if not hasattr(self, 'spawned_task_outputs'):
                        self.spawned_task_outputs = {}
                    self.spawned_task_outputs[tid] = output
                    logger.debug(f"Stored output for batch job {tid}")
                return output_handler

            self.task_queue_client.output_handlers[task_id] = make_output_handler(task_id)

    def _generate_orchestrator_command(self, task_name: str, chunk: List[Any], job_kwargs: Dict[str, Any]) -> str:
        """Generate command for orchestrator-spawned jobs"""
        try:
            if task_name == "resolve_ip":
                # Generate resolve_ip command
                ips_text = '\n'.join(str(ip) for ip in chunk)
                return f"cat << 'EOF' | python3 dnsx_wrapper.py\n{ips_text}\nEOF"
            elif task_name == "subdomain_finder":
                # Generate subdomain_finder command
                domains = [str(item) for item in chunk]
                domains_text = '\n'.join(domains)
                return f"cat << 'EOF' | python3 subdomain_finder_wrapper.py\n{domains_text}\nEOF"
            elif task_name == "port_scan":
                # Generate port_scan command
                ips = [str(item) for item in chunk]
                ips_text = '\n'.join(ips)
                return f"cat << 'EOF' | python3 port_scan_wrapper.py\n{ips_text}\nEOF"
            else:
                logger.error(f"No command generator for task type: {task_name}")
                return ""
        except Exception as e:
            logger.error(f"Error generating command for {task_name}: {e}")
            return ""

    def _build_job_params(self, task_name: str, command: str, program_name: str, **kwargs) -> Dict[str, Any]:
        """Build job parameters for orchestrator-spawned jobs"""
        import uuid

        # Get environment variables
        workflow_id = os.getenv('WORKFLOW_ID', 'unknown')
        execution_id = os.getenv('EXECUTION_ID', workflow_id)

        # Generate unique job name
        safe_task_name = task_name.replace('_', '-').lower()
        job_name = kwargs.get('job_name', f"{safe_task_name}-{str(uuid.uuid4())[:8]}")

        job_params = {
            "workflow_id": execution_id,
            "workflow_name": program_name,
            "program_name": program_name,
            "task_name": safe_task_name,
            "step_num": kwargs.get('step_num', 0),
            "step_name": kwargs.get('step_name', f"{safe_task_name}-chunk"),
            "job_name": job_name,
            "image": os.getenv('WORKER_IMAGE', 'worker:latest'),
            "image_pull_policy": os.getenv('IMAGE_PULL_POLICY', 'Always'),
            "args": [command],
            "timeout": kwargs.get('timeout', 600)
        }

        # Add any additional parameters
        job_params.update(kwargs)

        return job_params

    async def _queue_worker_tasks_batch(self, job_params_list: List[Dict[str, Any]]) -> List[str]:
        """Queue multiple worker tasks using KubernetesService"""
        try:
            from services.kubernetes import KubernetesService
            k8s_service = KubernetesService()
            return await k8s_service.queue_worker_tasks(job_params_list)
        except Exception as e:
            logger.error(f"Error queuing worker tasks batch: {e}")
            return []
    
    async def spawn_worker_job(self, task_name: str, command: str, program_name: str, 
                             timeout: int = 1800, **kwargs) -> Optional[str]:
        """
        Generic method to spawn a worker job for subsequent processing.
        
        Args:
            task_name: Name of the task to spawn
            command: Command to execute
            program_name: Program name for context
            timeout: Job timeout in seconds
            **kwargs: Additional parameters for job creation
            
        Returns:
            Task ID if successful, None otherwise
        """
        if not self.task_queue_client:
            logger.error("No task_queue_client available - cannot spawn worker job")
            return None
        
        try:
            import uuid
            import time
            from services.kubernetes import KubernetesService
            
            # Get environment variables
            workflow_id = os.getenv('WORKFLOW_ID')
            execution_id = os.getenv('EXECUTION_ID')
            if not workflow_id:
                #logger.warning("No WORKFLOW_ID found - using fallback")
                workflow_id = 'spawned-job'
            if not execution_id:
                #logger.warning("No EXECUTION_ID found - using workflow_id as fallback")
                execution_id = workflow_id
            
            # Generate unique job parameters with RFC 1123 compliant names
            # Replace underscores with hyphens and ensure valid format for Kubernetes compatibility
            def make_rfc1123_compliant(name: str) -> str:
                # Replace underscores with hyphens
                safe_name = name.replace('_', '-').lower()
                # Remove any non-alphanumeric characters except hyphens
                safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '-')
                # Ensure it starts and ends with alphanumeric characters
                safe_name = safe_name.strip('-')
                # If empty, use default name
                if not safe_name:
                    safe_name = 'job'
                # Ensure it starts with alphanumeric
                if not safe_name[0].isalnum():
                    safe_name = 'job-' + safe_name
                # Ensure it ends with alphanumeric  
                if not safe_name[-1].isalnum():
                    safe_name = safe_name + '-job'
                return safe_name
            
            safe_task_name = make_rfc1123_compliant(task_name)
            safe_step_name = f"{safe_task_name}-spawned-{int(time.time())}"
            safe_job_name = f"spawned-{safe_task_name}-{str(uuid.uuid4())[:8]}"
            
            job_params = {
                "workflow_id": execution_id,  # Use execution_id for output routing
                "workflow_name": program_name,
                "program_name": program_name,
                "task_name": safe_task_name,
                "step_num": 0,
                "step_name": safe_step_name,
                "job_name": safe_job_name,
                "image": os.getenv('WORKER_IMAGE', 'worker:latest'),
                "image_pull_policy": os.getenv('IMAGE_PULL_POLICY', 'Always'),
                "args": [command],
                "timeout": timeout
            }
            
            # Update with any additional parameters
            job_params.update(kwargs)
            
            logger.info(f"Spawning worker job: {job_params['job_name']} for task {task_name}")
            logger.info(f"📡 Job will send output to: tasks.output.{execution_id}")
            logger.info(f"🔍 Runner is listening on: tasks.output.{execution_id}")
            logger.info(f"🆔 WORKFLOW_ID: {workflow_id}, EXECUTION_ID: {execution_id}")
            
            # Create Kubernetes service and queue the job
            k8s_service = KubernetesService()
            
            # Queue the job using asyncio
            import asyncio
            import concurrent.futures
            
            def queue_job_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(k8s_service.queue_worker_tasks([job_params]))
                finally:
                    loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(queue_job_in_thread)
                task_ids = future.result(timeout=30)
            
            if task_ids and len(task_ids) > 0:
                task_id = task_ids[0]
                logger.info(f"Successfully spawned worker job with task_id: {task_id}")
                
                # Track the spawned job
                if hasattr(self, 'spawned_job_names'):
                    job_name = f"worker-{task_id}"
                    self.spawned_job_names.append(job_name)
                    if hasattr(self, 'spawned_task_ids'):
                        self.spawned_task_ids.append(task_id)
                
                return task_id
            else:
                logger.error("Failed to spawn worker job - no task_ids returned")
                return None
                
        except Exception as e:
            logger.error(f"Error spawning worker job for {task_name}: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def spawn_screenshot_job(self, urls: List[str], program_name: str) -> Optional[str]:
        """
        Convenience method to spawn a screenshot website job.
        
        Args:
            urls: List of URLs to screenshot
            program_name: Program name for context
            
        Returns:
            Task ID if successful, None otherwise
        """
        if not urls:
            logger.warning("No URLs provided for screenshot job")
            return None
        
        # Prepare URLs for screenshotter - use here document for newlines
        urls_text = '\n'.join(urls)
        command = f"cat << 'EOF' | bash screenshotter.sh\n{urls_text}\nEOF"
        
        return await self.spawn_worker_job(
            task_name="screenshot_website",
            command=command,
            program_name=program_name,
            timeout=1200  # 20 minutes for screenshot jobs
        )
    
    async def spawn_subdomain_finder_job(self, domains: List[str], program_name: str) -> Optional[str]:
        """
        Convenience method to spawn a subdomain_finder job.
        
        Args:
            domains: List of apex domains to find subdomains for
            program_name: Program name for context
            
        Returns:
            Task ID if successful, None otherwise
        """
        if not domains:
            logger.warning("No domains provided for subdomain_finder job")
            return None
        
        # Prepare domains for subfinder - each domain on a separate line
        domains_text = '\n'.join(domains)
        command = f"cat << 'EOF' | subfinder -silent\n{domains_text}\nEOF"
        
        return await self.spawn_worker_job(
            task_name="subdomain_finder",
            command=command,
            program_name=program_name,
            timeout=900  # 15 minutes for subdomain discovery
        )
    
    def parse_spawned_job_output(self, task_name: str, output: str, 
                               context: Optional[Dict[str, Any]] = None) -> Optional[Dict[AssetType, List[Any]]]:
        """
        Generic method to parse output from spawned jobs based on task type.
        
        Args:
            task_name: Name of the spawned task
            output: Raw output from the job
            context: Additional context for parsing (e.g., original URLs, domains)
            
        Returns:
            Parsed assets or None if parsing fails
        """
        try:
            if task_name == "screenshot_website":
                return self._parse_screenshot_output(output, context)
            elif task_name == "subdomain_finder":
                return self._parse_subdomain_finder_output(output, context)
            else:
                logger.warning(f"No parser available for spawned task: {task_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing output from spawned job {task_name}: {e}")
            return None
    
    def _parse_subdomain_finder_output(self, output: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[AssetType, List[Any]]]:
        """Parse subdomain_finder output from spawned subdomain_finder job"""
        try:
            # Import the subdomain_finder task to reuse its parsing logic
            from .subdomain_finder import SubdomainFinder
            
            subdomain_task = SubdomainFinder()
            parsed_assets = subdomain_task.parse_output(output)
            
            logger.info(f"Parsed {len(parsed_assets.get(AssetType.SUBDOMAIN, []))} subdomains from spawned subdomain_finder job")
            
            return parsed_assets
            
        except Exception as e:
            logger.error(f"Error parsing subdomain_finder output: {e}")
            return None 