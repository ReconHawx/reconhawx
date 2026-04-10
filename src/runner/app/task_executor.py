#!/usr/bin/env python3
import logging
import json
import re
from typing import Dict, List, Any, Optional, Union
from kubernetes import client
import os
from tasks import TaskRegistry
from tasks.base import Task, AssetType, FindingType, CommandSpec, parameter_manager
from models.assets import Ip, Service as AssetService
from models.workflow import TaskDefinition, AssetStore
from task_queue_client import TaskQueueClient
from services.kubernetes import KubernetesService
from worker_job_manager import WorkerJobManager
import redis
from datetime import datetime
from pydantic import BaseModel
import asyncio
import base64
from utils.utils import extract_apex_domain


logger = logging.getLogger('task_executor')

API_URL = os.getenv('API_URL', 'http://dev-api:8000')


def _extract_apex_domains_from_regex(domain_regex_list: List[str]) -> List[str]:
    """Extract unique apex domains from domain_regex patterns (mirrors ProgramDetail.js getApexDomains)."""
    if not domain_regex_list:
        return []
    apex_set = set()
    two_level_tlds = ['co', 'com', 'org', 'net', 'ac', 'gov', 'edu']
    for pattern in domain_regex_list:
        domain = re.sub(r'\^|\$', '', pattern)
        domain = re.sub(r'\.\*', '', domain)
        domain = domain.replace('\\.', '.').replace('\\', '')
        domain = re.sub(r'\(\?:', '', domain).replace(')', '')
        domain = re.sub(r'\[.*?\]', '', domain).strip()
        domain = re.sub(r'^\.+|\.+$', '', domain)
        parts = [p for p in domain.split('.') if p]
        if len(parts) >= 2 and '.' in domain:
            apex = '.'.join(parts[-3:]) if len(parts) >= 3 and parts[-2] in two_level_tlds else '.'.join(parts[-2:])
            apex_set.add(apex)
    return sorted(apex_set)
REDIS_URL = os.getenv('REDIS_URL', 'redis://dev-redis:6379/0')

DEFAULT_CHUNK_SIZE = 10  # Number of inputs that triggers chunking

class AssetFilter:
    """Filter assets by their properties using a simple query syntax
    
    Supports single filters: 'property.operation:value'
    Supports multiple filters with AND/OR: 'property1.op1:val1 and property2.op2:val2 or property3.op3:val3'
    """
    
    def __init__(self, filter_expression: str):
        self.filter_expression = filter_expression
        self.parsed_filters = self._parse_filter(filter_expression)
    
    def _parse_single_filter(self, filter_expr: str) -> Dict[str, Any]:
        """Parse a single filter expression like 'name.contains:admin'"""
        if not filter_expr or not filter_expr.strip():
            return None
        
        # Split by colon to separate property.operation from value
        parts = filter_expr.split(':', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid filter syntax: {filter_expr}. Expected format: 'property.operation:value'")
        
        property_operation = parts[0].strip()
        value = parts[1].strip()
        
        # Split property.operation to get property and operation
        prop_parts = property_operation.split('.', 1)
        if len(prop_parts) != 2:
            raise ValueError(f"Invalid property operation: {property_operation}. Expected format: 'property.operation'")
        
        property_name = prop_parts[0].strip()
        operation = prop_parts[1].strip()
        
        return {
            'property': property_name,
            'operation': operation,
            'value': value
        }
    
    def _parse_filter(self, filter_expr: str) -> List[Dict[str, Any]]:
        """Parse filter expression, supporting multiple filters with AND/OR operators"""
        if not filter_expr or not filter_expr.strip():
            return []
        
        # Split by ' and ' and ' or ' (case-insensitive)
        # We need to be careful to preserve the operators and handle them correctly
        expr = filter_expr.strip()
        
        # Use regex to find all operators with their positions
        # Pattern matches ' and ' or ' or ' (case-insensitive, with spaces)
        pattern = r'\s+(and|or)\s+'
        matches = list(re.finditer(pattern, expr, re.IGNORECASE))
        
        if not matches:
            # Single filter, no operators
            parsed = self._parse_single_filter(expr)
            return [parsed] if parsed else []
        
        # Split by operators while preserving them
        result = []
        last_pos = 0
        
        for i, match in enumerate(matches):
            # Extract filter before operator
            before_op = expr[last_pos:match.start()].strip()
            if before_op:
                parsed = self._parse_single_filter(before_op)
                if parsed:
                    result.append(parsed)
            
            # Extract operator
            op = match.group(1).lower()  # Normalize to lowercase
            result.append({'operator': op})
            
            last_pos = match.end()
        
        # Handle the last filter after the last operator
        after_last_op = expr[last_pos:].strip()
        if after_last_op:
            parsed = self._parse_single_filter(after_last_op)
            if parsed:
                result.append(parsed)
        
        # Validate: result should alternate between filters and operators
        if len(result) == 0:
            return []
        
        # Ensure we start with a filter, not an operator
        if isinstance(result[0], dict) and 'operator' in result[0]:
            raise ValueError("Invalid filter syntax: filter expression cannot start with operator")
        
        # Ensure we don't end with an operator
        if isinstance(result[-1], dict) and 'operator' in result[-1]:
            raise ValueError("Invalid filter syntax: filter expression cannot end with operator")
        
        # Ensure proper alternation: filters and operators should alternate
        for i in range(len(result) - 1):
            current = result[i]
            next_item = result[i + 1]
            is_current_operator = isinstance(current, dict) and 'operator' in current
            is_next_operator = isinstance(next_item, dict) and 'operator' in next_item
            
            if is_current_operator and is_next_operator:
                raise ValueError("Invalid filter syntax: consecutive operators found")
            elif not is_current_operator and not is_next_operator:
                # Both are filters, missing operator between them
                raise ValueError("Invalid filter syntax: missing operator between filters")
        
        return result
    
    def _evaluate_single_filter(self, filter_def: Dict[str, Any], asset: Dict[str, Any]) -> bool:
        """Evaluate a single filter condition against an asset"""
        property_name = filter_def['property']
        operation = filter_def['operation']
        expected_value = filter_def['value']
        
        # Get the property value from the asset
        property_value = asset.get(property_name)
        
        # Handle None values
        if property_value is None:
            return False
        
        # Convert to string for string operations
        if isinstance(property_value, (list, dict)):
            property_value = str(property_value)
        elif not isinstance(property_value, str):
            property_value = str(property_value)
        
        # Apply the operation
        if operation == 'contains':
            return expected_value.lower() in property_value.lower()
        elif operation == 'startswith':
            return property_value.lower().startswith(expected_value.lower())
        elif operation == 'endswith':
            return property_value.lower().endswith(expected_value.lower())
        elif operation == 'equals':
            return property_value.lower() == expected_value.lower()
        elif operation == 'regex':
            try:
                return bool(re.search(expected_value, property_value, re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid regex pattern: {expected_value}")
                return False
        elif operation == 'in':
            # Check if property value is in a comma-separated list
            expected_values = [v.strip() for v in expected_value.split(',')]
            return property_value.lower() in [v.lower() for v in expected_values]
        elif operation == 'not_contains':
            return expected_value.lower() not in property_value.lower()
        elif operation == 'not_equals':
            return property_value.lower() != expected_value.lower()
        else:
            logger.warning(f"Unknown filter operation: {operation}")
            return True  # Default to include if operation is unknown
    
    def evaluate(self, asset: Dict[str, Any]) -> bool:
        """Evaluate if an asset matches the filter criteria"""
        if not self.parsed_filters:
            return True  # No filter means include all
        
        # Handle single filter (backward compatibility)
        if len(self.parsed_filters) == 1 and 'operator' not in self.parsed_filters[0]:
            return self._evaluate_single_filter(self.parsed_filters[0], asset)
        
        # Evaluate compound filters with operator precedence
        # AND has higher precedence than OR, so we group AND operations first
        
        # First, evaluate all filters and create a list of boolean results with operators
        evaluated = []
        i = 0
        while i < len(self.parsed_filters):
            item = self.parsed_filters[i]
            if 'operator' in item:
                evaluated.append(item['operator'])
            else:
                # Evaluate the filter
                result = self._evaluate_single_filter(item, asset)
                evaluated.append(result)
            i += 1
        
        # Now process with AND precedence: group consecutive AND operations
        # Example: True and False or True and True -> (True and False) or (True and True)
        result_stack = []
        i = 0
        
        while i < len(evaluated):
            if isinstance(evaluated[i], bool):
                current_value = evaluated[i]
                
                # Look ahead for AND operations
                j = i + 1
                while j < len(evaluated) and evaluated[j] == 'and':
                    # Get the next boolean value
                    if j + 1 < len(evaluated) and isinstance(evaluated[j + 1], bool):
                        current_value = current_value and evaluated[j + 1]
                        j += 2
                    else:
                        break
                
                result_stack.append(current_value)
                i = j
            else:
                # This is an operator (OR)
                result_stack.append(evaluated[i])
                i += 1
        
        # Now evaluate OR operations left-to-right
        if not result_stack:
            return True
        
        final_result = result_stack[0] if isinstance(result_stack[0], bool) else True
        
        i = 1
        while i < len(result_stack):
            if isinstance(result_stack[i], str) and result_stack[i] == 'or':
                if i + 1 < len(result_stack) and isinstance(result_stack[i + 1], bool):
                    final_result = final_result or result_stack[i + 1]
                    i += 2
                else:
                    i += 1
            else:
                i += 1
        
        return final_result
    
    def filter_assets(self, assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter a list of assets based on the filter criteria"""
        if not self.parsed_filters:
            return assets
        
        filtered_assets = []
        for asset in assets:
            if self.evaluate(asset):
                filtered_assets.append(asset)
        
        logger.info(f"Filtered {len(assets)} assets to {len(filtered_assets)} using filter: {self.filter_expression}")
        return filtered_assets

class TaskExecutor:
    """Executes workflow tasks using decomposed components for better performance and maintainability"""
    
    def __init__(self, batch_v1: client.BatchV1Api):
        self.batch_v1 = batch_v1
        self.k8s_service = KubernetesService()  # Initialize without parameters
        self.task_queue_client = None
        self.running = False
        self.pending_tasks = {}  # Move pending_tasks to TaskExecutor
        # Use EXECUTION_ID for operations that need a valid ID, WORKFLOW_ID for workflow definition reference
        self.execution_id = os.getenv('EXECUTION_ID')
        self.workflow_id = os.getenv('WORKFLOW_ID')
        self.program_name = None  # Will be set when executing tasks
        self.asset_store = AssetStore()
        self.task_registry = TaskRegistry
        self.task_outputs = {}
        self.completed_task_ids = set()
        self.docker_registry = os.getenv('DOCKER_REGISTRY')
        self.input_limits = {}  # Track input limits by input name
        # Initialize Redis connection
        self.redis_client = redis.from_url(REDIS_URL)
        self.workflow_context = None  # Will be set when executing workflow
        
        # Initialize new component classes
        from task_components import TaskExecutionManager, AssetProcessor, SyncDataApiClient, MemoryOptimizationConfig
        self.execution_manager = TaskExecutionManager(
            self.k8s_service, 
            self.docker_registry or "", 
            self.execution_id or ""
        )
        # Enable streaming by default for better memory efficiency
        enable_streaming = os.getenv('ENABLE_STREAMING_ASSETS', 'true').lower() == 'true'
        memory_config = MemoryOptimizationConfig.from_environment()
        self.asset_processor = AssetProcessor(self.asset_store, enable_streaming, memory_config)
        self.output_handler = None  # Will be initialized when task_queue_client is available
        self.data_api_client = SyncDataApiClient(API_URL)
        self.async_data_api_client = None  # Will be created when needed
        
        # Enable progressive streaming by default
        self.progressive_streaming_enabled = os.getenv('ENABLE_PROGRESSIVE_STREAMING', 'true').lower() == 'true'
        # Note: Progressive streaming will be enabled in initialize() method after async client is created
        
        # Initialize WorkerJobManager for modern job management
        self.job_manager = None  # Will be initialized when task_queue_client is available

        # Initialize step API responses storage for workflow status updates
        self._step_api_responses = {}
        # Initialize step timing tracking
        self._step_timing = {}

    async def initialize(self):
        """Initialize the task executor"""
        self.running = True
        self.task_queue_client = TaskQueueClient()
        # Add back-reference (ignore type error as this is intentional)
        self.task_queue_client.task_executor = self  # type: ignore
        
        # Initialize output handler now that task_queue_client is available
        from task_components import OutputHandler
        self.output_handler = OutputHandler(self.task_queue_client)
        
        # Initialize WorkerJobManager now that task_queue_client is available
        self.job_manager = WorkerJobManager(
            task_queue_client=self.task_queue_client,
            k8s_service=self.k8s_service
        )
        logger.debug("WorkerJobManager initialized for modern job management")

        # Initialize async data API client for progressive streaming
        from data_api_client import DataAPIClient
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
        self.async_data_api_client = DataAPIClient(API_URL, internal_api_key)
        await self.async_data_api_client.initialize()

        # Enable progressive streaming now that async client is available
        if self.progressive_streaming_enabled:
            self.execution_manager.enable_progressive_streaming(self.async_data_api_client, self.asset_processor)

        return await self.task_queue_client.setup()
    
    async def shutdown(self):
        """Shutdown the task executor"""
        self.running = False
        
        # Clean up execution manager background tasks first
        if self.execution_manager:
            try:
                await self.execution_manager.cleanup_background_tasks()
                logger.debug("Execution manager background tasks cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up execution manager background tasks: {e}")
        
        # Clean up WorkerJobManager
        if self.job_manager:
            try:
                self.job_manager.cleanup_all()
                logger.debug("WorkerJobManager cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up WorkerJobManager: {e}")
        
        # Shut down progressive streamer's data API client first
        if self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
            logger.debug("Shutting down progressive streamer...")
            await self.execution_manager.progressive_streamer.shutdown()
            logger.debug("Progressive streamer shutdown completed")
        
        # Shut down async data API client
        if self.async_data_api_client:
            logger.debug("Shutting down async data API client...")
            await self.async_data_api_client.shutdown()
            logger.debug("Async data API client shutdown completed")
        else:
            logger.warning("async_data_api_client is None - was not initialized or already cleaned up")

        if self.task_queue_client:
            await self.task_queue_client.shutdown()
        self.task_queue_client = None
        self.job_manager = None
        self.async_data_api_client = None
        
    def _serialize_asset(self, asset: Any) -> Any:
        """Convert an asset object to a serializable type, handling datetime and specific asset types."""

        if isinstance(asset, datetime):
            return asset.isoformat()

        # Check if it's a Pydantic model
        elif isinstance(asset, BaseModel):
            try:
                # Use Pydantic's serialization for JSON-safe values
                return asset.model_dump(mode='json', by_alias=True)
            except Exception as e:
                logger.warning(f"Failed to model_dump {type(asset)}: {e}. Falling back to recursive dict serialization.")
                # Fallback to converting to dict then recursively serializing fields
                try:
                    # Use .__dict__ only if model_dump fails catastrophically
                    asset_dict = asset.__dict__ # This might include private Pydantic attributes
                    # Filter out private Pydantic attributes if necessary, or just serialize what's available
                    return {k: self._serialize_asset(v) for k, v in asset_dict.items() if not k.startswith('_')}
                except Exception as e2:
                     logger.error(f"Could not serialize Pydantic model {type(asset)} manually: {e2}")
                     return str(asset) # Last resort

        # Specific handling for common.models.assets.Service (if it's a Pydantic model, it should be caught above)
        # This handles cases where it might not inherit from BaseModel directly but has expected fields.
        elif isinstance(asset, AssetService):
             logger.debug(f"Serializing AssetService object: {asset}")
             # If AssetService is a Pydantic model, model_dump should have worked.
             # If not, attempt manual serialization like TaskBaseService.
             serialized = {}
             if not serialized and hasattr(asset, '__dict__'):
                 logger.warning("No specific attributes found for AssetService, trying __dict__ fallback.")
                 return {k: self._serialize_asset(v) for k, v in asset.__dict__.items() if not k.startswith('_')}
             elif not serialized:
                 logger.error("Could not serialize AssetService object with known attributes or __dict__.")
                 return str(asset)
             return serialized

        # Specific handling for non-Pydantic Ip type (if necessary)
        elif isinstance(asset, Ip):
             # Attempt manual serialization based on expected attributes
             if hasattr(asset, 'ip'):
                 serialized = {'ip': self._serialize_asset(asset.ip)} # Serialize potentially nested types
                 if hasattr(asset, 'ptr'):
                     # Recursively serialize potentially complex types within Ip (like lists of strings or other objects)
                     serialized['ptr'] = self._serialize_asset(asset.ptr)
                 # Add other relevant attributes if needed, ensuring they are serialized
                 # Example: serialized['some_other_field'] = self._serialize_asset(asset.some_other_field)
                 return serialized
             else:
                 logger.error("Could not serialize Ip asset manually - missing 'ip' attribute.")
                 return str(asset)

        # Handle lists: recursively serialize elements
        elif isinstance(asset, list):
             return [self._serialize_asset(item) for item in asset]

        # Handle dictionaries: recursively serialize values
        elif isinstance(asset, dict):
             # Ensure keys are strings (usually they are, but just in case)
             return {str(k): self._serialize_asset(v) for k, v in asset.items()}

        # Handle primitive types that are already JSON serializable
        elif isinstance(asset, (str, int, float, bool, type(None))):
            return asset

        # Fallback for other unknown types
        else:
            logger.warning(f"Cannot properly serialize asset of type {type(asset)}, converting to string representation.")
            return str(asset)

    def set_workflow_context(self, workflow):
        """Set the workflow context for resolving input mappings"""
        self.workflow_context = workflow
        logger.debug(f"Setting workflow context with inputs: {workflow.inputs}")
        if workflow.inputs:
            for input_name, input_def in workflow.inputs.items():
                logger.debug(f"  Input '{input_name}': type={input_def.type}, values={input_def.values}")

    def _apply_task_param_defaults(self, task_def: TaskDefinition, task_type: str) -> None:
        """Shallow merge: system (API effective) then workflow task_def.params (workflow wins per key)."""
        workflow_params = dict(task_def.params) if task_def.params else {}
        system_params = parameter_manager.get_task_parameters(task_type)
        task_def.params = {**system_params, **workflow_params}

    def _resolved_last_execution_threshold_hours(self, task: Task, task_def: TaskDefinition) -> int:
        """Prefer merged task_def.params after _apply_task_param_defaults; fall back to API manager."""
        from last_execution_threshold import try_last_execution_threshold_to_hours

        params = task_def.params or {}
        raw = params.get("last_execution_threshold")
        if raw is not None:
            t = try_last_execution_threshold_to_hours(raw)
            if t is not None and t > 0:
                return t
        return task.get_last_execution_threshold()

    async def execute_task(self, step_num: int, step_name: str, task_def: TaskDefinition, program_name: str) -> Dict[AssetType, List[Any]]:
        """Execute a task via the task queue and return its output assets - now decomposed for better maintainability"""
        # Debug: Check task_def at entry point
        logger.info(f"🔍 DEBUG (execute_task entry): task_def.name={task_def.name}")
        logger.info(f"   output_mode={getattr(task_def, 'output_mode', 'ATTR_NOT_FOUND')}")
        logger.info(f"   task_def type: {type(task_def)}")
        logger.info(f"   task_def.__dict__ keys: {list(task_def.__dict__.keys()) if hasattr(task_def, '__dict__') else 'NO __dict__'}")
        
        # Set program name for use in _prepare_input_data
        self.program_name = program_name

        task_results = []

        # Track assets sent progressively during WorkerJobManager execution
        progressive_assets_sent_count = [0]  # Use list for mutability in nested functions

        # Persistent guard to prevent multiple asset sending across task executions
        # Use instance variable to persist across method calls
        if not hasattr(self, '_task_assets_sent_guard'):
            self._task_assets_sent_guard = set()

        task_key = f"{step_name}_{task_def.name}_{program_name}"
        assets_already_sent = task_key in self._task_assets_sent_guard
        logger.debug(f"Main execution guard check - key: {task_key}, already_sent: {assets_already_sent}")

        # Get the task implementation - use task_type if available, otherwise fall back to name
        task_type = getattr(task_def, 'task_type', None) or task_def.name
        task_class = self.task_registry.get_task(task_type)
        if not task_class:
            raise ValueError(f"Task {task_type} not found in registry")
        
        logger.info(f"Executing task {task_def.name} (type: {task_type})")
        task_instance = task_class()

        workflow_output_mode = getattr(task_def, "output_mode", None)
        # Merge: system (API/builtins + DB) then workflow params (workflow wins per key)
        self._apply_task_param_defaults(task_def, task_type)
        # output_mode usually lives on the task def; allow system/reserved params when workflow omitted it
        if workflow_output_mode in (None, "") and task_def.params:
            om = task_def.params.get("output_mode")
            if om:
                task_def.output_mode = om

        # Set task_queue_client reference for tasks that need to spawn additional jobs
        if hasattr(task_instance, 'task_queue_client'):
            task_instance.task_queue_client = self.task_queue_client
            logger.debug(f"Set task_queue_client reference for {task_def.name}")

        # Convert new format to legacy format for compatibility if needed
        #legacy_task_def = self._convert_to_legacy_format(task_def)

        # Prepare input data using async method for better performance
        input_data = await self._prepare_input_data_async(task_instance, task_def)

        if input_data is None:
            logger.info(f"No input for {task_def.name}, skipping task")
            return {}

        # Ensure input_data is a list
        if isinstance(input_data, str):
            input_data = [input_data]

        try:
            if not self.job_manager:
                raise RuntimeError("WorkerJobManager not initialized - cannot execute tasks")

            # Unified execution path: all tasks use generate_commands
            proxy_enabled = task_def.use_proxy and hasattr(task_instance, 'supports_proxy') and task_instance.supports_proxy()
            if proxy_enabled:
                logger.info(f"Using WorkerJobManager with proxy for task {task_def.name}")
                processed_assets = await self._execute_task_with_job_manager(
                    task_def, task_instance, program_name, input_data, step_num, step_name, progressive_assets_sent_count
                )
            else:
                logger.info(f"Using unified execution for task {task_def.name}")
                processed_assets = await self._execute_task_unified(
                    task_def, task_instance, program_name, input_data, step_num, step_name, progressive_assets_sent_count
                )
            
            # Store assets in local asset store for step dependencies (both orchestrator and non-orchestrator paths)
            if processed_assets:
                self.asset_processor.store_assets(step_name, processed_assets)
            
            # Handle typosquat processing first, regardless of asset processing method
            if not task_def.internal and processed_assets:
                # Check for typosquat data
                typosquat_urls = processed_assets.get(FindingType.TYPOSQUAT_URL, [])
                typosquat_screenshots = processed_assets.get(FindingType.TYPOSQUAT_SCREENSHOT, [])
                typosquat_domains = processed_assets.get(FindingType.TYPOSQUAT_DOMAIN, [])

                # Serialize Pydantic objects to dicts if needed (with JSON-compatible datetime serialization)
                if typosquat_urls and len(typosquat_urls) > 0:
                    if hasattr(typosquat_urls[0], 'model_dump'):
                        # Pydantic v2: use mode='json' for JSON-compatible serialization (datetime -> str)
                        typosquat_urls = [url.model_dump(mode='json') for url in typosquat_urls]
                    elif hasattr(typosquat_urls[0], 'dict'):
                        # Pydantic v1: dict() doesn't serialize datetimes, so do it manually
                        typosquat_urls = [self._serialize_asset(url) for url in typosquat_urls]

                if typosquat_screenshots and len(typosquat_screenshots) > 0:
                    if hasattr(typosquat_screenshots[0], 'model_dump'):
                        typosquat_screenshots = [ss.model_dump(mode='json') for ss in typosquat_screenshots]
                    elif hasattr(typosquat_screenshots[0], 'dict'):
                        typosquat_screenshots = [self._serialize_asset(ss) for ss in typosquat_screenshots]

                if typosquat_domains and len(typosquat_domains) > 0:
                    if hasattr(typosquat_domains[0], 'model_dump'):
                        typosquat_domains = [d.model_dump(mode='json') for d in typosquat_domains]
                    elif hasattr(typosquat_domains[0], 'dict'):
                        typosquat_domains = [self._serialize_asset(d) for d in typosquat_domains]


                # Handle typosquat domains first
                if typosquat_domains:
                    logger.info(f"Processing {len(typosquat_domains)} typosquat domains")
                    if self.execution_id:
                        success = self.data_api_client._send_typosquat_assets(
                            typosquat_domains, program_name
                        )
                        if success:
                            logger.info("Successfully sent typosquat domains to findings endpoint")
                        else:
                            logger.warning("Failed to send typosquat domains to findings endpoint")

                # Handle typosquat URLs and screenshots
                if typosquat_urls:
                    logger.info(f"Processing {len(typosquat_urls)} typosquat URLs")
                    if self.execution_id:
                        # Check if this task spawned screenshot jobs - if so, don't process screenshots here
                        # as they will be handled by the spawned job processing
                        has_flag = hasattr(task_instance, 'has_spawned_screenshot_jobs')
                        flag_value = getattr(task_instance, 'has_spawned_screenshot_jobs', False) if has_flag else False
                        
                        if has_flag and flag_value:
                            logger.info("Task has spawned screenshot jobs - skipping screenshot processing here to prevent duplication")
                            # Only send URLs, not screenshots
                            success = self._send_typosquat_urls_and_screenshots_after_domains(
                                step_name, program_name, self.execution_id, typosquat_urls, []
                            )
                        else:
                            logger.info("Task has not spawned screenshot jobs - processing screenshots normally")
                            success = self._send_typosquat_urls_and_screenshots_after_domains(
                                step_name, program_name, self.execution_id, typosquat_urls, typosquat_screenshots
                            )
                        
                        if success:
                            logger.info("Successfully sent typosquat URLs and screenshots")
                        else:
                            logger.warning("Failed to send some typosquat URLs and screenshots")

            # Wait for any background tasks (like screenshot spawning) to complete first
            if hasattr(self.execution_manager, 'cleanup_background_tasks'):
                logger.debug("Waiting for background tasks to complete before checking spawned jobs")
                await self.execution_manager.cleanup_background_tasks()
            
            # Allow time for async spawning tasks to register jobs
            await asyncio.sleep(0.1)
            
            # Check if task instance has spawned jobs that need to be waited for
            if task_instance.spawned_job_names:
                logger.info(f"🔄 Task {task_def.name} has spawned {len(task_instance.spawned_job_names)} jobs, waiting for completion...")
                try:
                    job_statuses = await task_instance.wait_for_spawned_jobs(timeout=3600, task_queue_client=self.task_queue_client)  # 1 hour timeout
                    succeeded = sum(1 for status in job_statuses.values() if status == 'succeeded')
                    failed = sum(1 for status in job_statuses.values() if status == 'failed')
                    logger.info(f"✅ All spawned jobs completed: {succeeded} succeeded, {failed} failed")

                    # Process spawned task outputs and merge with main results
                    if hasattr(task_instance, 'process_spawned_task_outputs'):
                        logger.info("📊 Processing spawned task outputs and merging with main results")
                        spawned_outputs = task_instance.process_spawned_task_outputs()

                        if spawned_outputs:
                            logger.info(f"🔄 Merging {len(spawned_outputs)} spawned output types with main results")

                            # Merge spawned outputs with processed_assets
                            for asset_type, spawned_assets in spawned_outputs.items():
                                if asset_type in processed_assets:
                                    # Merge with existing assets
                                    existing_count = len(processed_assets[asset_type])
                                    processed_assets[asset_type].extend(spawned_assets)
                                    logger.info(f"✅ Merged {len(spawned_assets)} {asset_type.value} assets (total: {existing_count + len(spawned_assets)})")
                                else:
                                    # Add new asset type
                                    processed_assets[asset_type] = spawned_assets
                                    logger.info(f"✅ Added {len(spawned_assets)} new {asset_type.value} assets")
                        else:
                            logger.info("📊 No spawned outputs to merge")
                            
                except Exception as e:
                    logger.error(f"Error waiting for spawned jobs: {e}")
                    logger.exception("Full traceback:")
            else:
                logger.debug(f"Task {task_def.name} has no spawned jobs to wait for")

            # Check if asset coordination has already handled the assets for this step
            asset_coordination_used = self._check_asset_coordination_used(step_name)
            logger.info(f"Asset coordination check result for step {step_name}: {asset_coordination_used}")

            if asset_coordination_used:
                logger.info(f"Skipping batch sending since asset coordination already handled assets for step {step_name}")
                # Create a successful TaskResult for timestamp tracking since asset coordination bypassed normal execution
                if not task_results:  # Only create if we don't already have results
                    from task_components import TaskResult
                    task_results = [TaskResult(
                        task_id="asset-coordination-task",
                        success=True,  # Mark as successful since asset coordination completed successfully
                        output="",
                        parsed_assets=processed_assets,
                        execution_time=0.0,
                        error=None
                    )]

                # Update last execution timestamps for successful targets before returning
                # Skip for orchestrator tasks since they handle their own timestamp updates
                if not hasattr(task_instance, 'execute_task') or not callable(task_instance.execute_task):
                    await self._update_timestamps_for_successful_tasks(task_results, task_instance, task_def, input_data)
                # Convert to consistent tracking format even when asset coordination is used
                # For orchestrator tasks, task_results is not available, so pass empty list
                task_results_for_tracking = task_results if not hasattr(task_instance, 'execute_task') or not callable(task_instance.execute_task) else []
                return self._convert_assets_to_tracking_format(processed_assets, task_results_for_tracking)

            # Progressive streaming sends assets as chunks complete, so we don't need to send them all here
            # However, orchestrator tasks return final aggregated results and should always be sent via batch
            is_orchestrator_task = hasattr(task_instance, 'execute_task') and callable(task_instance.execute_task)

            # Determine if we should skip batch sending due to progressive streaming
            skip_batch_due_to_progressive = False
            if self.progressive_streaming_enabled and not is_orchestrator_task:
                # Get streaming statistics from execution_manager
                progressive_assets_sent = 0
                if self.execution_manager and self.execution_manager.progressive_streamer:
                    stats = self.execution_manager.progressive_streamer.get_streaming_stats()
                    progressive_assets_sent = stats['sent_assets_count']

                # Add assets sent via WorkerJobManager progressive processing
                if progressive_assets_sent_count[0] > 0:
                    logger.info(f"WorkerJobManager progressive streaming: {progressive_assets_sent_count[0]} assets sent")

                total_progressive_assets = progressive_assets_sent + progressive_assets_sent_count[0]
                logger.info(f"Total progressive streaming: {total_progressive_assets} assets sent, "
                          f"{stats['failed_sends'] if 'stats' in locals() and stats else 0} failed sends")

                # Check if progressive streaming sent assets
                if total_progressive_assets > 0:
                    logger.info("Skipping batch sending since progressive streaming handled asset delivery")
                    skip_batch_due_to_progressive = True
                    # Note: Typosquat processing is now handled earlier in the method
                #else:
                    # Progressive streaming sent no assets - fallback to batch mode
                    #logger.warning("Progressive streaming was enabled but sent 0 assets, falling back to batch sending")
            elif is_orchestrator_task:
                # Orchestrator tasks always use batch sending for their final aggregated results
                logger.info(f"Orchestrator task {task_def.name} detected - using batch sending for aggregated results")

            # Send assets via batch mode if not skipped due to progressive streaming

            if not skip_batch_due_to_progressive and not task_def.internal and processed_assets:
                if assets_already_sent:
                    logger.info("Assets already sent in this task execution, skipping orchestrator batch mode")
                elif not self.execution_id:
                    logger.error("Execution ID not set, cannot send assets")
                    return {}
                else:
                    # Filter out typosquat fields before sending to send_assets
                    assets_to_send = {k: v for k, v in processed_assets.items() if k != '_typosquat_urls' and k != '_typosquat_screenshots'}

                    # Separate nuclei findings, broken link findings, and wpscan findings from other assets
                    nuclei_findings = None
                    broken_link_findings = None
                    wpscan_findings = None
                    regular_assets = {}
                    
                    for k, v in assets_to_send.items():
                        if "typosquat" not in k.value.lower():  # Exclude typosquat assets
                            if k == FindingType.NUCLEI:
                                nuclei_findings = v  # Extract nuclei findings
                            elif k == FindingType.BROKEN_LINK:
                                broken_link_findings = v  # Extract broken link findings
                            elif k == FindingType.WPSCAN:
                                wpscan_findings = v  # Extract WPScan findings
                            else:
                                regular_assets[k] = v  # Keep other assets
                    
                    # Send nuclei findings to dedicated endpoint
                    if nuclei_findings:
                        logger.info(f"📤 Sending {len(nuclei_findings)} nuclei findings to dedicated endpoint")

                        # Convert nuclei findings to list format for dedicated endpoint
                        try:
                            # Include workflow context for job registration
                            workflow_context = {}
                            if hasattr(self, 'workflow_context') and self.workflow_context:
                                workflow_context.update({
                                    'workflow_id': getattr(self.workflow_context, 'id', None),
                                    'program_name': self.program_name
                                })
                            if hasattr(self, 'execution_id') and self.execution_id:
                                workflow_context['execution_id'] = self.execution_id

                            nuclei_response = await self.data_api_client.post_nuclei_findings_unified(
                                nuclei_findings, program_name,
                                workflow_id=workflow_context.get('workflow_id'),
                                step_name=step_name,
                                execution_id=workflow_context.get('execution_id')
                            )
                            nuclei_success = nuclei_response.get("status") != "error"
                            logger.info(f"📤 NUCLEI SENDING RESULT: {nuclei_success}")
                            if nuclei_success:
                                # Store API response data for workflow status updates
                                if nuclei_response and 'summary' in nuclei_response:
                                    self._store_step_api_response(step_name, nuclei_response)

                                # Track nuclei findings job if it's async
                                processing_mode = nuclei_response.get("processing_mode", "unknown")
                                if processing_mode in ["background", "unified_async"]:
                                    job_id = nuclei_response.get("job_id")
                                    if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                                        try:
                                            # Track job with progressive streamer
                                            self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                            logger.debug(f"Registered findings job {job_id} for step {step_name}")
                                        except Exception as e:
                                            logger.error(f"❌ Failed to register nuclei findings job {job_id} with progressive streamer: {e}")
                                    else:
                                        logger.warning(f"⚠️ Cannot register nuclei findings job {job_id}: execution_manager={self.execution_manager is not None}, has_progressive_streamer={hasattr(self.execution_manager, 'progressive_streamer') if self.execution_manager else False}, progressive_streamer={self.execution_manager.progressive_streamer if self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') else None}")
                            else:
                                logger.warning("Failed to send nuclei findings to dedicated endpoint")
                        except Exception as e:
                            logger.error(f"Error sending nuclei findings: {e}")
                            nuclei_success = False

                    # Send broken link findings to dedicated endpoint
                    if broken_link_findings:
                        logger.info(f"📤 Sending {len(broken_link_findings)} broken link findings to dedicated endpoint")
                        
                        try:
                            broken_link_success = self.data_api_client.post_broken_link_findings(
                                broken_link_findings, program_name
                            )
                            if not broken_link_success:
                                logger.warning("Failed to send broken link findings to dedicated endpoint")
                        except Exception as e:
                            logger.error(f"Error sending broken link findings: {e}")
                            broken_link_success = False
                    
                    # Send WPScan findings to dedicated endpoint
                    if wpscan_findings:
                        logger.info(f"📤 Sending {len(wpscan_findings)} WPScan findings to dedicated endpoint")
                        
                        try:
                            # Include workflow context for job registration
                            workflow_context = {}
                            if hasattr(self, 'workflow_context') and self.workflow_context:
                                workflow_context.update({
                                    'workflow_id': getattr(self.workflow_context, 'id', None),
                                    'program_name': self.program_name
                                })
                            if hasattr(self, 'execution_id') and self.execution_id:
                                workflow_context['execution_id'] = self.execution_id

                            wpscan_response = await self.data_api_client.post_wpscan_findings_unified(
                                wpscan_findings, program_name,
                                workflow_id=workflow_context.get('workflow_id'),
                                step_name=step_name,
                                execution_id=workflow_context.get('execution_id')
                            )
                            wpscan_success = wpscan_response.get("status") != "error"
                            logger.info(f"📤 WPSCAN SENDING RESULT: {wpscan_success}")
                            if wpscan_success:
                                # Store API response data for workflow status updates
                                if wpscan_response and 'summary' in wpscan_response:
                                    self._store_step_api_response(step_name, wpscan_response)

                                # Track WPScan findings job if it's async
                                processing_mode = wpscan_response.get("processing_mode", "unknown")
                                if processing_mode in ["background", "unified_async"]:
                                    job_id = wpscan_response.get("job_id")
                                    if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                                        try:
                                            # Track job with progressive streamer
                                            self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                            logger.debug(f"Registered WPScan findings job {job_id} for step {step_name}")
                                        except Exception as e:
                                            logger.error(f"❌ Failed to register WPScan findings job {job_id} with progressive streamer: {e}")
                                    else:
                                        logger.warning(f"⚠️ Cannot register WPScan findings job {job_id}: execution_manager={self.execution_manager is not None}, has_progressive_streamer={hasattr(self.execution_manager, 'progressive_streamer') if self.execution_manager else False}, progressive_streamer={self.execution_manager.progressive_streamer if self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') else None}")
                            else:
                                logger.warning("Failed to send WPScan findings to dedicated endpoint")
                        except Exception as e:
                            logger.error(f"Error sending WPScan findings: {e}")
                            wpscan_success = False
                    else:
                        broken_link_success = True

                    # Send other regular assets (excluding nuclei, broken links, and typosquat)
                    if regular_assets:
                        # Convert AssetType enum keys to string values for API compatibility
                        converted_assets = {}
                        for k, v in regular_assets.items():
                            if hasattr(k, 'value'):
                                converted_assets[k.value] = v
                            else:
                                converted_assets[str(k)] = v

                        success, api_response = self.data_api_client.send_assets(
                            step_name, program_name, self.execution_id, converted_assets, self.asset_processor
                        )
                        if success:
                            # Store API response data for workflow status updates
                            if api_response and 'summary' in api_response:
                                self._store_step_api_response(step_name, api_response)

                            # Only set guard flag if nuclei, broken links, and regular assets succeeded (or weren't present)
                            if (not nuclei_findings or nuclei_success) and (not broken_link_findings or broken_link_success):
                                self._task_assets_sent_guard.add(task_key)
                        else:
                            logger.warning("Failed to send some regular assets to data-api (orchestrator batch mode)")
                    else:
                        # Set guard flag for nuclei-only or broken-link-only processing
                        if (nuclei_findings and nuclei_success) or (broken_link_findings and broken_link_success):
                            self._task_assets_sent_guard.add(task_key)

                # Note: Typosquat processing is now handled earlier in the method

            else:
                # Fallback to traditional batch sending if progressive streaming is disabled
                logger.info("Progressive streaming disabled, using traditional batch sending")

                # Check if progressive streaming already sent assets
                total_progressive_sent = progressive_assets_sent_count[0]
                if total_progressive_sent > 0:
                    logger.info(f"Progressive streaming already sent {total_progressive_sent} assets, skipping fallback")
                    # Skip the entire fallback branch since progressive streaming handled it
                elif assets_already_sent:
                    logger.info("Assets already sent in this task execution, skipping fallback batch mode")
                elif not task_def.internal and processed_assets:
                    if not self.execution_id:
                        logger.error("Execution ID not set, cannot send assets")
                        return {}

                    # Filter out typosquat fields before sending to send_assets
                    assets_to_send = {k: v for k, v in processed_assets.items() if k != '_typosquat_urls' and k != '_typosquat_screenshots'}

                    # Separate nuclei, typosquat, and broken link findings from other assets
                    nuclei_findings = None
                    typosquat_findings = None
                    broken_link_findings = None
                    regular_assets = {}

                    for k, v in assets_to_send.items():
                        if k == FindingType.NUCLEI:
                            nuclei_findings = v  # Extract nuclei findings
                        elif k == FindingType.TYPOSQUAT_DOMAIN:
                            typosquat_findings = v  # Extract typosquat findings
                        elif k == FindingType.BROKEN_LINK:
                            broken_link_findings = v  # Extract broken link findings
                        else:
                            regular_assets[k] = v  # Keep other assets

                    # Send other regular assets FIRST (excluding nuclei and typosquat)
                    if regular_assets:
                        # Convert AssetType enum keys to string values for API compatibility
                        converted_assets = {}
                        for k, v in regular_assets.items():
                            if hasattr(k, 'value'):
                                converted_assets[k.value] = v
                            else:
                                converted_assets[str(k)] = v

                        success, api_response = self.data_api_client.send_assets(
                            step_name, program_name, self.execution_id, converted_assets, self.asset_processor
                        )
                        logger.debug(f"DEBUT SENDING ASSETS: {success}")
                        if success:
                            logger.info("Successfully sent regular assets to data-api (batch mode)")
                            # Store API response data for workflow status updates
                            if api_response and 'summary' in api_response:
                                self._store_step_api_response(step_name, api_response)
                        else:
                            logger.warning("Failed to send some regular assets to data-api (batch mode)")

                    # Send nuclei findings to dedicated endpoint LAST (after related assets are created)
                    nuclei_success = True
                    if nuclei_findings:
                        logger.info(f"📤 Sending {len(nuclei_findings)} nuclei findings to dedicated endpoint (fallback)")

                        try:
                            # Include workflow context for job registration
                            workflow_context = {}
                            if hasattr(self, 'workflow_context') and self.workflow_context:
                                workflow_context.update({
                                    'workflow_id': getattr(self.workflow_context, 'id', None),
                                    'program_name': self.program_name
                                })
                            if hasattr(self, 'execution_id') and self.execution_id:
                                workflow_context['execution_id'] = self.execution_id

                            nuclei_response = await self.data_api_client.post_nuclei_findings_unified(
                                nuclei_findings, program_name,
                                workflow_id=workflow_context.get('workflow_id'),
                                step_name=step_name,
                                execution_id=workflow_context.get('execution_id')
                            )
                            nuclei_success = nuclei_response.get("status") != "error"
                            logger.info(f"📤 NUCLEI SENDING RESULT (fallback): {nuclei_success}")
                            if nuclei_success:
                                # Store API response data for workflow status updates
                                if nuclei_response and 'summary' in nuclei_response:
                                    self._store_step_api_response(step_name, nuclei_response)

                                # Track nuclei findings job if it's async
                                processing_mode = nuclei_response.get("processing_mode", "unknown")
                                if processing_mode in ["background", "unified_async"]:
                                    job_id = nuclei_response.get("job_id")
                                    if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                                        try:
                                            logger.info(f"🔍 DEBUG: Attempting to register nuclei findings job {job_id} with progressive streamer")
                                            # Track job for step coordination

                                            # Track job with progressive streamer
                                            self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                            logger.debug(f"Registered findings job {job_id} for step {step_name}")
                                        except Exception as e:
                                            logger.error(f"❌ Failed to register nuclei findings job {job_id} with progressive streamer: {e}")
                                            logger.error(f"🔍 DEBUG: Exception details: {type(e).__name__}: {str(e)}")
                                            import traceback
                                            logger.error(f"🔍 DEBUG: Full traceback: {traceback.format_exc()}")
                                    else:
                                        logger.warning(f"⚠️ Cannot register nuclei findings job {job_id}: execution_manager={self.execution_manager is not None}, has_progressive_streamer={hasattr(self.execution_manager, 'progressive_streamer') if self.execution_manager else False}, progressive_streamer={self.execution_manager.progressive_streamer if self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') else None}")
                            else:
                                logger.warning("Failed to send nuclei findings to dedicated endpoint (fallback)")
                        except Exception as e:
                            logger.error(f"Error sending nuclei findings (fallback): {e}")
                            nuclei_success = False

                    # Send typosquat findings to dedicated endpoint (after nuclei, before setting guard flag)
                    typosquat_success = True
                    typosquat_response = {}
                    if typosquat_findings:
                        logger.info(f"🔍 TYPOSQUAT: Sending {len(typosquat_findings)} typosquat findings to dedicated endpoint (fallback)")

                        typosquat_success, typosquat_response = self.data_api_client.send_typosquat_findings(
                            step_name, program_name, self.execution_id, typosquat_findings, self.asset_processor
                        )
                        logger.info(f"🔍 TYPOSQUAT SENDING RESULT (fallback): {typosquat_success}")
                        if typosquat_success:
                            # Store API response data for workflow status updates
                            if typosquat_response and 'summary' in typosquat_response:
                                self._store_step_api_response(step_name, typosquat_response)
                        else:
                            logger.warning("Failed to send typosquat findings to dedicated endpoint (fallback)")

                    # Send broken link findings to dedicated endpoint
                    broken_link_success = True
                    if broken_link_findings:
                        logger.info(f"📤 Sending {len(broken_link_findings)} broken link findings to dedicated endpoint (fallback)")
                        try:
                            broken_link_success = self.data_api_client.post_broken_link_findings(
                                broken_link_findings, program_name
                            )
                            if not broken_link_success:
                                logger.warning("Failed to send broken link findings to dedicated endpoint (fallback)")
                        except Exception as e:
                            logger.error(f"Error sending broken link findings (fallback): {e}")
                            broken_link_success = False
                    else:
                        broken_link_success = True

                    # Set guard flag if nuclei, typosquat, broken links, and regular assets succeeded
                    if (not nuclei_findings or nuclei_success) and (not typosquat_findings or typosquat_success) and (not broken_link_findings or broken_link_success):
                        self._task_assets_sent_guard.add(task_key)

                    # Note: Typosquat processing is now handled earlier in the method
            
            # Wait for screenshot tasks to complete if we spawned any
            if hasattr(self, 'spawned_screenshot_tasks') and self.spawned_screenshot_tasks:
                logger.info(f"📸 Waiting for {len(self.spawned_screenshot_tasks)} screenshot tasks to complete")
                try:
                    await self._wait_for_screenshot_tasks_completion(timeout=1800)  # 30 minutes timeout
                except Exception as e:
                    logger.error(f"Error waiting for screenshot tasks completion: {e}")
            
            # Update last execution timestamps for successful targets
            # Skip for orchestrator tasks since they handle their own timestamp updates
            if not hasattr(task_instance, 'execute_task') or not callable(task_instance.execute_task):
                if getattr(self, '_last_batch_result', None) is not None:
                    logger.info(f"Updating timestamps for WorkerJobManager: {self._last_batch_result}")
                    await self._update_timestamps_for_worker_job_manager(self._last_batch_result, task_instance, task_def, input_data)
            
            # For orchestrator tasks, task_results is not available, so pass empty list
            task_results_for_tracking = task_results if not hasattr(task_instance, 'execute_task') or not callable(task_instance.execute_task) else []
            return self._convert_assets_to_tracking_format(processed_assets, task_results_for_tracking)
                
        except Exception as e:
            logger.error(f"Error executing task {task_def.name}: {str(e)}")
            logger.exception(e)
            raise
    
    def _convert_assets_to_tracking_format(self, processed_assets: Dict[AssetType, List[Any]], 
                                         task_results: List) -> Dict:
        """Convert new asset format back to old tracking format for compatibility"""
        # This is a temporary compatibility layer
        # In Phase 2, we should update all callers to use the new format
        tracking_format = {}
        
        # Add processed assets to the tracking format (includes merged spawned outputs)
        for task_result in task_results:
            if task_result.success and task_result.parsed_assets:
                tracking_format[task_result.task_id] = {
                    "status": "Completed",
                    "assets": task_result.parsed_assets,
                    "output_processed": True,
                    "output": {"output": task_result.output, "success": task_result.success}
                }
        
        # Override with final processed_assets that include spawned outputs merged
        if processed_assets:
            # Convert AssetType keys to strings and use the merged assets
            final_assets = {}
            for asset_type, assets in processed_assets.items():
                # Handle both AssetType enum objects and string keys
                if hasattr(asset_type, 'value'):
                    # AssetType enum object
                    final_assets[asset_type.value] = assets
                else:
                    # String key (like '_typosquat_urls')
                    final_assets[str(asset_type)] = assets
            
            # Create a single task entry with the merged assets
            task_id = list(tracking_format.keys())[0] if tracking_format else "merged_task"
            tracking_format[task_id] = {
                "status": "Completed", 
                "assets": final_assets,
                "output_processed": True,
                "output": {"output": "Merged results including spawned outputs", "success": True}
            }
            
            logger.debug(f"📊 Final tracking format includes {sum(len(assets) for assets in final_assets.values())} total assets")
        
        return tracking_format

    def _resolve_input_mapping(self, input_mapping: Dict[str, Union[str, List[str]]]) -> List[str]:
        """Resolve input mapping to actual input data. Supports multiple sources per input (array of paths)."""
        all_input_data = []
        
        for input_key, mapping_path in input_mapping.items():
            # Normalize to list: support both single string and array of strings
            paths = [mapping_path] if isinstance(mapping_path, str) else mapping_path
            
            for path in paths:
                logger.debug(f"Resolving input mapping: {input_key} -> {path}")
                
                # Parse the mapping path
                path_parts = path.split('.')
                
                if len(path_parts) < 2:
                    logger.warning(f"Invalid mapping path format: {path}")
                    continue
                    
                if path_parts[0] == 'inputs':
                    # Reference to workflow inputs: inputs.input_1
                    input_data = self._resolve_workflow_input(path_parts[1])
                    if input_data:
                        all_input_data.extend(input_data)
                        
                elif path_parts[0] == 'steps':
                    # Reference to step outputs: steps.step_1.task_name.outputs.domains
                    if len(path_parts) >= 5 and path_parts[3] == 'outputs':
                        step_name = path_parts[1]
                        task_name = path_parts[2]
                        output_type = path_parts[4]
                        input_data = self._resolve_step_output(step_name, task_name, output_type)
                        if input_data:
                            all_input_data.extend(input_data)
                    else:
                        logger.warning(f"Invalid step output path format: {path}")
                else:
                    logger.warning(f"Unknown mapping path type: {path_parts[0]}")
        
        # Deduplicate while preserving order
        return list(dict.fromkeys(all_input_data))
    
    def _resolve_workflow_input(self, input_name: str) -> List[str]:
        """Resolve a workflow input to actual data"""
        if not self.workflow_context or not self.workflow_context.inputs:
            logger.warning(f"No workflow context or inputs available to resolve: {input_name}")
            return []
            
        input_def = self.workflow_context.inputs.get(input_name)
        if not input_def:
            logger.warning(f"Input definition not found: {input_name}")
            return []
            
        if input_def.type == 'direct':
            # Direct input with static values
            values = input_def.values or []
            logger.debug(f"Resolved workflow input '{input_name}' to values: {values}")
            return values
            
        elif input_def.type == 'program_asset':
            # Program asset input - this will be handled later in the async method
            # For now, just return an indicator that this needs async resolution

            # Backward compatibility: Check if asset_type is actually a finding type
            finding_types = ['typosquat_url', 'typosquat_domain', 'typosquat_apex_domain', 'external_link']
            if hasattr(input_def, 'asset_type') and input_def.asset_type in finding_types:
                logger.warning(f"Input '{input_name}' has type='program_asset' with asset_type='{input_def.asset_type}'. "
                             f"This is a finding type. Auto-converting to program_finding for backward compatibility. "
                             f"Please update the workflow definition to use type='program_finding' with finding_type='{input_def.asset_type}'")
                return [f"__PROGRAM_FINDING__{input_name}"]

            return [f"__PROGRAM_ASSET__{input_name}"]

        elif input_def.type == 'program_finding':
            # Program finding input - this will be handled later in the async method
            # For now, just return an indicator that this needs async resolution
            return [f"__PROGRAM_FINDING__{input_name}"]

        elif input_def.type == 'program_protected_domains':
            # Program protected domains input - will be handled in async method
            return [f"__PROGRAM_PROTECTED_DOMAINS__{input_name}"]

        elif input_def.type == 'program_scope_domains':
            # Program scope domains input - apex domains from domain_regex, will be handled in async method
            return [f"__PROGRAM_SCOPE_DOMAINS__{input_name}"]

        else:
            logger.warning(f"Unknown input type: {input_def.type}")
            return []
    
    @staticmethod
    def _apex_domain_asset_name(asset: Any) -> str:
        if isinstance(asset, dict):
            return str(asset.get("name") or asset)
        return str(getattr(asset, "name", asset))

    def _merge_batch_into_aggregated_assets(
        self,
        aggregated_assets: Dict[Any, List[Any]],
        batch_assets: Dict[Any, List[Any]],
        *,
        ip_field: str = "ip",
        service_extend: bool = True,
    ) -> None:
        """Merge batch_assets into aggregated_assets with O(total assets) deduplication per type."""
        for at, assets in batch_assets.items():
            if not assets:
                continue
            if at == AssetType.SUBDOMAIN:
                target = aggregated_assets.setdefault(at, [])
                seen = {getattr(x, "name", str(x)) for x in target}
                for a in assets:
                    key = getattr(a, "name", str(a))
                    if key not in seen:
                        seen.add(key)
                        target.append(a)
            elif at == AssetType.IP:
                target = aggregated_assets.setdefault(at, [])
                seen = {getattr(x, ip_field, str(x)) for x in target}
                for a in assets:
                    key = getattr(a, ip_field, str(a))
                    if key not in seen:
                        seen.add(key)
                        target.append(a)
            elif at == AssetType.APEX_DOMAIN:
                target = aggregated_assets.setdefault(at, [])
                seen = {self._apex_domain_asset_name(x) for x in target}
                for a in assets:
                    key = self._apex_domain_asset_name(a)
                    if key not in seen:
                        seen.add(key)
                        target.append(a)
            elif at == AssetType.URL:
                target = aggregated_assets.setdefault(at, [])
                seen = {getattr(x, "url", str(x)) for x in target}
                for a in assets:
                    key = getattr(a, "url", str(a))
                    if key not in seen:
                        seen.add(key)
                        target.append(a)
            elif at == AssetType.SERVICE and service_extend:
                aggregated_assets.setdefault(at, []).extend(assets)
            else:
                target = aggregated_assets.setdefault(at, [])
                seen = {str(x) for x in target}
                for a in assets:
                    key = str(a)
                    if key not in seen:
                        seen.add(key)
                        target.append(a)

    def _extend_batch_bucket_unique(
        self,
        batch_assets: Dict[Any, List[Any]],
        asset_type: Any,
        assets: List[Any],
        *,
        ip_field: str,
    ) -> None:
        """Append parsed assets into batch_assets[bucket] with O(len(bucket)+len(assets)) deduplication."""
        if not assets:
            return
        bucket = batch_assets.setdefault(asset_type, [])
        if asset_type.value == "subdomain":
            seen = {getattr(x, "name", str(x)) for x in bucket}
            for asset in assets:
                key = getattr(asset, "name", str(asset))
                if key not in seen:
                    seen.add(key)
                    bucket.append(asset)
        elif asset_type.value == "ip":
            seen = {getattr(x, ip_field, str(x)) for x in bucket}
            for asset in assets:
                key = getattr(asset, ip_field, str(asset))
                if key not in seen:
                    seen.add(key)
                    bucket.append(asset)
        elif asset_type.value == "url":
            seen = {getattr(x, "url", str(x)) for x in bucket}
            for asset in assets:
                key = getattr(asset, "url", str(asset))
                if key not in seen:
                    seen.add(key)
                    bucket.append(asset)
        else:
            seen = {str(x) for x in bucket}
            for asset in assets:
                key = str(asset)
                if key not in seen:
                    seen.add(key)
                    bucket.append(asset)

    def _resolve_step_output(self, step_name: str, task_name: str, output_type: str) -> List[str]:
        """Resolve step output to actual data"""
        logger.debug(f"Resolving step output: {step_name}.{task_name}.{output_type}")
        
        # Map output types to asset types
        asset_type_mapping = {
            'subdomains': 'subdomain',
            'domains': 'subdomain',
            'apex_domains': 'apex_domain',
            'ips': 'ip', 
            'urls': 'url',
            'services': 'service',
            'certificates': 'certificate',
            'strings': 'string'
        }
        
        asset_type = asset_type_mapping.get(output_type, output_type)
        step_assets = self.asset_store.get_step_assets(step_name, asset_type)
        if not step_assets:
            logger.warning(f"No {asset_type} assets found for step {step_name}")
            return []
            
        # Convert assets to string list based on type
        result = []
        for asset in step_assets:
            if isinstance(asset, str):
                result.append(asset)
            elif isinstance(asset, dict) and asset.get('name'):
                result.append(str(asset['name']))
            elif hasattr(asset, 'name'):  # Domain assets
                result.append(asset.name)
            elif hasattr(asset, 'ip'):  # IP assets
                result.append(asset.ip)
            elif hasattr(asset, 'url'):  # URL assets
                result.append(asset.url)
            else:
                result.append(str(asset))
                
        logger.info(f"Resolved {len(result)} {output_type} from step {step_name}")
        return result

    async def _prepare_input_data_async(self, task: Task, task_def: TaskDefinition) -> Optional[Union[str, List[str]]]:
        """Async version of input data preparation with optimized API calls"""
        from task_components import MemoryOptimizationConfig
        memory_config = MemoryOptimizationConfig.from_environment()
        input_data = []
        # Handle new input_mapping format first
        if task_def.input_mapping:
            input_data = self._resolve_input_mapping(task_def.input_mapping)
            
            # Handle program asset, finding, protected domains, and scope domains inputs that need async resolution
            program_asset_inputs = []
            program_finding_inputs = []
            program_protected_domains_inputs = []
            program_scope_domains_inputs = []
            resolved_inputs = []

            for item in input_data:
                if isinstance(item, str) and item.startswith('__PROGRAM_ASSET__'):
                    # Extract input name and resolve async
                    input_name = item.replace('__PROGRAM_ASSET__', '')
                    program_asset_inputs.append(input_name)
                elif isinstance(item, str) and item.startswith('__PROGRAM_FINDING__'):
                    # Extract input name and resolve async
                    input_name = item.replace('__PROGRAM_FINDING__', '')
                    program_finding_inputs.append(input_name)
                elif isinstance(item, str) and item.startswith('__PROGRAM_PROTECTED_DOMAINS__'):
                    input_name = item.replace('__PROGRAM_PROTECTED_DOMAINS__', '')
                    program_protected_domains_inputs.append(input_name)
                elif isinstance(item, str) and item.startswith('__PROGRAM_SCOPE_DOMAINS__'):
                    input_name = item.replace('__PROGRAM_SCOPE_DOMAINS__', '')
                    program_scope_domains_inputs.append(input_name)
                else:
                    resolved_inputs.append(item)

            # Resolve program asset inputs asynchronously
            if program_asset_inputs:
                async_data = await self._resolve_program_asset_inputs_async(program_asset_inputs, memory_config)
                resolved_inputs.extend(async_data)

            # Resolve program finding inputs asynchronously
            if program_finding_inputs:
                async_data = await self._resolve_program_finding_inputs_async(program_finding_inputs, memory_config)
                resolved_inputs.extend(async_data)

            # Resolve program protected domains inputs asynchronously
            if program_protected_domains_inputs:
                async_data = await self._resolve_program_protected_domains_inputs_async(program_protected_domains_inputs)
                resolved_inputs.extend(async_data)

            # Resolve program scope domains inputs asynchronously
            if program_scope_domains_inputs:
                async_data = await self._resolve_program_scope_domains_inputs_async(program_scope_domains_inputs)
                resolved_inputs.extend(async_data)

            input_data = resolved_inputs
            
        # # Legacy support: If direct input is provided, use it
        # elif task_def.input is not None:
        #     logger.debug(f"Using legacy direct input: {task_def.input}")
        #     if not isinstance(task_def.input, list):
        #         task_def.input = [task_def.input]
        #     logger.debug(f"Direct input list: {task_def.input}")
        #     input_data = task_def.input
        
        # # Legacy support: If input_from is provided, collect assets from those steps or program assets
        # elif task_def.input_from is not None:
        #     # Use async client for API calls
        #     from task_components import AsyncDataApiClient
        #     async with AsyncDataApiClient(API_URL, self.redis_client) as async_client:
        #         for source in task_def.input_from:
        #             logger.info(f"Preparing input data from source: {source}")
        #             source_parts = source.split(".")
        #             source_type = source_parts[0]
                    
        #             if source_type == "program":
        #                 try:
        #                     logger.info(f"Fetching program assets for {self.program_name}")
        #                     asset_type = source_parts[1]
        #                     filter_type = source_parts[2] if len(source_parts) > 2 else None
                            
        #                     logger.info(f"Asset type: {asset_type}")
                            
        #                     # Check program stats first (with caching)
        #                     if not self.program_name:
        #                         logger.error("Program name not set, cannot fetch program stats")
        #                         continue
        #                     stats_data = await async_client.get_program_stats(self.program_name)
        #                     if stats_data:
        #                         logger.info(f"Program asset stats: {stats_data}")
        #                         details_map = {
        #                             'apex-domain': 'apex_domain_details',
        #                             'subdomain': 'subdomain_details',
        #                             'ip': 'ip_details', 
        #                             'service': 'service_details',
        #                             'url': 'url_details'
        #                         }
        #                         details_key = details_map.get(asset_type)
        #                         if details_key and details_key in stats_data:
        #                             type_count = stats_data[details_key].get('total', 0)
        #                             if type_count == 0:
        #                                 logger.warning(f"No {asset_type} assets found for program {self.program_name}")
        #                         else:
        #                             logger.warning(f"No stats found for asset type {asset_type}")
                            
        #                     # Use memory-efficient asset fetching for large datasets
        #                     all_assets = []
        #                     if stats_data:
        #                         details_key = details_map.get(asset_type)
        #                         total_count = stats_data.get(details_key, {}).get('total', 0) if details_key else 0
                                
        #                         # Use streaming approach for large datasets
        #                         if total_count > memory_config.streaming_asset_threshold:
        #                             logger.info(f"Using streaming approach for {total_count} {asset_type} assets")
        #                             all_assets = await self._fetch_assets_streaming(
        #                                 async_client, asset_type, self.program_name, total_count, memory_config
        #                             )
        #                         else:
        #                             all_assets = await self._fetch_assets_standard(
        #                                 async_client, asset_type, self.program_name, memory_config
        #                             )
        #                     else:
        #                         all_assets = await self._fetch_assets_standard(
        #                             async_client, asset_type, self.program_name, memory_config
        #                         )
                            
        #                     # Apply input_filter if specified
        #                     logger.debug(f"Task definition input_filter: {task_def.input_filter}")
        #                     logger.debug(f"Task definition type: {type(task_def.input_filter)}")
        #                     logger.debug(f"All assets count: {len(all_assets) if all_assets else 0}")
                            
        #                     if task_def.input_filter and all_assets:
        #                         try:
        #                             logger.info(f"Applying input filter: {task_def.input_filter}")
        #                             logger.debug(f"Before filtering: {len(all_assets)} assets")
        #                             if len(all_assets) > 0:
        #                                 logger.debug(f"Sample asset structure: {all_assets[0]}")
        #                             asset_filter = AssetFilter(task_def.input_filter)
        #                             all_assets = asset_filter.filter_assets(all_assets)
        #                             logger.info(f"After filtering: {len(all_assets)} assets remaining")
        #                             if len(all_assets) > 0:
        #                                 logger.debug(f"Sample filtered asset: {all_assets[0]}")
        #                         except Exception as e:
        #                             logger.error(f"Error applying input filter '{task_def.input_filter}': {str(e)}")
        #                             logger.warning("Continuing without filter due to error")
        #                     elif task_def.input_filter and not all_assets:
        #                         logger.warning(f"Input filter specified but no assets to filter: {task_def.input_filter}")
        #                     elif not task_def.input_filter:
        #                         logger.debug("No input filter specified")
                            
        #                     # Process assets based on type and filter
        #                     if asset_type == "subdomain":
        #                         if filter_type == "resolved":
        #                             resolved_domains = [asset["name"] for asset in all_assets if asset.get("ip")]
        #                             input_data.extend(resolved_domains)
        #                         elif filter_type == "unresolved":
        #                             unresolved_domains = [asset["name"] for asset in all_assets if not asset.get("ip")]
        #                             input_data.extend(unresolved_domains)
        #                         else:
        #                             domain_names = [asset["name"] for asset in all_assets]
        #                             input_data.extend(domain_names)
        #                     elif asset_type == "apex-domain":
        #                         apex_domains = [asset["name"] for asset in all_assets]
        #                         input_data.extend(apex_domains)
        #                     elif asset_type == "ip":
        #                         if filter_type == "!service_provider":
        #                             for ip in all_assets:
        #                                 if not ip.get("service_provider", ""):
        #                                     input_data.append(ip.get("ip"))
        #                         elif filter_type == "resolved":
        #                             resolved_ips = [asset["ip"] for asset in all_assets if asset.get("ptr")]
        #                             input_data.extend(resolved_ips)
        #                         elif filter_type == "unresolved":
        #                             unresolved_ips = [asset["ip"] for asset in all_assets if not asset.get("ptr")]
        #                             input_data.extend(unresolved_ips)
        #                         else:
        #                             ip_addresses = [asset["ip"] for asset in all_assets]
        #                             input_data.extend(ip_addresses)
                            
        #                     elif asset_type == "url":
        #                         if len(all_assets) > 0:
        #                             logger.info(f"{len(all_assets)} urls found, first url path: {all_assets[0].get('path', 'N/A')}")
        #                         else:
        #                             logger.info(f"{len(all_assets)} urls found")
                                    
        #                         if filter_type == "root":
        #                             urls = [asset["url"] for asset in all_assets if asset.get("path") == "/"]
        #                             logger.info(f"Root urls: {urls}")
        #                             input_data.extend(urls)
        #                         else:
        #                             urls = [asset["url"] for asset in all_assets]
        #                             input_data.extend(urls)
                            
        #                     elif asset_type == "cidr":
        #                         logger.info(f"Fetching CIDR blocks for program {self.program_name}")
                                
        #                         # Get program metadata to fetch CIDR list
        #                         program_data = await async_client.get_program_metadata(self.program_name)
        #                         if program_data:
        #                             cidr_list = program_data.get("cidr_list", [])
        #                             if cidr_list:
        #                                 logger.info(f"Found {len(cidr_list)} CIDR blocks: {cidr_list}")
        #                                 input_data.extend(cidr_list)
        #                             else:
        #                                 logger.warning(f"No CIDR blocks found for program {self.program_name}")
        #                         else:
        #                             logger.warning(f"Could not fetch program metadata for {self.program_name}")
                            
        #                     else:
        #                         logger.warning(f"Unknown asset type: {asset_type}")
        #                         continue
                                
        #                 except Exception as e:
        #                     logger.error(f"Error fetching program assets from data-api: {str(e)}")
        #                     logger.exception(e)
                    
        #             elif source_parts[0] == "step":
        #                 # Handle step-based assets (these don't require API calls)
        #                 source_step = source_parts[1]
        #                 step_assets = []
        #                 asset_type = None
                        
        #                 # Check if specific asset type is requested (e.g., step.step1.ip)
        #                 requested_asset_type = None
        #                 if len(source_parts) > 2:
        #                     requested_asset_type = source_parts[2]
        #                     logger.info(f"Explicit asset type requested for step {source_step}: {requested_asset_type}")
                        
        #                 # If specific asset type is requested, only look for that type
        #                 if requested_asset_type:
        #                     if requested_asset_type == "domain":
        #                         domain_assets = self.asset_store.get_step_assets(source_step, AssetType.SUBDOMAIN.value)
        #                         if domain_assets:
        #                             asset_type = "domain"
        #                             # Convert to dict format for filtering
        #                             for asset in domain_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"name": asset})
        #                                 elif hasattr(asset, 'name'):
        #                                     step_assets.append({"name": asset.name})
        #                                 else:
        #                                     logger.warning(f"Unexpected domain asset type: {type(asset)}")
        #                     elif requested_asset_type == "ip":
        #                         ip_assets = self.asset_store.get_step_assets(source_step, AssetType.IP.value)
        #                         if ip_assets:
        #                             asset_type = "ip"
        #                             # Convert to dict format for filtering
        #                             for asset in ip_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"ip": asset})
        #                                 elif hasattr(asset, 'ip'):
        #                                     step_assets.append({"ip": asset.ip})
        #                                 else:
        #                                     logger.warning(f"Unexpected IP asset type: {type(asset)}")
        #                     elif requested_asset_type == "url":
        #                         url_assets = self.asset_store.get_step_assets(source_step, AssetType.URL.value)
        #                         if url_assets:
        #                             asset_type = "url"
        #                             # Convert to dict format for filtering
        #                             for asset in url_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"url": asset})
        #                                 elif hasattr(asset, 'url'):
        #                                     step_assets.append({"url": asset.url})
        #                                 else:
        #                                     logger.warning(f"Unexpected URL asset type: {type(asset)}")
        #                     elif requested_asset_type == "string":
        #                         string_assets = self.asset_store.get_step_assets(source_step, AssetType.STRING.value)
        #                         if string_assets:
        #                             asset_type = "string"
        #                             step_assets = [{"value": asset} for asset in string_assets]
        #                     elif requested_asset_type == "service":
        #                         service_assets = self.asset_store.get_step_assets(source_step, AssetType.SERVICE.value)
        #                         if service_assets:
        #                             asset_type = "service"
        #                             # Convert to dict format for filtering
        #                             for asset in service_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"service": asset})
        #                                 elif hasattr(asset, 'ip'):
        #                                     step_assets.append({"ip": asset.ip, "port": asset.port, "protocol": asset.protocol, "service": asset.service})
        #                                 else:
        #                                     logger.warning(f"Unexpected service asset type: {type(asset)}")
        #                     elif requested_asset_type == "certificate":
        #                         cert_assets = self.asset_store.get_step_assets(source_step, AssetType.CERTIFICATE.value)
        #                         if cert_assets:
        #                             asset_type = "certificate"
        #                             # Convert to dict format for filtering
        #                             for asset in cert_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"certificate": asset})
        #                                 elif hasattr(asset, 'domain'):
        #                                     step_assets.append({"domain": asset.domain, "issuer": asset.issuer, "valid_until": asset.valid_until})
        #                                 else:
        #                                     logger.warning(f"Unexpected certificate asset type: {type(asset)}")
        #                     elif requested_asset_type == "screenshot":
        #                         screenshot_assets = self.asset_store.get_step_assets(source_step, AssetType.SCREENSHOT.value)
        #                         if screenshot_assets:
        #                             asset_type = "screenshot"
        #                             # Convert to dict format for filtering
        #                             for asset in screenshot_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"screenshot": asset})
        #                                 elif hasattr(asset, 'url'):
        #                                     step_assets.append({"url": asset.url, "filename": asset.filename})
        #                                 else:
        #                                     logger.warning(f"Unexpected screenshot asset type: {type(asset)}")
        #                     elif requested_asset_type == "nuclei":
        #                         nuclei_assets = self.asset_store.get_step_assets(source_step, AssetType.NUCLEI.value)
        #                         if nuclei_assets:
        #                             asset_type = "nuclei"
        #                             # Convert to dict format for filtering
        #                             for asset in nuclei_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"nuclei": asset})
        #                                 elif hasattr(asset, 'url'):
        #                                     step_assets.append({"url": asset.url, "template": asset.template, "severity": asset.severity})
        #                                 else:
        #                                     logger.warning(f"Unexpected nuclei asset type: {type(asset)}")
        #                     elif requested_asset_type == "typosquat":
        #                         typosquat_assets = self.asset_store.get_step_assets(source_step, FindingType.TYPOSQUAT_DOMAIN.value)
        #                         if typosquat_assets:
        #                             asset_type = "typosquat"
        #                             # Convert to dict format for filtering
        #                             for asset in typosquat_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"typosquat": asset})
        #                                 elif hasattr(asset, 'domain'):
        #                                     step_assets.append({"domain": asset.domain, "variation": asset.variation, "risk_score": asset.risk_score})
        #                                 else:
        #                                     logger.warning(f"Unexpected typosquat asset type: {type(asset)}")
        #                     else:
        #                         logger.warning(f"Unknown asset type requested: {requested_asset_type}")
                            
        #                     # If we have step assets from explicit asset type processing, extract values and continue
        #                     if step_assets:
        #                         # Apply input_filter if specified
        #                         logger.debug(f"Task definition input_filter for step assets: {task_def.input_filter}")
        #                         logger.debug(f"Task definition type for step assets: {type(task_def.input_filter)}")
        #                         logger.debug(f"Step assets count: {len(step_assets) if step_assets else 0}")
                                
        #                         if task_def.input_filter and step_assets:
        #                             try:
        #                                 logger.info(f"Applying input filter to step assets: {task_def.input_filter}")
        #                                 logger.debug(f"Before filtering step assets: {len(step_assets)} assets")
        #                                 if len(step_assets) > 0:
        #                                     logger.debug(f"Sample step asset structure: {step_assets[0]}")
        #                                 asset_filter = AssetFilter(task_def.input_filter)
        #                                 step_assets = asset_filter.filter_assets(step_assets)
        #                                 logger.info(f"After filtering step assets: {len(step_assets)} assets remaining")
        #                                 if len(step_assets) > 0:
        #                                     logger.debug(f"Sample filtered step asset: {step_assets[0]}")
        #                             except Exception as e:
        #                                 logger.error(f"Error applying input filter to step assets '{task_def.input_filter}': {str(e)}")
        #                                 logger.warning("Continuing without filter due to error")
        #                         elif task_def.input_filter and not step_assets:
        #                             logger.warning(f"Input filter specified but no step assets to filter: {task_def.input_filter}")
        #                         elif not task_def.input_filter:
        #                             logger.debug("No input filter specified for step assets")
                                
        #                         # Extract values based on asset type
        #                         if asset_type == "domain":
        #                             input_data.extend([asset["name"] for asset in step_assets])
        #                         elif asset_type == "string":
        #                             input_data.extend([asset["value"] for asset in step_assets])
        #                         elif asset_type == "ip":
        #                             input_data.extend([asset["ip"] for asset in step_assets])
        #                         elif asset_type == "url":
        #                             input_data.extend([asset["url"] for asset in step_assets])
        #                         elif asset_type == "service":
        #                             # For services, we typically want the IP:port combination
        #                             input_data.extend([f"{asset['ip']}:{asset['port']}" for asset in step_assets if 'ip' in asset and 'port' in asset])
        #                         elif asset_type == "certificate":
        #                             # For certificates, we typically want the domain
        #                             input_data.extend([asset["domain"] for asset in step_assets if "domain" in asset])
        #                         # elif asset_type == "screenshot":
        #                         #     # For screenshots, we typically want the URL
        #                         #     input_data.extend([asset["url"] for asset in step_assets if "url" in asset])
        #                         # elif asset_type == "nuclei":
        #                         #     # For nuclei findings, we typically want the URL
        #                         #     input_data.extend([asset["url"] for asset in step_assets if "url" in asset])
        #                         # elif asset_type == "typosquat":
        #                         #     # For typosquat findings, we typically want the domain
        #                         #     input_data.extend([asset["domain"] for asset in step_assets if "domain" in asset])
        #                         continue
        #                 else:
        #                     # Fallback to priority-based selection (backward compatibility)
        #                     logger.debug(f"No specific asset type requested for step {source_step}, using priority-based selection")
                            
        #                     # Collect assets from step with priority order
        #                     domain_assets = self.asset_store.get_step_assets(source_step, AssetType.SUBDOMAIN.value)
        #                     if domain_assets:
        #                         asset_type = "domain"
        #                         # Convert to dict format for filtering
        #                         for asset in domain_assets:
        #                             if isinstance(asset, str):
        #                                 step_assets.append({"name": asset})
        #                             elif hasattr(asset, 'name'):
        #                                 step_assets.append({"name": asset.name})
        #                             else:
        #                                 logger.warning(f"Unexpected domain asset type: {type(asset)}")
                            
        #                     if not step_assets:
        #                         string_assets = self.asset_store.get_step_assets(source_step, AssetType.STRING.value)
        #                         if string_assets:
        #                             asset_type = "string"
        #                             step_assets = [{"value": asset} for asset in string_assets]
                            
        #                     if not step_assets:
        #                         ip_assets = self.asset_store.get_step_assets(source_step, AssetType.IP.value)
        #                         if ip_assets:
        #                             asset_type = "ip"
        #                             # Convert to dict format for filtering
        #                             for asset in ip_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"ip": asset})
        #                                 elif hasattr(asset, 'ip'):
        #                                     step_assets.append({"ip": asset.ip})
        #                                 else:
        #                                     logger.warning(f"Unexpected IP asset type: {type(asset)}")
                            
        #                     if not step_assets:
        #                         url_assets = self.asset_store.get_step_assets(source_step, AssetType.URL.value)
        #                         if url_assets:
        #                             asset_type = "url"
        #                             # Convert to dict format for filtering
        #                             for asset in url_assets:
        #                                 if isinstance(asset, str):
        #                                     step_assets.append({"url": asset})
        #                                 elif hasattr(asset, 'url'):
        #                                     step_assets.append({"url": asset.url})
        #                                 else:
        #                                     logger.warning(f"Unexpected URL asset type: {type(asset)}")
                            
        #                     if step_assets:
        #                         # Apply input_filter if specified
        #                         logger.debug(f"Task definition input_filter for step assets: {task_def.input_filter}")
        #                         logger.debug(f"Task definition type for step assets: {type(task_def.input_filter)}")
        #                         logger.debug(f"Step assets count: {len(step_assets) if step_assets else 0}")
                                
        #                         if task_def.input_filter and step_assets:
        #                             try:
        #                                 logger.info(f"Applying input filter to step assets: {task_def.input_filter}")
        #                                 logger.debug(f"Before filtering step assets: {len(step_assets)} assets")
        #                                 if len(step_assets) > 0:
        #                                     logger.debug(f"Sample step asset structure: {step_assets[0]}")
        #                                 asset_filter = AssetFilter(task_def.input_filter)
        #                                 step_assets = asset_filter.filter_assets(step_assets)
        #                                 logger.info(f"After filtering step assets: {len(step_assets)} assets remaining")
        #                                 if len(step_assets) > 0:
        #                                     logger.debug(f"Sample filtered step asset: {step_assets[0]}")
        #                             except Exception as e:
        #                                 logger.error(f"Error applying input filter to step assets '{task_def.input_filter}': {str(e)}")
        #                                 logger.warning("Continuing without filter due to error")
        #                         elif task_def.input_filter and not step_assets:
        #                             logger.warning(f"Input filter specified but no step assets to filter: {task_def.input_filter}")
        #                         elif not task_def.input_filter:
        #                             logger.debug("No input filter specified for step assets")
                                
        #                         # Extract values based on asset type
        #                         if asset_type == "domain":
        #                             input_data.extend([asset["name"] for asset in step_assets])
        #                         elif asset_type == "string":
        #                             input_data.extend([asset["value"] for asset in step_assets])
        #                         elif asset_type == "ip":
        #                             input_data.extend([asset["ip"] for asset in step_assets])
        #                         elif asset_type == "url":
        #                             input_data.extend([asset["url"] for asset in step_assets])
        #                         elif asset_type == "service":
        #                             # For services, we typically want the IP:port combination
        #                             input_data.extend([f"{asset['ip']}:{asset['port']}" for asset in step_assets if 'ip' in asset and 'port' in asset])
        #                         elif asset_type == "certificate":
        #                             # For certificates, we typically want the domain
        #                             input_data.extend([asset["domain"] for asset in step_assets if "domain" in asset])
        #                         elif asset_type == "screenshot":
        #                             # For screenshots, we typically want the URL
        #                             input_data.extend([asset["url"] for asset in step_assets if "url" in asset])
        #                         elif asset_type == "nuclei":
        #                             # For nuclei findings, we typically want the URL
        #                             input_data.extend([asset["url"] for asset in step_assets if "url" in asset])
        #                         elif asset_type == "typosquat":
        #                             # For typosquat findings, we typically want the domain
        #                             input_data.extend([asset["domain"] for asset in step_assets if "domain" in asset])
        #                         continue
                            
        #                     if requested_asset_type:
        #                         logger.warning(f"No {requested_asset_type} assets found for source {source}")
        #                     else:
        #                         logger.warning(f"No valid assets found for source {source}")
        
        # Continue with the rest of the processing (same as sync version)
        if not input_data:
            logger.info("No inputs could be prepared from any of the specified sources")
            return None
        
        return await self._finalize_input_data_async(input_data, task, task_def)
    
    async def _resolve_program_asset_inputs_async(self, input_names: List[str], memory_config) -> List[str]:
        """Resolve program asset inputs asynchronously"""
        from task_components import AsyncDataApiClient
        all_input_data = []
        
        async with AsyncDataApiClient(API_URL, self.redis_client) as async_client:
            for input_name in input_names:
                if not self.workflow_context or not self.workflow_context.inputs:
                    logger.warning(f"No workflow context available for program asset input: {input_name}")
                    continue
                    
                input_def = self.workflow_context.inputs.get(input_name)
                if not input_def or input_def.type != 'program_asset':
                    logger.warning(f"Invalid program asset input definition: {input_name}")
                    continue
                    
                logger.info(f"Resolving program asset input: {input_name}")
                try:
                    # Get asset type from input definition
                    asset_type = input_def.asset_type
                    filter_type = None  # Could be extracted from value_type if needed

                    logger.info(f"Fetching {asset_type} assets for program {self.program_name}")
                    
                    # Check program stats first
                    stats_data = await async_client.get_program_stats(self.program_name)
                    if stats_data:
                        logger.info(f"Program asset stats: {stats_data}")
                        details_map = {
                            'apex-domain': 'apex_domain_details',
                            'subdomain': 'subdomain_details',
                            'ip': 'ip_details', 
                            'service': 'service_details',
                            'url': 'url_details'
                        }
                        details_key = details_map.get(asset_type)
                        if details_key and details_key in stats_data:
                            type_count = stats_data[details_key].get('total', 0)
                            if type_count == 0:
                                logger.warning(f"No {asset_type} assets found for program {self.program_name}")
                                continue
                    
                    # Fetch assets
                    all_assets = []
                    if stats_data:
                        details_key = details_map.get(asset_type)
                        total_count = stats_data.get(details_key, {}).get('total', 0) if details_key else 0
                        
                        if total_count > memory_config.streaming_asset_threshold:
                            logger.info(f"Using streaming approach for {total_count} {asset_type} assets")
                            all_assets = await self._fetch_assets_streaming(
                                async_client, asset_type, self.program_name, total_count, memory_config
                            )
                        else:
                            all_assets = await self._fetch_assets_standard(
                                async_client, asset_type, self.program_name, memory_config
                            )
                    else:
                        all_assets = await self._fetch_assets_standard(
                            async_client, asset_type, self.program_name, memory_config
                        )
                    
                    # Apply filter if specified in input definition
                    if input_def.filter and all_assets:
                        try:
                            logger.info(f"Applying input filter: {input_def.filter}")
                            asset_filter = AssetFilter(input_def.filter)
                            all_assets = asset_filter.filter_assets(all_assets)
                            logger.info(f"After filtering: {len(all_assets)} assets remaining")
                        except Exception as e:
                            logger.error(f"Error applying input filter '{input_def.filter}': {str(e)}")
                    
                    # Store the input limit for use in _finalize_input_data_async
                    if hasattr(input_def, 'limit') and input_def.limit:
                        self.input_limits[input_name] = input_def.limit
                        logger.info(f"Input limit {input_def.limit} stored for input '{input_name}', will be applied after threshold checking for progressive batching")
                    else:
                        # Clear any previous limit for this input
                        self.input_limits.pop(input_name, None)
                    
                    # Extract relevant data based on asset type and filter
                    if asset_type == "apex-domain":
                        all_input_data.extend([asset["name"] for asset in all_assets])
                    elif asset_type == "subdomain":
                        # Use getattr to safely access filter_type with fallback to None
                        filter_type = getattr(input_def, 'filter_type', None)
                        if filter_type == "resolved":
                            # Only subdomains that have an IP address
                            resolved_domains = [asset["name"] for asset in all_assets if asset.get("ip")]
                            all_input_data.extend(resolved_domains)
                        elif filter_type == "unresolved":
                            # Only subdomains that don't have an IP address
                            unresolved_domains = [asset["name"] for asset in all_assets if not asset.get("ip")]
                            all_input_data.extend(unresolved_domains)
                        else:
                            # No filter - include all subdomains
                            all_input_data.extend([asset["name"] for asset in all_assets])
                    elif asset_type == "ip":
                        # Use getattr to safely access filter_type with fallback to None
                        filter_type = getattr(input_def, 'filter_type', None)
                        if filter_type == "resolved":
                            # Only IPs that have a PTR record
                            resolved_ips = [asset["ip_address"] for asset in all_assets if asset.get("ptr")]
                            all_input_data.extend(resolved_ips)
                        elif filter_type == "unresolved":
                            # Only IPs that don't have a PTR record
                            unresolved_ips = [asset["ip_address"] for asset in all_assets if not asset.get("ptr")]
                            all_input_data.extend(unresolved_ips)
                        else:
                            # No filter - include all IPs
                            all_input_data.extend([asset["ip_address"] for asset in all_assets])
                    elif asset_type == "url":
                        filter_type = getattr(input_def, 'filter_type', None)
                        if filter_type == "root":
                            all_input_data.extend([asset["url"] for asset in all_assets if asset.get("path") == "/"])
                        else:
                            all_input_data.extend([asset["url"] for asset in all_assets])
                    elif asset_type == "cidr":
                        # Handle CIDR specially from program metadata
                        program_data = await async_client.get_program_metadata(self.program_name)
                        if program_data:
                            cidr_list = program_data.get("cidr_list", [])
                            all_input_data.extend(cidr_list)
                    else:
                        logger.warning(f"Unknown asset type for program input: {asset_type}")
                        
                except Exception as e:
                    logger.error(f"Error resolving program asset input {input_name}: {str(e)}")

        return all_input_data

    async def _resolve_program_finding_inputs_async(self, input_names: List[str], memory_config) -> List[str]:
        """Resolve program finding inputs asynchronously (e.g., typosquat URLs)"""
        from task_components import AsyncDataApiClient
        all_input_data = []

        async with AsyncDataApiClient(API_URL, self.redis_client) as async_client:
            for input_name in input_names:
                if not self.workflow_context or not self.workflow_context.inputs:
                    logger.warning(f"No workflow context available for program finding input: {input_name}")
                    continue

                input_def = self.workflow_context.inputs.get(input_name)
                if not input_def or input_def.type != 'program_finding':
                    logger.warning(f"Invalid program finding input definition: {input_name}")
                    continue

                logger.info(f"Resolving program finding input: {input_name}")
                try:
                    # Get finding type from input definition
                    # Backward compatibility: check asset_type if finding_type is not set
                    finding_type = getattr(input_def, 'finding_type', None)
                    if not finding_type and hasattr(input_def, 'asset_type'):
                        finding_type = input_def.asset_type
                        logger.info(f"Using asset_type as finding_type for backward compatibility: {finding_type}")

                    if not finding_type:
                        logger.error(f"No finding_type specified for input {input_name}")
                        continue

                    logger.info(f"Fetching {finding_type} findings for program {self.program_name}")

                    if finding_type == "typosquat_url":
                        # Fetch typosquat URLs
                        # First, get initial page to check total count
                        initial_response = await async_client.get_program_typosquat_urls(
                            self.program_name, page_size=1, page=1
                        )

                        pagination = initial_response.get("pagination", {})
                        total_count = pagination.get("total_items", 0)

                        if total_count == 0:
                            logger.warning(f"No typosquat URLs found for program {self.program_name}")
                            continue

                        logger.info(f"Found {total_count} typosquat URLs for program {self.program_name}")

                        # Fetch findings using appropriate method based on count
                        all_findings = []
                        if total_count > memory_config.streaming_asset_threshold:
                            logger.info(f"Using streaming approach for {total_count} typosquat URLs")
                            all_findings = await self._fetch_typosquat_urls_streaming(
                                async_client, self.program_name, total_count, memory_config
                            )
                        else:
                            all_findings = await self._fetch_typosquat_urls_standard(
                                async_client, self.program_name, memory_config
                            )

                        # Apply filter if specified in input definition
                        if input_def.filter and all_findings:
                            try:
                                logger.info(f"Applying input filter: {input_def.filter}")
                                asset_filter = AssetFilter(input_def.filter)
                                all_findings = asset_filter.filter_assets(all_findings)
                                logger.info(f"After filtering: {len(all_findings)} findings remaining")
                            except Exception as e:
                                logger.error(f"Error applying input filter '{input_def.filter}': {str(e)}")

                        # Store the input limit for use in _finalize_input_data_async
                        if hasattr(input_def, 'limit') and input_def.limit:
                            self.input_limits[input_name] = input_def.limit
                            logger.info(f"Input limit {input_def.limit} stored for input '{input_name}'")
                        else:
                            # Clear any previous limit for this input
                            self.input_limits.pop(input_name, None)

                        # Extract URLs from findings, applying filter_type if specified
                        filter_type = getattr(input_def, 'filter_type', None)
                        if filter_type == "root":
                            # Only root URLs (where path == "/")
                            root_urls = [finding.get("url") for finding in all_findings
                                        if finding.get("url") and finding.get("path") == "/"]
                            all_input_data.extend(root_urls)
                            logger.info(f"Filtered to {len(root_urls)} root typosquat URLs (path='/')")
                        else:
                            # All URLs
                            all_input_data.extend([finding.get("url") for finding in all_findings if finding.get("url")])
                    elif finding_type == "external_link":
                        # Fetch external links
                        # First, get initial page to check total count
                        initial_response = await async_client.get_program_external_links(
                            self.program_name, page_size=1, page=1
                        )

                        pagination = initial_response.get("pagination", {})
                        total_count = pagination.get("total_items", 0)

                        if total_count == 0:
                            logger.warning(f"No external links found for program {self.program_name}")
                            continue

                        logger.info(f"Found {total_count} external links for program {self.program_name}")

                        # Fetch findings using appropriate method based on count
                        all_findings = []
                        if total_count > memory_config.streaming_asset_threshold:
                            logger.info(f"Using streaming approach for {total_count} external links")
                            all_findings = await self._fetch_external_links_streaming(
                                async_client, self.program_name, total_count, memory_config
                            )
                        else:
                            all_findings = await self._fetch_external_links_standard(
                                async_client, self.program_name, memory_config
                            )

                        # Apply filter if specified in input definition
                        if input_def.filter and all_findings:
                            try:
                                logger.info(f"Applying input filter: {input_def.filter}")
                                asset_filter = AssetFilter(input_def.filter)
                                all_findings = asset_filter.filter_assets(all_findings)
                                logger.info(f"After filtering: {len(all_findings)} findings remaining")
                            except Exception as e:
                                logger.error(f"Error applying input filter '{input_def.filter}': {str(e)}")

                        # Store the input limit for use in _finalize_input_data_async
                        if hasattr(input_def, 'limit') and input_def.limit:
                            self.input_limits[input_name] = input_def.limit
                            logger.info(f"Input limit {input_def.limit} stored for input '{input_name}'")
                        else:
                            # Clear any previous limit for this input
                            self.input_limits.pop(input_name, None)

                        # Extract URLs from findings
                        all_input_data.extend([finding.get("url") for finding in all_findings if finding.get("url")])
                    elif finding_type == "typosquat_domain":
                        # Optional similarity filter (min % with protected domain)
                        typosquat_min_sim = getattr(input_def, 'min_similarity_percent', None)
                        typosquat_prot_domain = getattr(input_def, 'similarity_protected_domain', None)
                        # Fetch typosquat domains
                        # First, get initial page to check total count
                        initial_response = await async_client.get_program_typosquat_domains(
                            self.program_name, limit=1, skip=0,
                            min_similarity_percent=typosquat_min_sim,
                            similarity_protected_domain=typosquat_prot_domain
                        )

                        pagination = initial_response.get("pagination", {})
                        total_count = pagination.get("total_items", 0)

                        if total_count == 0:
                            logger.warning(f"No typosquat domains found for program {self.program_name}")
                            continue

                        logger.info(f"Found {total_count} typosquat domains for program {self.program_name}")

                        # Fetch findings using appropriate method based on count
                        all_findings = []
                        if total_count > memory_config.streaming_asset_threshold:
                            logger.info(f"Using streaming approach for {total_count} typosquat domains")
                            all_findings = await self._fetch_typosquat_domains_streaming(
                                async_client, self.program_name, total_count, memory_config,
                                min_similarity_percent=typosquat_min_sim,
                                similarity_protected_domain=typosquat_prot_domain
                            )
                        else:
                            all_findings = await self._fetch_typosquat_domains_standard(
                                async_client, self.program_name, memory_config,
                                min_similarity_percent=typosquat_min_sim,
                                similarity_protected_domain=typosquat_prot_domain
                            )

                        # Apply filter if specified in input definition
                        if input_def.filter and all_findings:
                            try:
                                logger.info(f"Applying input filter: {input_def.filter}")
                                asset_filter = AssetFilter(input_def.filter)
                                all_findings = asset_filter.filter_assets(all_findings)
                                logger.info(f"After filtering: {len(all_findings)} findings remaining")
                            except Exception as e:
                                logger.error(f"Error applying input filter '{input_def.filter}': {str(e)}")

                        # Store the input limit for use in _finalize_input_data_async
                        if hasattr(input_def, 'limit') and input_def.limit:
                            self.input_limits[input_name] = input_def.limit
                            logger.info(f"Input limit {input_def.limit} stored for input '{input_name}'")
                        else:
                            # Clear any previous limit for this input
                            self.input_limits.pop(input_name, None)

                        # Extract typo_domain from findings
                        all_input_data.extend([finding.get("typo_domain") for finding in all_findings if finding.get("typo_domain")])
                    elif finding_type == "typosquat_apex_domain":
                        # Optional similarity filter (min % with protected domain)
                        typosquat_min_sim = getattr(input_def, 'min_similarity_percent', None)
                        typosquat_prot_domain = getattr(input_def, 'similarity_protected_domain', None)
                        # Fetch typosquat domains and derive apex domains from their typo_domain field
                        # First, get initial page to check total count
                        initial_response = await async_client.get_program_typosquat_domains(
                            self.program_name, limit=1, skip=0,
                            min_similarity_percent=typosquat_min_sim,
                            similarity_protected_domain=typosquat_prot_domain
                        )

                        pagination = initial_response.get("pagination", {})
                        total_count = pagination.get("total_items", 0)

                        if total_count == 0:
                            logger.warning(f"No typosquat domains found for program {self.program_name} when deriving apex domains")
                            continue

                        logger.info(f"Found {total_count} typosquat domains for program {self.program_name} (for apex derivation)")

                        # Fetch findings using appropriate method based on count
                        all_findings = []
                        if total_count > memory_config.streaming_asset_threshold:
                            logger.info(f"Using streaming approach for {total_count} typosquat domains (apex derivation)")
                            all_findings = await self._fetch_typosquat_domains_streaming(
                                async_client, self.program_name, total_count, memory_config,
                                min_similarity_percent=typosquat_min_sim,
                                similarity_protected_domain=typosquat_prot_domain
                            )
                        else:
                            all_findings = await self._fetch_typosquat_domains_standard(
                                async_client, self.program_name, memory_config,
                                min_similarity_percent=typosquat_min_sim,
                                similarity_protected_domain=typosquat_prot_domain
                            )

                        # Apply filter if specified in input definition
                        if input_def.filter and all_findings:
                            try:
                                logger.info(f"Applying input filter: {input_def.filter}")
                                asset_filter = AssetFilter(input_def.filter)
                                all_findings = asset_filter.filter_assets(all_findings)
                                logger.info(f"After filtering: {len(all_findings)} findings remaining")
                            except Exception as e:
                                logger.error(f"Error applying input filter '{input_def.filter}': {str(e)}")

                        # Store the input limit for use in _finalize_input_data_async
                        if hasattr(input_def, 'limit') and input_def.limit:
                            self.input_limits[input_name] = input_def.limit
                            logger.info(f"Input limit {input_def.limit} stored for input '{input_name}'")
                        else:
                            # Clear any previous limit for this input
                            self.input_limits.pop(input_name, None)

                        # Derive unique apex domains from the typo_domain field
                        apex_set = set()
                        for finding in all_findings:
                            typo = finding.get("typo_domain")
                            if not typo:
                                continue
                            try:
                                apex = extract_apex_domain(typo)
                                apex_set.add(apex)
                            except Exception as e:
                                logger.debug(f"Failed to extract apex from typo_domain '{typo}': {e}")

                        derived_apex_domains = list(apex_set)
                        logger.info(f"Derived {len(derived_apex_domains)} unique apex domains from {len(all_findings)} typosquat domains")

                        all_input_data.extend(derived_apex_domains)
                    else:
                        logger.warning(f"Unknown finding type for program input: {finding_type}")

                except Exception as e:
                    logger.error(f"Error resolving program finding input {input_name}: {str(e)}")

        return all_input_data

    async def _resolve_program_protected_domains_inputs_async(self, input_names: List[str]) -> List[str]:
        """Resolve program protected domains inputs - fetches protected_domains list from program config"""
        from task_components import AsyncDataApiClient
        all_input_data = []

        async with AsyncDataApiClient(API_URL, self.redis_client) as async_client:
            for input_name in input_names:
                if not self.workflow_context or not self.workflow_context.inputs:
                    logger.warning(f"No workflow context available for program protected domains input: {input_name}")
                    continue

                input_def = self.workflow_context.inputs.get(input_name)
                if not input_def or input_def.type != 'program_protected_domains':
                    logger.warning(f"Invalid program protected domains input definition: {input_name}")
                    continue

                logger.info(f"Resolving program protected domains input: {input_name}")
                try:
                    program_data = await async_client.get_program_metadata(self.program_name)
                    protected_domains = program_data.get("protected_domains", []) or []
                    if isinstance(protected_domains, list):
                        all_input_data.extend(protected_domains)
                    logger.info(f"Fetched {len(protected_domains)} protected domains for program {self.program_name}")
                except Exception as e:
                    logger.error(f"Error resolving program protected domains input {input_name}: {str(e)}")

        return all_input_data

    async def _resolve_program_scope_domains_inputs_async(self, input_names: List[str]) -> List[str]:
        """Resolve program scope domains inputs - extracts apex domains from domain_regex patterns"""
        from task_components import AsyncDataApiClient
        all_input_data = []

        async with AsyncDataApiClient(API_URL, self.redis_client) as async_client:
            for input_name in input_names:
                if not self.workflow_context or not self.workflow_context.inputs:
                    logger.warning(f"No workflow context available for program scope domains input: {input_name}")
                    continue

                input_def = self.workflow_context.inputs.get(input_name)
                if not input_def or input_def.type != 'program_scope_domains':
                    logger.warning(f"Invalid program scope domains input definition: {input_name}")
                    continue

                logger.info(f"Resolving program scope domains input: {input_name}")
                try:
                    program_data = await async_client.get_program_metadata(self.program_name)
                    domain_regex = program_data.get("domain_regex", []) or []
                    if isinstance(domain_regex, list):
                        scope_domains = _extract_apex_domains_from_regex(domain_regex)
                        all_input_data.extend(scope_domains)
                        logger.info(f"Extracted {len(scope_domains)} scope domains from domain_regex for program {self.program_name}")
                except Exception as e:
                    logger.error(f"Error resolving program scope domains input {input_name}: {str(e)}")

        return all_input_data

    async def _finalize_input_data_async(self, input_data: List, task: Task, task_def: TaskDefinition) -> Optional[List[str]]:
        """Finalize input data processing with filtering and validation"""
        try:
            logger.debug(f"Input Data: {len(input_data)} items")
            # Clean and validate input data
            cleaned_inputs = []
            for item in input_data:
                if isinstance(item, str):
                    if item.startswith('[') and item.endswith(']'):
                        try:
                            parsed = json.loads(item)
                            if isinstance(parsed, list):
                                cleaned_inputs.extend(parsed)
                                continue
                        except json.JSONDecodeError:
                            pass
                    cleaned_inputs.extend([x.strip() for x in item.split() if x.strip()])
                else:
                    cleaned_inputs.append(item)
            
            input_data = cleaned_inputs
            logger.info(f"Cleaned input size for task {task_def.name}: {len(input_data)}")

            # Find input limit but don't apply it yet - we'll apply it after filtering
            input_limit = None
            if task_def.input_mapping:
                for input_key, mapping_path in task_def.input_mapping.items():
                    paths = [mapping_path] if isinstance(mapping_path, str) else mapping_path
                    for path in paths:
                        # Parse mapping path like "inputs.input_1"
                        path_parts = path.split('.')
                        if len(path_parts) >= 2 and path_parts[0] == 'inputs':
                            input_name = path_parts[1]
                            if input_name in self.input_limits:
                                found_limit = self.input_limits[input_name]
                                logger.info(f"Input limit {found_limit} stored for input '{input_name}', will be applied after execution time filtering")
                                # Use the first (or smallest) limit found
                                if input_limit is None or found_limit < input_limit:
                                    input_limit = found_limit

            # Check if we should use progressive batching based on original dataset size
            # We use progressive batching when we have a large dataset and want to process it in chunks
            should_use_progressive = (len(input_data) > 100)  # Use progressive for datasets > 100
            
            # Filter based on last execution
            if task_def.force:
                logger.info("Force flag is true, skipping last execution check")
                filtered_input_data = input_data

                # Apply input limit when force flag is used
                if input_limit and len(filtered_input_data) > input_limit:
                    filtered_input_data = filtered_input_data[:input_limit]
                    logger.info(f"Applied input limit {input_limit} with force flag, reduced to {len(filtered_input_data)} targets")
            else:
                logger.info(f"Force flag is false, checking last execution for {len(input_data)} targets")
                
                if should_use_progressive:
                    # For progressive batching, use the input_limit as the target batch size
                    # Default to 100 if no input_limit is defined
                    target_limit = input_limit if input_limit else 100

                    logger.info(f"Large dataset detected ({len(input_data)} assets), implementing progressive batching with target limit {target_limit}")
                    filtered_input_data = await self._process_assets_progressively(
                        input_data, task, task_def, target_limit
                    )
                else:
                    # Standard processing for small datasets
                    logger.info(f"Small dataset ({len(input_data)} assets), using standard processing")
                    filtered_input_data = await self._filter_assets_by_execution_time(
                        input_data, task, task_def
                    )

                    # Apply input limit after filtering for standard processing
                    if input_limit and filtered_input_data and len(filtered_input_data) > input_limit:
                        filtered_input_data = filtered_input_data[:input_limit]
                        logger.info(f"Applied input limit {input_limit} after filtering, reduced to {len(filtered_input_data)} targets")
                
                if filtered_input_data is None:
                    return None
            
            input_data = filtered_input_data
            logger.info(f"{len(input_data)} targets left after filtering recent executions")
            
            logger.info(f"Prepared {len(input_data)} total inputs")
            return input_data
            
        except Exception as e:
            logger.error(f"Error finalizing input data: {str(e)}")
            logger.exception(e)
            raise

    async def _process_assets_progressively(self, all_assets: List, task: Task, task_def: TaskDefinition, batch_size: int) -> Optional[List[str]]:
        """Process assets progressively in batches, accumulating until input_limit is reached"""
        # Ensure batch_size is valid
        if batch_size is None or batch_size <= 0:
            batch_size = 100  # Default batch size
            logger.warning(f"Invalid batch_size provided, using default: {batch_size}")

        total_assets = len(all_assets)
        processed_count = 0
        current_batch_start = 0
        accumulated_assets = []  # Accumulate filtered assets across batches

        logger.info(f"Starting progressive processing of {total_assets} assets in batches of {batch_size}, target limit: {batch_size}")

        while current_batch_start < total_assets and len(accumulated_assets) < batch_size:
            current_batch_end = min(current_batch_start + batch_size, total_assets)
            current_batch = all_assets[current_batch_start:current_batch_end]
            batch_num = (current_batch_start // batch_size) + 1
            total_batches = (total_assets - 1) // batch_size + 1

            logger.info(f"Processing batch {batch_num}/{total_batches}: assets {current_batch_start + 1}-{current_batch_end} of {total_assets}")

            # Filter current batch by execution time
            filtered_batch = await self._filter_assets_by_execution_time(current_batch, task, task_def)

            if filtered_batch is None:
                # All assets in this batch were tested within threshold
                logger.info(f"Batch {batch_num}: All {len(current_batch)} assets tested within threshold, moving to next batch")
            else:
                # Found untested assets in this batch
                logger.info(f"Batch {batch_num}: Found {len(filtered_batch)} untested assets out of {len(current_batch)} total")

                # Add filtered assets to our accumulator
                remaining_needed = batch_size - len(accumulated_assets)
                assets_to_add = filtered_batch[:remaining_needed]
                accumulated_assets.extend(assets_to_add)

                logger.info(f"Added {len(assets_to_add)} assets, total accumulated: {len(accumulated_assets)}/{batch_size}")

                # If we've reached our target limit, return the accumulated assets
                if len(accumulated_assets) >= batch_size:
                    logger.info(f"Reached input limit of {batch_size} assets, returning accumulated results")
                    return accumulated_assets[:batch_size]

            # Move to next batch
            current_batch_start = current_batch_end
            processed_count += len(current_batch)

        # If we get here, either we've processed all assets or found some but not enough to meet the limit
        if len(accumulated_assets) > 0:
            logger.info(f"Progressive processing complete: Found {len(accumulated_assets)} untested assets out of {total_assets} total (less than target limit of {batch_size})")
            return accumulated_assets
        else:
            logger.info(f"Progressive processing complete: All {total_assets} assets were tested within threshold")
            return None

    async def _filter_assets_by_execution_time(self, input_data: List, task: Task, task_def: TaskDefinition) -> Optional[List[str]]:
        """Filter assets based on last execution time (standard implementation)"""
        from task_components import MemoryOptimizationConfig
        from datetime import datetime, timedelta
        
        filtered_input_data = []
        
        # Batch Redis operations for performance
        target_hashes = []
        target_to_hash = {}
        
        # Collect all timestamp hashes
        for target in input_data:
            timestamp_hash = task.get_timestamp_hash(target, task_def.params or {})
            if timestamp_hash:
                target_hashes.append(timestamp_hash)
                target_to_hash[target] = timestamp_hash
        
        # Batch fetch all timestamps at once (in chunks for very large lists)
        if target_hashes:
            hash_to_execution_time = {}
            memory_config = MemoryOptimizationConfig.from_environment()
            batch_size = memory_config.redis_batch_size    
            
            try:
                # Process hashes in batches to avoid Redis pipeline limits
                for i in range(0, len(target_hashes), batch_size):
                    batch_hashes = target_hashes[i:i + batch_size]
                    batch_num = i // batch_size + 1
                    total_batches = (len(target_hashes) - 1) // batch_size + 1
                                        
                    # Use Redis pipeline for batch operations
                    pipe = self.redis_client.pipeline()
                    for hash_key in batch_hashes:
                        pipe.get(hash_key)
                    batch_execution_times = pipe.execute()
                    
                    # Add batch results to lookup dictionary
                    for j, execution_time in enumerate(batch_execution_times):
                        if execution_time:
                            hash_to_execution_time[batch_hashes[j]] = execution_time
                
                logger.info(f"Found {len(hash_to_execution_time)} cached execution times from {total_batches} Redis batches")
                
            except Exception as e:
                logger.warning(f"Error in batch Redis fetch: {e}, falling back to individual checks")
                hash_to_execution_time = {}
                for target in input_data:
                    timestamp_hash = target_to_hash.get(target)
                    if timestamp_hash:
                        try:
                            execution_time = self.redis_client.get(timestamp_hash)
                            if execution_time:
                                hash_to_execution_time[timestamp_hash] = execution_time
                        except Exception as e2:
                            logger.debug(f"Error fetching individual hash {timestamp_hash}: {e2}")
        else:
            hash_to_execution_time = {}
        
        # Filter targets based on fetched execution times
        threshold_hours = self._resolved_last_execution_threshold_hours(task, task_def)
        current_time = datetime.now()
        skipped_targets = []
        for target in input_data:
            timestamp_hash = target_to_hash.get(target)
            if not timestamp_hash:
                filtered_input_data.append(target)
                continue
            
            last_execution = hash_to_execution_time.get(timestamp_hash)
            if last_execution:
                try:
                    
                    # Decode bytes to string before converting to float
                    last_execution_str = last_execution.decode('utf-8') if isinstance(last_execution, bytes) else str(last_execution)
                    last_execution_time = datetime.fromtimestamp(float(last_execution_str))
                    time_since_last = current_time - last_execution_time
                    
                    if time_since_last < timedelta(hours=threshold_hours):
                        skipped_targets.append(target)
                        continue
                except (ValueError, OSError) as e:
                    logger.warning(f"Invalid timestamp for {target}: {e}, including target")
            
            filtered_input_data.append(target)
        
        logger.debug(f"Skipped {len(skipped_targets)} target that were last executed within the last {threshold_hours} hours")
        
        if len(filtered_input_data) == 0:
            logger.info(f"All targets were executed within the last {threshold_hours} hours, skipping task")
            return None
        
        logger.info(f"{len(filtered_input_data)} targets left after filtering recent executions")
        return filtered_input_data
    
    async def _fetch_assets_streaming(self, async_client, asset_type: str, program_name: str, 
                                     total_count: int, config) -> List[Any]:
        """Fetch assets using streaming approach for large datasets"""
        all_assets = []
        page = 1
        page_size = config.streaming_page_size
        processed_count = 0
        
        while processed_count < total_count:
            logger.debug(f"Fetching page {page} of {asset_type} assets ({processed_count}/{total_count} processed)")
            response_data = await async_client.get_program_assets(
                asset_type, program_name, page_size, (page - 1) * page_size
            )
            
            page_assets = response_data.get("items", [])
            if not page_assets:
                break
            
            # Process assets in smaller chunks to control memory
            chunk_size = 500
            for i in range(0, len(page_assets), chunk_size):
                chunk = page_assets[i:i + chunk_size]
                all_assets.extend(chunk)
                
                # Force garbage collection for very large datasets
                if processed_count % 10000 == 0 and processed_count > 0:
                    import gc
                    gc.collect()
            
            processed_count += len(page_assets)
            page += 1
            
            # Safety check to avoid infinite loops
            if page > config.max_pages:
                logger.warning(f"Reached maximum page limit for {asset_type} assets")
                break
        
        logger.info(f"Streaming fetch completed: {len(all_assets)} {asset_type} assets")
        return all_assets
    
    async def _fetch_assets_standard(self, async_client, asset_type: str, program_name: str, config) -> List[Any]:
        """Standard asset fetching for smaller datasets"""
        all_assets = []
        page = 1
        page_size = config.standard_page_size
        
        while True:
            logger.debug(f"Fetching page {page} of {asset_type} assets for {program_name}")
            response_data = await async_client.get_program_assets(
                asset_type, program_name, page_size, (page - 1) * page_size
            )
            
            page_assets = response_data.get("items", [])
            all_assets.extend(page_assets)
            
            pagination = response_data.get("pagination", {})
            total_pages = pagination.get("total_pages", 0)
            current_page = pagination.get("current_page", 0)
            
            logger.debug(f"Retrieved {len(page_assets)} assets from page {current_page}/{total_pages}")
            
            if not page_assets or current_page >= total_pages:
                break
            page += 1
        
        logger.info(f"Retrieved a total of {len(all_assets)} {asset_type} assets for {program_name}")
        return all_assets

    async def _fetch_typosquat_urls_streaming(self, async_client, program_name: str,
                                              total_count: int, config) -> List[Any]:
        """Fetch typosquat URLs using streaming approach for large datasets"""
        all_findings = []
        page = 1
        page_size = config.streaming_page_size
        processed_count = 0

        while processed_count < total_count:
            logger.debug(f"Fetching page {page} of typosquat URLs ({processed_count}/{total_count} processed)")
            response_data = await async_client.get_program_typosquat_urls(
                program_name, page_size, page
            )

            page_findings = response_data.get("items", [])
            if not page_findings:
                break

            # Process findings in smaller chunks to control memory
            chunk_size = 500
            for i in range(0, len(page_findings), chunk_size):
                chunk = page_findings[i:i + chunk_size]
                all_findings.extend(chunk)

                # Force garbage collection for very large datasets
                if processed_count % 10000 == 0 and processed_count > 0:
                    import gc
                    gc.collect()

            processed_count += len(page_findings)
            page += 1

            # Check pagination info to see if we're done
            pagination = response_data.get("pagination", {})
            if processed_count >= pagination.get("total_items", 0):
                break

        logger.info(f"Retrieved {len(all_findings)} typosquat URLs using streaming approach")
        return all_findings

    async def _fetch_typosquat_urls_standard(self, async_client, program_name: str, config) -> List[Any]:
        """Standard typosquat URL fetching for smaller datasets"""
        all_findings = []
        page = 1
        page_size = config.standard_page_size

        while True:
            logger.debug(f"Fetching page {page} of typosquat URLs for {program_name}")
            response_data = await async_client.get_program_typosquat_urls(
                program_name, page_size, page
            )

            page_findings = response_data.get("items", [])
            all_findings.extend(page_findings)

            pagination = response_data.get("pagination", {})
            total_pages = pagination.get("total_pages", 0)
            current_page = pagination.get("current_page", 0)

            logger.debug(f"Retrieved {len(page_findings)} typosquat URLs from page {current_page}/{total_pages}")

            if not page_findings or current_page >= total_pages:
                break
            page += 1

        logger.info(f"Retrieved a total of {len(all_findings)} typosquat URLs for {program_name}")
        return all_findings

    async def _fetch_typosquat_domains_streaming(self, async_client, program_name: str,
                                                 total_count: int, config,
                                                 min_similarity_percent=None,
                                                 similarity_protected_domain=None) -> List[Any]:
        """Fetch typosquat domains using streaming approach for large datasets"""
        all_findings = []
        page = 1
        page_size = config.streaming_page_size
        processed_count = 0
        extra_params = {}
        if min_similarity_percent is not None:
            extra_params['min_similarity_percent'] = min_similarity_percent
        if similarity_protected_domain is not None:
            extra_params['similarity_protected_domain'] = similarity_protected_domain

        while processed_count < total_count:
            logger.debug(f"Fetching page {page} of typosquat domains ({processed_count}/{total_count} processed)")
            response_data = await async_client.get_program_typosquat_domains(
                program_name, limit=page_size, skip=(page - 1) * page_size,
                **extra_params
            )

            page_findings = response_data.get("items", [])
            if not page_findings:
                break

            # Process findings in smaller chunks to control memory
            chunk_size = 500
            for i in range(0, len(page_findings), chunk_size):
                chunk = page_findings[i:i + chunk_size]
                all_findings.extend(chunk)

                # Force garbage collection for very large datasets
                if processed_count % 10000 == 0 and processed_count > 0:
                    import gc
                    gc.collect()

            processed_count += len(page_findings)
            page += 1

            # Check pagination info to see if we're done
            pagination = response_data.get("pagination", {})
            if processed_count >= pagination.get("total_items", 0):
                break

        logger.info(f"Retrieved {len(all_findings)} typosquat domains using streaming approach")
        return all_findings

    async def _fetch_typosquat_domains_standard(self, async_client, program_name: str, config,
                                                 min_similarity_percent=None,
                                                 similarity_protected_domain=None) -> List[Any]:
        """Standard typosquat domain fetching for smaller datasets"""
        all_findings = []
        page = 1
        page_size = config.standard_page_size
        extra_params = {}
        if min_similarity_percent is not None:
            extra_params['min_similarity_percent'] = min_similarity_percent
        if similarity_protected_domain is not None:
            extra_params['similarity_protected_domain'] = similarity_protected_domain

        while True:
            logger.debug(f"Fetching page {page} of typosquat domains for {program_name}")
            response_data = await async_client.get_program_typosquat_domains(
                program_name, limit=page_size, skip=(page - 1) * page_size,
                **extra_params
            )

            page_findings = response_data.get("items", [])
            all_findings.extend(page_findings)

            pagination = response_data.get("pagination", {})
            total_pages = pagination.get("total_pages", 0)
            current_page = pagination.get("current_page", 0)

            logger.debug(f"Retrieved {len(page_findings)} typosquat domains from page {current_page}/{total_pages}")

            if not page_findings or current_page >= total_pages:
                break
            page += 1

        logger.info(f"Retrieved a total of {len(all_findings)} typosquat domains for {program_name}")
        return all_findings

    async def _fetch_external_links_streaming(self, async_client, program_name: str,
                                              total_count: int, config) -> List[Any]:
        """Fetch external links using streaming approach for large datasets"""
        all_findings = []
        page = 1
        page_size = config.streaming_page_size
        processed_count = 0

        while processed_count < total_count:
            logger.debug(f"Fetching page {page} of external links ({processed_count}/{total_count} processed)")
            response_data = await async_client.get_program_external_links(
                program_name, page_size, page
            )

            page_findings = response_data.get("items", [])
            if not page_findings:
                break

            # Process findings in smaller chunks to control memory
            chunk_size = 500
            for i in range(0, len(page_findings), chunk_size):
                chunk = page_findings[i:i + chunk_size]
                all_findings.extend(chunk)

                # Force garbage collection for very large datasets
                if processed_count % 10000 == 0 and processed_count > 0:
                    import gc
                    gc.collect()

            processed_count += len(page_findings)
            page += 1

            # Check pagination info to see if we're done
            pagination = response_data.get("pagination", {})
            if processed_count >= pagination.get("total_items", 0):
                break

        logger.info(f"Retrieved {len(all_findings)} external links using streaming approach")
        return all_findings

    async def _fetch_external_links_standard(self, async_client, program_name: str, config) -> List[Any]:
        """Standard external links fetching for smaller datasets"""
        all_findings = []
        page = 1
        page_size = config.standard_page_size

        while True:
            logger.debug(f"Fetching page {page} of external links for {program_name}")
            response_data = await async_client.get_program_external_links(
                program_name, page_size, page
            )

            page_findings = response_data.get("items", [])
            all_findings.extend(page_findings)

            pagination = response_data.get("pagination", {})
            total_pages = pagination.get("total_pages", 0)
            current_page = pagination.get("current_page", 0)

            logger.debug(f"Retrieved {len(page_findings)} external links from page {current_page}/{total_pages}")

            if not page_findings or current_page >= total_pages:
                break
            page += 1

        logger.info(f"Retrieved a total of {len(all_findings)} external links for {program_name}")
        return all_findings

    def get_available_tasks(self) -> List[str]:
        """Get a list of all available task names"""
        return self.task_registry.list_tasks()

    def get_task(self, task_name: str) -> Optional[Task]:
        """Get a task instance by name"""
        task_class = self.task_registry.get_task(task_name)
        if task_class:
            return task_class()
        return None
    
    def _send_typosquat_urls_and_screenshots_after_domains(self, step_name: str, program_name: str, execution_id: str, typosquat_urls: List[Dict[str, Any]], typosquat_screenshots: List[Dict[str, Any]] = None) -> bool:
        """Send typosquat URLs and screenshots to the API after typosquat domains have been sent"""
        try:
            success = True
            
            # Send typosquat URLs first
            if typosquat_urls:
                logger.info(f"Sending {len(typosquat_urls)} typosquat URLs after domains for step {step_name}")
                
                # Send each URL individually to the typosquat-url endpoint
                success_count = 0
                for url_data in typosquat_urls:
                    try:
                        # Ensure the URL data has the required typosquat domain information
                        if not url_data.get('typosquat_domain') and not url_data.get('typosquat_domain_id'):
                            # Try to extract domain from hostname if available
                            hostname = url_data.get('hostname')
                            if hostname:
                                url_data['typosquat_domain'] = hostname
                                logger.debug(f"Using hostname '{hostname}' as typosquat_domain for URL {url_data.get('url', 'unknown')}")
                            else:
                                logger.warning(f"URL {url_data.get('url', 'unknown')} has no typosquat domain information, skipping")
                                continue
                        
                        # Ensure program_name is set
                        if not url_data.get('program_name'):
                            url_data['program_name'] = program_name
                        
                        # Clean API metadata
                        url_data.pop('_id', None)
                        url_data.pop('created_at', None)
                        url_data.pop('updated_at', None)
                        
                        # Send directly to the typosquat-url endpoint
                        if hasattr(self.data_api_client, 'store_typosquat_url'):
                            # Use the specialized method if available
                            success = self.data_api_client.store_typosquat_url(url_data)
                        else:
                            # Fallback: send directly to the endpoint
                            import requests
                            headers = {"Content-Type": "application/json"}
                            if hasattr(self.data_api_client, 'internal_api_key') and self.data_api_client.internal_api_key:
                                headers['Authorization'] = f'Bearer {self.data_api_client.internal_api_key}'
                            
                            response = requests.post(
                                f"{self.data_api_client.base_url}/findings/typosquat-url",
                                json=url_data,
                                headers=headers,
                                timeout=30
                            )
                            success = response.status_code == 200
                        
                        if success:
                            success_count += 1
                            logger.debug(f"Successfully sent typosquat URL: {url_data.get('url', 'unknown')}")
                        else:
                            logger.warning(f"Failed to send typosquat URL {url_data.get('url', 'unknown')}")
                            
                    except Exception as e:
                        logger.error(f"Error sending typosquat URL {url_data.get('url', 'unknown')}: {e}")
                
                logger.info(f"Sent {success_count}/{len(typosquat_urls)} typosquat URLs successfully")
                success = success and (success_count == len(typosquat_urls))
            
            # Send typosquat screenshots after URLs
            if typosquat_screenshots:
                logger.info(f"Sending {len(typosquat_screenshots)} typosquat screenshots after URLs for step {step_name}")
                screenshot_success_count = 0
                for screenshot_data in typosquat_screenshots:
                    try:
                        # Check if we have base64-encoded image data or file path
                        if "screenshot_data" in screenshot_data and screenshot_data["screenshot_data"]:
                            # New format: base64-encoded image data
                            image_data = base64.b64decode(screenshot_data["screenshot_data"]["image_data"])
                            filename = screenshot_data["screenshot_data"]["filename"]
                            content_type = "image/png"
                            
                            logger.debug(f"Processing base64 screenshot for {screenshot_data.get('url', 'unknown')} ({len(image_data)} bytes)")
                            
                        elif "screenshot_path" in screenshot_data and screenshot_data["screenshot_path"]:
                            # Legacy format: file path (fallback)
                            screenshot_path = screenshot_data["screenshot_path"]
                            if not os.path.exists(screenshot_path):
                                logger.warning(f"Screenshot file not found: {screenshot_path}")
                                continue
                            
                            with open(screenshot_path, 'rb') as f:
                                image_data = f.read()
                            filename = os.path.basename(screenshot_path)
                            content_type = "image/png"
                            
                            logger.debug(f"Processing file screenshot for {screenshot_data.get('url', 'unknown')} ({len(image_data)} bytes)")
                        else:
                            logger.warning(f"No screenshot data found for {screenshot_data.get('url', 'unknown')}")
                            continue
                        
                        # Prepare form data and send to /findings/typosquat-screenshot
                        response = requests.post(
                            f"{self.data_api_client.base_url}/findings/typosquat-screenshot",
                            files={'file': (filename, image_data, content_type)},
                            data={
                                'url': screenshot_data.get('url', ''),
                                'program_name': screenshot_data.get('program_name', program_name),
                                'workflow_id': screenshot_data.get('workflow_id', ''),
                                'step_name': screenshot_data.get('step_name', step_name)
                            }
                        )
                        
                        if response.status_code == 200:
                            try:
                                result = response.json()
                                file_id = result.get('file_id', 'unknown')
                                logger.info(f"Successfully uploaded typosquat screenshot for {screenshot_data.get('url', 'unknown')} (file_id: {file_id})")
                                screenshot_success_count += 1
                            except Exception as e:
                                logger.warning(f"Screenshot uploaded but failed to parse response: {e}")
                                screenshot_success_count += 1
                        else:
                            logger.error(f"Failed to upload typosquat screenshot for {screenshot_data.get('url', 'unknown')}: {response.status_code} - {response.text}")
                            
                    except Exception as e:
                        logger.error(f"Error uploading typosquat screenshot for {screenshot_data.get('url', 'unknown')}: {e}")
                
                logger.info(f"Sent {screenshot_success_count}/{len(typosquat_screenshots)} typosquat screenshots successfully")
                success = success and (screenshot_success_count == len(typosquat_screenshots))
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending typosquat URLs and screenshots after domains: {e}")
            return False

    def _process_screenshot_task_results(self, task_id: str, output: str) -> bool:
        """Process results from spawned screenshot tasks and send to typosquat-screenshot endpoint"""
        try:
            if not hasattr(self, 'spawned_screenshot_tasks') or task_id not in self.spawned_screenshot_tasks:
                logger.warning(f"Screenshot task {task_id} not found in spawned tasks")
                return False
            
            task_info = self.spawned_screenshot_tasks[task_id]
            url = task_info.get('url', '')
            program_name = task_info.get('program_name', '')
            workflow_id = task_info.get('workflow_id', '')
            step_name = task_info.get('step_name', '')
            
            logger.info(f"📸 Processing screenshot results for task {task_id} (URL: {url})")
            logger.info(f"📸 Output length: {len(output) if output else 0}")
            logger.info(f"📸 Output preview: {str(output)[:200] if output else 'None'}...")
            
            # Check if output is empty or just whitespace
            if not output or not output.strip():
                logger.warning(f"⚠️ Empty output received from screenshot task for {url}")
                logger.warning("⚠️ This suggests the screenshotter.sh script didn't produce any output")
                logger.warning("⚠️ The screenshot task completed but no screenshots were generated")
                # Don't fail the task - just log the issue
                return True
            
            # Parse the screenshot output using the screenshot_website task
            try:
                from tasks.screenshot_website import ScreenshotWebsite
                screenshot_task = ScreenshotWebsite()
                parsed_output = screenshot_task.parse_output(output)
                
                if AssetType.SCREENSHOT in parsed_output and parsed_output[AssetType.SCREENSHOT]:
                    screenshots = parsed_output[AssetType.SCREENSHOT]
                    logger.info(f"📸 Found {len(screenshots)} screenshots in output for {url}")
                    
                    # Process the screenshots as regular screenshots
                    success = self._process_regular_screenshots(
                        screenshots, program_name, workflow_id, step_name
                    )

                    if success:
                        logger.info(f"✅ Successfully processed {len(screenshots)} regular screenshots for {url}")
                        # Remove the task from tracking after successful processing
                        del self.spawned_screenshot_tasks[task_id]
                        return True
                    else:
                        logger.warning(f"⚠️ Failed to process some regular screenshots for {url}")
                        return False
                else:
                    logger.warning(f"⚠️ No screenshots found in output for {url}")
                    logger.warning(f"⚠️ Parsed output keys: {list(parsed_output.keys()) if parsed_output else 'None'}")
                    # Don't fail the task - just log the issue
                    return True
                    
            except Exception as e:
                logger.error(f"Error parsing screenshot output for {url}: {e}")
                logger.error(f"Raw output: {output[:500] if output else 'None'}...")
                # Don't fail the task - just log the issue
                return True
                
        except Exception as e:
            logger.error(f"Error processing screenshot task results: {e}")
            return False

    def _process_regular_screenshots(self, screenshots: List[Dict[str, Any]], program_name: str, workflow_id: str, step_name: str) -> bool:
        """Process regular screenshots and send them to the /assets/screenshot endpoint"""
        try:
            success = True

            for screenshot in screenshots:
                try:
                    # Extract image data from base64
                    image_data = base64.b64decode(screenshot.get("image_data", ""))
                    url = screenshot.get("url", "")
                    filename = screenshot.get("filename", "")

                    if not image_data or not url:
                        logger.warning(f"Missing image data or URL for regular screenshot: {screenshot}")
                        continue

                    # Send to regular screenshot endpoint using data API client
                    if self.data_api_client:
                        # Prepare screenshot asset for the data API client
                        screenshot_asset = {
                            "url": url,
                            "image_data": screenshot.get("image_data", ""),
                            "filename": filename
                        }

                        # Use the data API client's screenshot method
                        success = self.data_api_client._send_screenshot_assets(
                            [screenshot_asset], program_name, workflow_id, step_name
                        ) and success

                        if success:
                            logger.info(f"📸 Successfully uploaded regular screenshot for {url}")
                        else:
                            logger.error(f"📸 Failed to upload regular screenshot for {url}")
                    else:
                        logger.error("No data API client available for screenshot upload")

                except Exception as e:
                    logger.error(f"Error processing regular screenshot for {screenshot.get('url', 'unknown')}: {e}")
                    success = False

            return success

        except Exception as e:
            logger.error(f"Error processing regular screenshots: {e}")
            return False
    
    async def _wait_for_screenshot_tasks_completion(self, timeout: int = 1800) -> bool:
        """Wait for all spawned screenshot tasks to complete and process their results"""
        if not hasattr(self, 'spawned_screenshot_tasks') or not self.spawned_screenshot_tasks:
            logger.info("No screenshot tasks to wait for")
            return True
        
        logger.info(f"📸 Waiting for {len(self.spawned_screenshot_tasks)} screenshot tasks to complete")
        
        try:
            from services.kubernetes import KubernetesService
            k8s_service = KubernetesService()
            
            # Get job names from task IDs
            job_names = []
            for task_id, task_info in self.spawned_screenshot_tasks.items():
                job_name = task_info.get('job_name', f'worker-{task_id}')
                job_names.append(job_name)
            
            logger.info(f"📸 Waiting for screenshot jobs: {job_names}")
            
            # Wait for all jobs to complete
            job_statuses = await k8s_service.wait_for_jobs_completion(
                job_names, 
                timeout=timeout,
                check_interval=30
            )
            
            # Log completion status
            succeeded = sum(1 for status in job_statuses.values() if status == 'succeeded')
            failed = sum(1 for status in job_statuses.values() if status == 'failed')
            logger.info(f"📸 Screenshot jobs completed: {succeeded} succeeded, {failed} failed")
            
            # Now collect outputs from completed jobs and process them
            if succeeded > 0:
                logger.info("📸 Collecting outputs from completed screenshot jobs")
                
                for task_id, task_info in list(self.spawned_screenshot_tasks.items()):
                    job_name = task_info.get('job_name', f'worker-{task_id}')
                    job_status = job_statuses.get(job_name, 'unknown')
                    
                    if job_status == 'succeeded':
                        try:
                            # PRIORITY 1: Try to get output from NATS first (clean output)
                            # Since we fixed command_wrapper.py, NATS should have clean data
                            if hasattr(self, 'task_queue_client') and self.task_queue_client:
                                try:
                                    logger.info(f"📸 Trying to get output from NATS for screenshot task {task_id}")
                                    output = await self.task_queue_client.get_task_output(task_id)
                                    if output and output.strip():
                                        logger.info(f"📸 Successfully got clean output from NATS for task {task_id}")
                                        logger.info(f"📸 NATS output length: {len(output)}")
                                        logger.info(f"📸 NATS output preview: {output[:200]}...")
                                        
                                        success = self._process_screenshot_task_results(task_id, output)
                                        if success:
                                            logger.info(f"✅ Successfully processed screenshot task {task_id}")
                                            # Remove the task from tracking after successful processing
                                            del self.spawned_screenshot_tasks[task_id]
                                        else:
                                            logger.warning(f"⚠️ Failed to process screenshot task {task_id}")
                                    else:
                                        logger.warning(f"⚠️ No output received from NATS for screenshot task {task_id}")
                                        # Fall back to pod logs
                                        output = None
                                except Exception as nats_error:
                                    logger.error(f"Error getting output from NATS for task {task_id}: {nats_error}")
                                    output = None
                            else:
                                logger.warning(f"⚠️ No task queue client available for task {task_id}")
                                output = None
                            
                            # PRIORITY 2: Fall back to pod logs if NATS failed
                            if not output:
                                logger.info(f"📸 Falling back to pod logs for task {task_id}")
                                
                                # Get the job output by finding the pod directly using the job name
                                # Since get_pod_logs expects specific labels that don't match our screenshot jobs,
                                # we'll find the pod by job name and get logs directly
                                try:
                                    # List pods with the job name as a label selector
                                    pods = k8s_service.core_api.list_namespaced_pod(
                                        namespace=k8s_service.environment,
                                        label_selector=f"job-name={job_name}"
                                    ).items
                                    
                                    if pods:
                                        # Get the most recent pod
                                        pods.sort(key=lambda x: x.metadata.creation_timestamp, reverse=True)
                                        pod = pods[0]
                                        
                                        # Get logs from the pod
                                        output = k8s_service.core_api.read_namespaced_pod_log(
                                            name=pod.metadata.name,
                                            namespace=k8s_service.environment
                                        )
                                        
                                        if output and output.strip():
                                            logger.info(f"📸 Processing output from screenshot task {task_id} (pod logs)")
                                            logger.info(f"📸 Pod output length: {len(output)}")
                                            logger.info(f"📸 Pod output preview: {output[:200]}...")
                                            
                                            success = self._process_screenshot_task_results(task_id, output)
                                            if success:
                                                logger.info(f"✅ Successfully processed screenshot task {task_id}")
                                                # Remove the task from tracking after successful processing
                                                del self.spawned_screenshot_tasks[task_id]
                                            else:
                                                logger.warning(f"⚠️ Failed to process screenshot task {task_id}")
                                        else:
                                            logger.warning(f"⚠️ No output received from screenshot task {task_id}")
                                    else:
                                        logger.warning(f"⚠️ No pods found for job {job_name}")
                                except Exception as pod_error:
                                    logger.error(f"Error getting pod logs for job {job_name}: {pod_error}")
                                    # Final fallback to get_pod_logs method
                                    if job_name.startswith('worker-'):
                                        task_id_from_job = job_name.replace('worker-', '')
                                        output = k8s_service.get_pod_logs("worker", task_id_from_job)
                                        if output and output != "No logs available for this workflow":
                                            logger.info(f"📸 Processing output from screenshot task {task_id} (final fallback)")
                                            success = self._process_screenshot_task_results(task_id, output)
                                            if success:
                                                logger.info(f"✅ Successfully processed screenshot task {task_id}")
                                                del self.spawned_screenshot_tasks[task_id]
                                            else:
                                                logger.warning(f"⚠️ Failed to process screenshot task {task_id}")
                                        else:
                                            logger.warning(f"⚠️ No output received from screenshot task {task_id} (final fallback)")
                                    else:
                                        logger.warning(f"⚠️ Unexpected job name format for screenshot task: {job_name}")
                        except Exception as e:
                            logger.error(f"Error processing output from screenshot task {task_id}: {e}")
                    elif job_status == 'failed':
                        logger.warning(f"⚠️ Screenshot job {job_name} failed")
                        # Remove failed tasks from tracking
                        del self.spawned_screenshot_tasks[task_id]
            
            return failed == 0
            
        except Exception as e:
            logger.error(f"Error waiting for screenshot tasks completion: {e}")
            return False
    
    async def _update_timestamps_for_successful_tasks(self, task_results: List, task_instance: Task, task_def: TaskDefinition, input_data: List[str]):
        """Update last execution timestamps for successful task executions only"""
        try:            
            # Count successful tasks
            successful_count = sum(1 for result in task_results if hasattr(result, 'success') and result.success)
            total_count = len(task_results)
            
            if successful_count == 0:
                logger.info(f"No successful tasks to update timestamps for (0/{total_count} succeeded)")
                return
            
            # If all tasks succeeded, update timestamps for all input targets
            if successful_count == total_count and total_count > 0:
                logger.info(f"All tasks succeeded ({successful_count}/{total_count}), updating timestamps for all targets")
                current_time = datetime.now().timestamp()
                task_params = task_def.params or {}
                
                updated_count = 0
                for target in input_data:
                    timestamp_hash = task_instance.get_timestamp_hash(target, task_params)
                    if timestamp_hash:
                        try:
                            self.redis_client.set(timestamp_hash, str(current_time))
                            #logger.debug(f"Updated last execution timestamp for target {target}")
                            updated_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to update timestamp for target {target}: {e}")
                
                logger.info(f"Updated timestamps for {updated_count}/{len(input_data)} targets")
            else:
                # Partial success - we can't easily map which specific targets succeeded
                # since tasks are chunked. Log this case for future enhancement.
                logger.info(f"Partial task success ({successful_count}/{total_count}), skipping timestamp updates")
                logger.info("Consider implementing per-target success tracking for more precise timestamp updates")
                
        except Exception as e:
            logger.error(f"Error updating timestamps for successful tasks: {e}")
            logger.exception(e)

    async def _update_timestamps_for_worker_job_manager(self, batch_result, task_instance: Task, task_def: TaskDefinition, input_data: List[str]):
        """Update last execution timestamps for WorkerJobManager tasks based on batch success.

        When all jobs succeed, updates timestamps for all input_data targets.
        When some jobs fail, updates timestamps only for targets whose job succeeded
        (job order matches input_data order).
        """
        try:
            if batch_result.completed_jobs == 0:
                logger.info("No completed jobs, skipping timestamp updates")
                return

            current_time = datetime.now().timestamp()
            task_params = task_def.params or {}

            if batch_result.success_rate == 1.0:
                logger.info(f"All jobs succeeded ({batch_result.successful_jobs}/{batch_result.total_jobs}), updating timestamps for all targets")
                updated_count = 0
                for target in input_data:
                    timestamp_hash = task_instance.get_timestamp_hash(target, task_params)
                    if timestamp_hash:
                        try:
                            self.redis_client.set(timestamp_hash, str(current_time))
                            updated_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to update timestamp for target {target}: {e}")
                logger.info(f"Updated timestamps for {updated_count}/{len(input_data)} targets")
            else:
                # Partial success: update only targets whose job succeeded (job order matches input_data order)
                updated_count = 0
                failed_count = 0
                for i, job in enumerate(batch_result.jobs.values()):
                    if i >= len(input_data):
                        break
                    if job.is_successful:
                        target = input_data[i]
                        timestamp_hash = task_instance.get_timestamp_hash(target, task_params)
                        if timestamp_hash:
                            try:
                                self.redis_client.set(timestamp_hash, str(current_time))
                                updated_count += 1
                            except Exception as e:
                                logger.warning(f"Failed to update timestamp for target {target}: {e}")
                    else:
                        failed_count += 1
                logger.info(
                    f"Updated timestamps for {updated_count}/{len(input_data)} targets "
                    f"({failed_count} jobs failed)"
                )

        except Exception as e:
            logger.error(f"Error updating timestamps for WorkerJobManager tasks: {e}")
            logger.exception(e)

    async def _execute_task_unified(
        self,
        task_def: TaskDefinition,
        task_instance: Task,
        program_name: str,
        input_data: List[str],
        step_num: int,
        step_name: str,
        progressive_assets_sent_count: List[int],
    ) -> Dict:
        """
        Unified execution: get commands via generate_commands, spawn, parse, merge.
        Handles both standard tasks and orchestrators (dns_bruteforce, subdomain_permutations, resolve_ip_cidr).
        """
        try:
            if not self.job_manager:
                raise RuntimeError("WorkerJobManager not initialized")
            if not input_data:
                logger.info(f"No input data for task {task_def.name}")
                return {}

            params = task_def.params or {}
            context = {
                "step_name": step_name,
                "program_name": program_name,
                "task_def": task_def,
                "task_queue_client": self.task_queue_client,
                "job_manager": self.job_manager,
            }

            # 1. Generate commands (all tasks implement this)
            command_specs = await task_instance.generate_commands(input_data, params, context)
            if not command_specs:
                # Check for synthetic assets only (e.g. dns_bruteforce with all wildcards)
                synthetic = None
                if hasattr(task_instance, "get_synthetic_assets"):
                    synthetic = await task_instance.get_synthetic_assets(context)
                if synthetic:
                    output_mode = getattr(task_def, "output_mode", None)
                    if output_mode == "typosquat_findings":
                        return task_instance.transform_to_findings(synthetic, {"program_name": program_name})
                    return synthetic
                return {}

            # 2. Get synthetic assets (orchestrators like dns_bruteforce)
            synthetic_assets = None
            if hasattr(task_instance, "get_synthetic_assets"):
                synthetic_assets = await task_instance.get_synthetic_assets(context)

            # 3. Group commands by task_name for spawning and parsing
            by_task: Dict[str, List[CommandSpec]] = {}
            for spec in command_specs:
                by_task.setdefault(spec.task_name, []).append(spec)

            aggregated_assets = {}
            pending_result_tasks = []

            # 4. Spawn, wait, parse for each task type
            for task_name, specs in by_task.items():
                commands = [s.command for s in specs]
                timeout = 3600
                if specs and specs[0].params:
                    timeout = specs[0].params.get("timeout", 3600)

                # Use task_instance when parsing same task (has task_queue_client for spawned jobs)
                parser_task = task_instance if task_name == task_def.name else self.task_registry.get_task(task_name)()
                parent_is_resolve_ip_cidr = task_def.name == "resolve_ip_cidr"

                def make_result_processor(parser, pname, filter_ptr):
                    async def process_async(outputs: Dict[str, Any], batch_num: int):
                        batch_assets = {}
                        for task_id, output in outputs.items():
                            try:
                                normalized = parser.normalize_output_for_parsing(output)
                                parsed = parser.parse_output(normalized, params)
                                if filter_ptr and pname == "resolve_ip":
                                    for at, assets in parsed.items():
                                        if at == AssetType.IP:
                                            filtered = [a for a in assets if hasattr(a, "ptr") and a.ptr is not None]
                                            batch_assets.setdefault(at, []).extend(filtered)
                                        else:
                                            batch_assets.setdefault(at, []).extend(assets)
                                else:
                                    for at, assets in parsed.items():
                                        batch_assets.setdefault(at, []).extend(assets)
                            except Exception as e:
                                logger.error(f"Error parsing output from {task_id}: {e}")
                        if batch_assets and self.progressive_streaming_enabled:
                            task_id = list(outputs.keys())[0] if outputs else None
                            sent = await self._send_batch_assets_progressively(
                                batch_assets, program_name, step_name, task_id
                            )
                            progressive_assets_sent_count[0] += sent
                        self._merge_batch_into_aggregated_assets(
                            aggregated_assets, batch_assets, ip_field="ip"
                        )

                    def process(outputs: Dict[str, Any], batch_num: int):
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                t = asyncio.create_task(process_async(outputs, batch_num))
                                pending_result_tasks.append(t)
                            else:
                                loop.run_until_complete(process_async(outputs, batch_num))
                        except Exception as e:
                            logger.error(f"Error in result processor: {e}")

                    return process

                result_processor = (
                    make_result_processor(parser_task, task_name, parent_is_resolve_ip_cidr)
                    if self.progressive_streaming_enabled
                    else None
                )

                batch_result = await self.job_manager.spawn_batch(
                    task_name=task_name,
                    commands=commands,
                    batch_size=20,
                    timeout=timeout,
                    process_incrementally=self.progressive_streaming_enabled,
                    result_processor=result_processor,
                    step_name=step_name,
                )

                def progress_cb(completed: int, total: int):
                    logger.info(f"Task {task_def.name} progress: {completed}/{total} jobs ({completed / total:.1%})")

                await self.job_manager.wait_for_batch(
                    batch_result,
                    timeout=timeout * len(commands),
                    progress_callback=progress_cb,
                )

                if not self.progressive_streaming_enabled:
                    outputs = self.job_manager.get_job_outputs(batch_result)
                    for task_id, output in outputs.items():
                        try:
                            normalized = parser_task.normalize_output_for_parsing(output)
                            parsed = parser_task.parse_output(normalized, params)
                            if parent_is_resolve_ip_cidr and task_name == "resolve_ip":
                                for at, assets in parsed.items():
                                    if at == AssetType.IP:
                                        filtered = [a for a in assets if hasattr(a, "ptr") and a.ptr is not None]
                                        aggregated_assets.setdefault(at, []).extend(filtered)
                                    else:
                                        aggregated_assets.setdefault(at, []).extend(assets)
                            else:
                                for at, assets in parsed.items():
                                    aggregated_assets.setdefault(at, []).extend(assets)
                        except Exception as e:
                            logger.error(f"Error parsing output from {task_id}: {e}")

                self.job_manager.cleanup_batch(batch_result)
                self._last_batch_result = batch_result

            # Wait for any async result processors to finish
            if pending_result_tasks:
                await asyncio.gather(*pending_result_tasks)

            # 5. Merge synthetic assets
            if synthetic_assets:
                for at, assets in synthetic_assets.items():
                    aggregated_assets.setdefault(at, []).extend(assets)

            # 6. Typosquat findings mode
            output_mode = getattr(task_def, "output_mode", None)
            if output_mode == "typosquat_findings" and aggregated_assets:
                return task_instance.transform_to_findings(
                    aggregated_assets, {"program_name": program_name}
                )

            return aggregated_assets

        except Exception as e:
            logger.error(f"Error in unified task execution for {task_def.name}: {e}")
            logger.exception(e)
            return {}

    async def _execute_task_with_job_manager(self, task_def: TaskDefinition, task_instance: Task,
                                           program_name: str, input_data: List[str],
                                           step_num: int, step_name: str, progressive_assets_sent_count: List[int]) -> Dict:
        """Execute task using WorkerJobManager instead of legacy execution_manager"""
        try:
            if not self.job_manager:
                raise RuntimeError("WorkerJobManager not initialized")
            
            if not input_data:
                logger.info(f"No input data for task {task_def.name}")
                return {}
            
            # Get task parameters for chunking
            chunk_size = task_instance.get_chunk_size(input_data, task_def.params or {})

            # For timeout calculation, we need to consider if the task will generate variations
            # Check if the task has a prepare_input_data method that might expand the input
            timeout_input = input_data
            analyze_input_as_variations = task_def.params.get("analyze_input_as_variations", False) if task_def.params else False

            if hasattr(task_instance, 'prepare_input_data') and not analyze_input_as_variations:
                try:
                    # For standard mode (analyze_input_as_variations=false), we need to estimate
                    # the size after variation generation for proper timeout calculation
                    sample_processed = task_instance.prepare_input_data(input_data[:1], task_def.params or {})
                    if sample_processed and isinstance(sample_processed, list):
                        # Estimate total processed size based on sample
                        estimated_processed_size = len(sample_processed) * len(input_data)
                        timeout_input = ['x'] * min(estimated_processed_size, 1000)  # Cap for timeout calc
                        logger.debug(f"Estimated processed input size: {estimated_processed_size} for timeout calculation")
                except Exception as e:
                    logger.debug(f"Could not estimate processed input size for timeout: {e}")
                    timeout_input = input_data

            timeout = task_instance.get_timeout(timeout_input, task_def.params or {})
            logger.info(f"Executing {task_def.name} with {len(input_data)} inputs, chunk_size={chunk_size}, timeout={timeout}")

            # Chunk the input data
            input_chunks = []
            for i in range(0, len(input_data), chunk_size):
                chunk = input_data[i:i + chunk_size]
                input_chunks.append(chunk)

            # Generate commands for each chunk
            commands = []
            for chunk in input_chunks:
                if task_def.params.get("timeout", None) is not None:
                    task_def.params["timeout"] = timeout

                command = task_instance.get_command(chunk, task_def.params or {})
                # Handle both single commands and arrays of commands
                if isinstance(command, list):
                    commands.extend(command)
                else:
                    commands.append(command)
            
            logger.info(f"Generated {len(commands)} commands for {len(input_chunks)} chunks")

            # Handle AWS API Gateway proxy setup if enabled
            # NOTE: Proxies will be created in batches during execution (see batch processing below)
            # This avoids creating all proxies upfront and limits active API Gateways
            proxy_enabled = False
            proxy_targets_for_batching = None

            if task_def.use_proxy:
                if hasattr(task_instance, 'supports_proxy') and task_instance.supports_proxy():
                    try:
                        logger.info(f"Proxy enabled for task {task_def.name} - will use batch-wise proxy creation")

                        # Extract targets that need proxying (DON'T create them yet)
                        proxy_targets_for_batching = task_instance.extract_proxy_targets(input_data, task_def.params or {})

                        if proxy_targets_for_batching:
                            proxy_enabled = True
                            # Get batch size from env or use default
                            from task_components import PROXY_BATCH_SIZE
                            logger.info(f"Found {len(proxy_targets_for_batching)} targets for proxy creation")
                            logger.info(f"Will create proxies in batches of {PROXY_BATCH_SIZE} during execution")
                        else:
                            logger.warning(f"No proxy targets extracted for task {task_def.name}")

                    except Exception as e:
                        logger.error(f"Error extracting proxy targets for task {task_def.name}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        # Continue without proxies on error (graceful degradation)
                        proxy_enabled = False
                else:
                    logger.warning(f"Task {task_def.name} does not support proxying")

            # Initialize variables for asset accumulation
            aggregated_assets = {}  # Accumulate all assets from batches
            progressive_asset_counts = {}  # Track counts without re-processing
            proxy_mappings_by_batch = {}  # Store proxy mappings for each batch

            # Define progressive result processor for memory efficiency

            async def process_batch_results_async(outputs: Dict[str, Any], batch_num: int):
                logger.info(f"Processing results from batch {batch_num} for task {task_def.name}")
                batch_assets = {}

                # Get proxy mappings for this batch
                logger.debug(f"Looking for proxy mappings with key {batch_num}, available keys: {list(proxy_mappings_by_batch.keys())}")
                batch_proxy_mappings = proxy_mappings_by_batch.get(batch_num, {})
                if batch_proxy_mappings:
                    logger.debug(f"Found {len(batch_proxy_mappings)} proxy mappings for batch {batch_num}")
                else:
                    logger.debug(f"No proxy mappings found for batch {batch_num}")

                for task_id, output in outputs.items():
                    try:
                        # Replace proxy URLs in raw output BEFORE parsing if proxy was enabled
                        if proxy_enabled and batch_proxy_mappings and hasattr(task_instance, 'replace_proxies_in_output'):
                            logger.debug(f"Replacing proxy URLs in raw output for task {task_id}")
                            # Extract the actual output string from the result dict if needed
                            output_str = output.get('output', output) if isinstance(output, dict) else output
                            if output_str:
                                replaced_output = task_instance.replace_proxies_in_output(output_str, batch_proxy_mappings)
                                # Update the output dict with the replaced string
                                if isinstance(output, dict):
                                    output['output'] = replaced_output
                                else:
                                    output = replaced_output

                        # Normalize output format for parsing (handle both string and dict inputs)
                        normalized_output = task_instance.normalize_output_for_parsing(output)

                        # Check output_mode to determine which processing method to use
                        output_mode = getattr(task_def, 'output_mode', None)
                        logger.info(f"🔍 DEBUG: task={task_def.name}, output_mode={output_mode}, type={type(output_mode)}")

                        if output_mode == 'typosquat_findings':
                            # Typosquat findings mode: parse to assets then transform to findings
                            logger.info(f"📊 Using typosquat findings mode for task {task_def.name}")
                            parsed = task_instance.process_output_for_typosquat_mode(normalized_output, task_def.params or {})
                        else:
                            # Normal mode: parse output to assets
                            parsed = task_instance.parse_output(normalized_output, task_def.params or {})

                        # Merge parsed assets with deduplication
                        for asset_type, assets in parsed.items():
                            if asset_type not in batch_assets:
                                batch_assets[asset_type] = []

                            initial_bucket_len = len(batch_assets[asset_type])
                            self._extend_batch_bucket_unique(
                                batch_assets, asset_type, assets, ip_field="ip_address"
                            )

                            # Track counts for progressive streaming (count only newly added deduplicated assets)
                            if self.progressive_streaming_enabled:
                                logger.debug(f"asset_type: {asset_type}")
                                asset_type_key = asset_type.value if hasattr(asset_type, 'value') else str(asset_type)
                                if asset_type_key not in progressive_asset_counts:
                                    progressive_asset_counts[asset_type_key] = 0
                                new_assets_added = len(batch_assets[asset_type]) - initial_bucket_len
                                progressive_asset_counts[asset_type_key] += new_assets_added

                    except Exception as e:
                        logger.error(f"Error parsing output from task {task_id}: {e}")
                        logger.error(f"Raw output type: {type(output)}")
                        if isinstance(output, str):
                            logger.error(f"Raw output preview: {output[:200]}...")
                        elif isinstance(output, dict):
                            logger.error(f"Raw output keys: {list(output.keys()) if output else 'empty dict'}")

                # Send batch assets immediately if we have progressive streaming enabled
                if self.progressive_streaming_enabled and batch_assets:
                    # Use task_id to allow each worker job to send its own assets
                    # Each call to process_batch_results is for one job, so outputs should have one key
                    task_id = list(outputs.keys())[0] if outputs else None
                    logger.info(f"Sending progressive assets for task {task_id} with {len(batch_assets)} asset types")

                    assets_sent = await self._send_batch_assets_progressively(batch_assets, program_name, step_name, task_id)
                    progressive_assets_sent_count[0] += assets_sent
                    logger.info(f"Sent {assets_sent} assets for task {task_id}")

                    self._merge_batch_into_aggregated_assets(
                        aggregated_assets,
                        batch_assets,
                        ip_field="ip_address",
                        service_extend=False,
                    )

            # Create synchronous wrapper for WorkerJobManager compatibility
            def process_batch_results(outputs: Dict[str, Any], batch_num: int):
                """Synchronous wrapper for async result processor"""
                try:
                    # Create a task to run the async function
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is already running, create task
                        asyncio.create_task(process_batch_results_async(outputs, batch_num))
                    else:
                        # If no loop is running, run synchronously
                        loop.run_until_complete(process_batch_results_async(outputs, batch_num))
                except Exception as e:
                    logger.error(f"Error in synchronous result processor wrapper: {e}")
            
            # Use WorkerJobManager for batch execution
            # Note: result_processor is now handled by individual job output handlers for progressive streaming
            logger.debug(f"Commands: {commands}")
            if len(commands) == 0:
                logger.info(f"No commands to spawn for task {task_def.name}")
                return {}
            elif proxy_enabled and proxy_targets_for_batching:
                # Batch-wise proxy execution: create proxies per batch to limit active API Gateways
                from services.fireprox import FireProxService
                from task_components import PROXY_BATCH_SIZE, PROXY_RATE_LIMIT

                total_commands = len(commands)
                proxy_batch_size = PROXY_BATCH_SIZE
                total_batches = (total_commands + proxy_batch_size - 1) // proxy_batch_size

                logger.info(f"🔄 Proxy-aware batching: {total_commands} commands split into {total_batches} batches of {proxy_batch_size}")
                logger.info(f"📊 This will create max {proxy_batch_size} active API Gateways at a time")

                all_batch_results = []

                for batch_num in range(total_batches):
                    start_idx = batch_num * proxy_batch_size
                    end_idx = min(start_idx + proxy_batch_size, total_commands)
                    batch_commands = commands[start_idx:end_idx]
                    batch_proxy_targets = proxy_targets_for_batching[start_idx:end_idx]

                    logger.info(f"📦 Batch {batch_num + 1}/{total_batches}: Processing {len(batch_commands)} commands")

                    # Initialize FireProx for this batch
                    fireprox_service = FireProxService(
                        rate_limit=PROXY_RATE_LIMIT,
                        burst_size=proxy_batch_size,
                        max_retries=10
                    )

                    proxy_mappings = {}

                    try:
                        # Step 1: Create proxies for this batch
                        logger.info(f"🌐 Creating {len(batch_proxy_targets)} API Gateways for batch {batch_num + 1}")
                        for target_url in batch_proxy_targets:
                            try:
                                mapping = fireprox_service.create_proxy(target_url)
                                if mapping:
                                    proxy_mappings[mapping.original_url] = mapping.proxy_url
                                    logger.debug(f"✓ Created proxy: {target_url} -> {mapping.proxy_url}")
                            except Exception as e:
                                logger.error(f"Error creating proxy for {target_url}: {e}")

                        if not proxy_mappings:
                            logger.error(f"No proxies created for batch {batch_num + 1}, skipping batch")
                            continue

                        logger.info(f"✓ Created {len(proxy_mappings)} proxies for batch {batch_num + 1}")

                        # Store proxy mappings for this batch so result processor can access them
                        # Result processor logs show "batch {num}" where num matches our "batch_num + 1"
                        proxy_mappings_by_batch[batch_num + 1] = proxy_mappings
                        logger.debug(f"Stored proxy mappings for batch {batch_num + 1} in proxy_mappings_by_batch")

                        # Step 2: Replace URLs in batch commands
                        proxied_batch_commands = []
                        for cmd in batch_commands:
                            proxied_cmd = task_instance.replace_targets_with_proxies(cmd, proxy_mappings)
                            proxied_batch_commands.append(proxied_cmd)

                        # Step 3: Spawn batch with proxied commands
                        logger.info(f"📤 Spawning {len(proxied_batch_commands)} jobs for batch {batch_num + 1}")
                        batch_result = await self.job_manager.spawn_batch(
                            task_name=task_def.name,
                            commands=proxied_batch_commands,
                            batch_size=20,  # Internal spawn_batch batching
                            timeout=timeout,
                            process_incrementally=self.progressive_streaming_enabled,
                            result_processor=process_batch_results if self.progressive_streaming_enabled else None,
                            step_name=step_name
                        )

                        # Step 4: Wait for batch completion
                        logger.info(f"⏳ Waiting for batch {batch_num + 1} to complete...")
                        await self.job_manager.wait_for_batch(
                            batch_result,
                            timeout=timeout * len(batch_commands)
                        )

                        # Update last-execution timestamps for this batch's targets (per-batch so cache is correct)
                        batch_input_slice = input_data[start_idx:end_idx]
                        await self._update_timestamps_for_worker_job_manager(
                            batch_result, task_instance, task_def, batch_input_slice
                        )

                        all_batch_results.append(batch_result)
                        logger.info(f"✓ Batch {batch_num + 1} completed")

                    finally:
                        # Step 5: ALWAYS cleanup proxies after each batch
                        if proxy_mappings:
                            logger.info(f"🧹 Cleaning up {len(proxy_mappings)} API Gateways for batch {batch_num + 1}")
                            try:
                                success, failed = fireprox_service.cleanup_all()
                                logger.info(f"✓ Cleanup batch {batch_num + 1}: {success} deleted, {failed} failed")
                            except Exception as cleanup_error:
                                logger.error(f"Error during proxy cleanup for batch {batch_num + 1}: {cleanup_error}")

                # Timestamps already updated per batch above; do not run single post-execution update
                self._last_batch_result = None
                logger.info(f"✅ All {total_batches} batches completed")

                # Deduplicate assets and cleanup batch resources (same shape as non-proxy path)
                deduplicated_assets = self._deduplicate_assets(aggregated_assets)
                for br in all_batch_results:
                    self.job_manager.cleanup_batch(br)
                total_assets = sum(len(assets) for assets in deduplicated_assets.values())
                logger.info(f"Task {task_def.name} completed successfully: {total_assets} unique assets across {len(deduplicated_assets)} types")
                return deduplicated_assets

            else:
                # Normal execution without proxies
                batch_result = await self.job_manager.spawn_batch(
                    task_name=task_def.name,
                    commands=commands,
                    batch_size=20,  # Reasonable batch size for most tasks
                    timeout=timeout,
                    process_incrementally=self.progressive_streaming_enabled,
                    result_processor=process_batch_results if self.progressive_streaming_enabled else None,
                    step_name=step_name
                )
                
                # Wait for all jobs to complete with progress tracking
                def progress_callback(completed: int, total: int):
                    logger.info(f"Task {task_def.name} progress: {completed}/{total} jobs completed ({completed/total:.1%})")
                
                await self.job_manager.wait_for_batch(
                    batch_result, 
                    timeout=timeout * len(input_chunks),  # Scale timeout by number of chunks
                    progress_callback=progress_callback
                )
                
                # Get final statistics
                stats = self.job_manager.get_job_statistics(batch_result)
                logger.info(f"Task {task_def.name} completed: {stats}")
                
                # Note: If progressive streaming was enabled, assets were already processed in process_batch_results
                # We still need to collect outputs for tracking purposes, but avoid double processing
                outputs = self.job_manager.get_job_outputs(batch_result)

                # Handle asset aggregation based on streaming mode
                # aggregated_assets already initialized above
                if not self.progressive_streaming_enabled:
                    # Traditional mode: parse and aggregate all assets
                    logger.info("Using traditional processing mode - parsing all outputs")
                    for task_id, output in outputs.items():
                        try:
                            # Note: Proxy URL replacement is now handled per-batch in batch-wise execution
                            # so we don't need global proxy_mappings replacement here

                            # Normalize output format for parsing (handle both string and dict inputs)
                            normalized_output = task_instance.normalize_output_for_parsing(output)

                            # Check output_mode to determine which processing method to use
                            output_mode = getattr(task_def, 'output_mode', None)
                            logger.info(f"🔍 DEBUG (traditional): task={task_def.name}, output_mode={output_mode}, type={type(output_mode)}")

                            if output_mode == 'typosquat_findings':
                                # Typosquat findings mode: parse to assets then transform to findings
                                logger.info(f"📊 Using typosquat findings mode for task {task_def.name}")
                                parsed = task_instance.process_output_for_typosquat_mode(normalized_output, task_def.params or {})
                            else:
                                # Normal mode: parse output to assets
                                parsed = task_instance.parse_output(normalized_output, task_def.params or {})

                            # Merge assets with deduplication
                            for asset_type, assets in parsed.items():
                                if asset_type not in aggregated_assets:
                                    aggregated_assets[asset_type] = []

                                # Deduplicate assets based on their identifying attribute
                                for asset in assets:
                                    if asset_type.value == 'subdomain':
                                        # For subdomains, deduplicate by name
                                        asset_name = getattr(asset, 'name', str(asset))
                                        if not any(getattr(existing, 'name', str(existing)) == asset_name for existing in aggregated_assets[asset_type]):
                                            aggregated_assets[asset_type].append(asset)
                                    elif asset_type.value == 'ip':
                                        # For IPs, deduplicate by ip_address
                                        asset_ip = getattr(asset, 'ip_address', str(asset))
                                        if not any(getattr(existing, 'ip_address', str(existing)) == asset_ip for existing in aggregated_assets[asset_type]):
                                            aggregated_assets[asset_type].append(asset)
                                    elif asset_type.value == 'url':
                                        # For URLs, deduplicate by url
                                        asset_url = getattr(asset, 'url', str(asset))
                                        if not any(getattr(existing, 'url', str(existing)) == asset_url for existing in aggregated_assets[asset_type]):
                                            aggregated_assets[asset_type].append(asset)
                                    elif asset_type.value == 'apex_domain':
                                        an = self._apex_domain_asset_name(asset)
                                        if not any(
                                            self._apex_domain_asset_name(existing) == an
                                            for existing in aggregated_assets[asset_type]
                                        ):
                                            aggregated_assets[asset_type].append(asset)
                                    else:
                                        # For other asset types, use string representation for deduplication
                                        asset_str = str(asset)
                                        if asset_str not in [str(existing) for existing in aggregated_assets[asset_type]]:
                                            aggregated_assets[asset_type].append(asset)
                        except Exception as e:
                            logger.error(f"Error parsing output from task {task_id}: {e}")
                else:
                    # Progressive streaming mode: assets already sent, just log completion
                    logger.debug("Progressive streaming mode enabled - assets already processed and sent, skipping traditional parsing")
                # Assets are accumulated in the progressive streaming loop above

                # Store batch result for timestamp updates before cleanup
                self._last_batch_result = batch_result

                # Clean up job resources
                self.job_manager.cleanup_batch(batch_result)

                # Deduplicate assets before returning
                deduplicated_assets = self._deduplicate_assets(aggregated_assets)

                total_assets = sum(len(assets) for assets in deduplicated_assets.values())
                logger.info(f"Task {task_def.name} completed successfully: {total_assets} unique assets across {len(deduplicated_assets)} types")

                # Process any pending typosquat URLs after assets have been sent
                #if task_def.name == "typosquat_detection" and hasattr(task_instance, 'process_pending_typosquat_urls'):
                #    try:
                #        logger.info("Processing pending typosquat URLs after domain processing")
                #        task_instance.process_pending_typosquat_urls()
                #    except Exception as e:
                #        logger.error(f"Error processing pending typosquat URLs: {e}")

                # Note: Proxy cleanup is now handled per-batch in batch-wise execution
                # Each batch cleans up its own proxies in the finally block

                return deduplicated_assets

        except Exception as e:
            logger.error(f"Error executing task {task_def.name} with WorkerJobManager: {e}")
            logger.exception("Full traceback:")

            # Note: Proxy cleanup on error is now handled per-batch in batch-wise execution
            # Each batch's finally block ensures cleanup even on error

            raise
    
    async def _send_batch_assets_progressively(self, assets_and_findings: Dict, program_name: str, step_name: str, task_id: Optional[str] = None) -> int:
        """Send batch assets progressively during execution"""
        assets_sent = 0
        try:
            # Check if assets were already sent for this task (prevents duplicate sends)
            # For worker jobs, include task_id to allow each job to send its own assets
            if task_id:
                task_key = f"{step_name}_{program_name}_{task_id}"
            else:
                task_key = f"{step_name}_{program_name}"

            if task_key in self._task_assets_sent_guard:
                logger.info(f"Assets already sent for task {task_key}, skipping progressive batch send")
                return 0

            if not self.execution_id:
                logger.warning("No execution_id available for progressive asset sending")
                return 0

            assets = {}
            findings = {}

            for k, v in assets_and_findings.items():
                if isinstance(k, AssetType):
                    if k.value == "screenshot":
                        # Handle screenshots separately
                        screenshots = v
                    else:
                        assets[k.value] = v
                elif isinstance(k, FindingType):
                    findings[k.value] = v
            # Check if we have any actual assets to send
            asset_count = sum(len(v) if isinstance(v, list) else 0 for v in assets.values())
            finding_count = sum(len(v) if isinstance(v, list) else 0 for v in findings.values())
            screenshot_count = len(screenshots) if 'screenshots' in locals() and screenshots else 0
            
            if asset_count == 0 and finding_count == 0 and screenshot_count == 0:
                logger.debug("Nothing to send - skipping API call")
                return 0
            
            nuclei_success = True
            typosquat_domain_success = True
            assets_success = True
            assets_sent = 0
            findings_sent = 0
            success = True
            if not self.async_data_api_client:
                logger.error("Async data API client not initialized")
                return 0

            # Send other regular assets via unified API FIRST (so related items are created before nuclei findings)
            api_response = None
            if assets and any(assets.values()):  # Check if dict is not empty AND contains actual asset lists
                try:
                    api_response = await self.async_data_api_client.post_assets_unified(
                        assets, program_name, self.execution_id, step_name
                    )
                    assets_success = api_response.get("status") != "error"

                    if assets_success:
                        assets_sent += asset_count

                        # Store API response data for workflow status updates
                        if api_response and 'summary' in api_response:
                            self._store_step_api_response(step_name, api_response)
                    else:
                        logger.warning("Failed to send regular assets via unified API")
                except Exception as e:
                    logger.error(f"Error sending regular assets via unified API: {e}")
                    assets_success = False

            # Send screenshots to dedicated endpoint
            screenshot_success = True
            if 'screenshots' in locals() and screenshots:
                try:
                    logger.info(f"Progressively sending {len(screenshots)} screenshots to dedicated endpoint")
                    screenshot_response = await self.async_data_api_client._send_screenshot_assets(
                        screenshots, program_name, self.execution_id, step_name
                    )
                    screenshot_success = screenshot_response[0]  # Returns (success, responses)
                    if screenshot_success:
                        assets_sent += len(screenshots)
                        logger.info(f"Successfully sent {len(screenshots)} screenshots progressively")
                    else:
                        logger.warning("Failed to send screenshots via dedicated endpoint")
                except Exception as e:
                    logger.error(f"Error sending screenshots via dedicated endpoint: {e}")
                    screenshot_success = False

            # Send findings to dedicated endpoints LAST (after related assets are created)
            nuclei_response = None
            nuclei_findings = findings.get('nuclei', [])
            broken_link_findings = findings.get('broken_link', [])
            wpscan_findings = findings.get('wpscan', [])
            typosquat_domain_findings = findings.get('typosquat_domain', [])
            typosquat_url_findings = findings.get('typosquat_url', [])
            typosquat_screenshot_findings = findings.get('typosquat_screenshot', [])

            # Consolidate all typosquat findings for unified sending
            has_typosquat_findings = typosquat_domain_findings or typosquat_url_findings or typosquat_screenshot_findings
            if nuclei_findings:
                try:
                    nuclei_response = await self.async_data_api_client.post_nuclei_findings_unified(
                        nuclei_findings, program_name,
                        workflow_id=None, step_name=step_name, execution_id=self.execution_id
                    )
                    nuclei_success = nuclei_response.get("status") != "error"

                    if nuclei_success:
                        logger.info(f"Progressively sent {len(nuclei_findings)} nuclei findings to dedicated endpoint")
                        findings_sent += len(nuclei_findings)

                        # Store API response data for workflow status updates
                        if nuclei_response and 'summary' in nuclei_response:
                            self._store_step_api_response(step_name, nuclei_response)

                        # Register nuclei job with coordinator if it's async
                        processing_mode = nuclei_response.get("processing_mode", "unknown")
                        if processing_mode in ["background", "unified_async"]:
                            job_id = nuclei_response.get("job_id")
                            if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                                try:
                                    logger.info(f"🔍 DEBUG: Registering progressive nuclei findings job {job_id} with progressive streamer")
                                    # Track job with progressive streamer
                                    # Track job with progressive streamer
                                    self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                    logger.debug(f"Registered nuclei job {job_id} for step {step_name}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to register progressive nuclei findings job {job_id} with progressive streamer: {e}")
                                    logger.error(f"🔍 DEBUG: Registration error: {type(e).__name__}: {str(e)}")
                            else:
                                logger.warning(f"⚠️ Cannot register progressive nuclei findings job {job_id} - progressive streamer not available")
                                logger.debug("Progressive streamer not available for nuclei findings registration")
                    else:
                        logger.warning("Failed to send nuclei findings to dedicated endpoint")
                except Exception as e:
                    logger.error(f"Error sending nuclei findings to dedicated endpoint: {e}")
                    nuclei_success = False

            # Send typosquat findings to their respective dedicated endpoints
            typosquat_success = True
            typosquat_domain_response = None
            typosquat_url_response = None
            typosquat_screenshot_response = None

            # Send typosquat domain findings to /findings/typosquat
            if typosquat_domain_findings:
                try:
                    logger.info(f"Progressively sending {len(typosquat_domain_findings)} typosquat domain findings to /findings/typosquat")
                    typosquat_domain_response = await self.async_data_api_client.post_typosquat_domain_findings(
                        typosquat_domain_findings, program_name
                    )
                    domain_success = typosquat_domain_response.get("status") != "error"

                    if domain_success:
                        logger.info(f"Progressively sent {len(typosquat_domain_findings)} typosquat domain findings")
                        findings_sent += len(typosquat_domain_findings)
                        if typosquat_domain_response and 'summary' in typosquat_domain_response:
                            self._store_step_api_response(step_name, typosquat_domain_response)
                    else:
                        logger.warning("Failed to send typosquat domain findings")
                        typosquat_success = False
                except Exception as e:
                    logger.error(f"Error sending typosquat domain findings: {e}")
                    typosquat_success = False

            # Send typosquat URL findings to /findings/typosquat-url
            if typosquat_url_findings:
                try:
                    logger.info(f"Progressively sending {len(typosquat_url_findings)} typosquat URL findings to /findings/typosquat-url")
                    typosquat_url_response = await self.async_data_api_client.post_typosquat_url_findings(
                        typosquat_url_findings, program_name
                    )
                    url_success = typosquat_url_response.get("status") != "error"

                    if url_success:
                        # Use actual successful count from aggregated response
                        successful_count = typosquat_url_response.get("summary", {}).get("successful", len(typosquat_url_findings))
                        logger.info(f"Progressively sent {successful_count}/{len(typosquat_url_findings)} typosquat URL findings")
                        findings_sent += successful_count
                        if typosquat_url_response and 'summary' in typosquat_url_response:
                            self._store_step_api_response(step_name, typosquat_url_response)
                    else:
                        logger.warning("Failed to send typosquat URL findings")
                        typosquat_success = False
                except Exception as e:
                    logger.error(f"Error sending typosquat URL findings: {e}")
                    typosquat_success = False

            # Send typosquat screenshot findings to /findings/typosquat-screenshot
            if typosquat_screenshot_findings:
                try:
                    logger.info(f"Progressively sending {len(typosquat_screenshot_findings)} typosquat screenshot findings to /findings/typosquat-screenshot")
                    typosquat_screenshot_response = await self.async_data_api_client.post_typosquat_screenshot_findings(
                        typosquat_screenshot_findings, program_name
                    )
                    screenshot_success = typosquat_screenshot_response.get("status") != "error"

                    if screenshot_success:
                        # Use actual successful count from aggregated response
                        successful_count = typosquat_screenshot_response.get("summary", {}).get("successful", len(typosquat_screenshot_findings))
                        logger.info(f"Progressively sent {successful_count}/{len(typosquat_screenshot_findings)} typosquat screenshot findings")
                        findings_sent += successful_count
                        if typosquat_screenshot_response and 'summary' in typosquat_screenshot_response:
                            self._store_step_api_response(step_name, typosquat_screenshot_response)
                    else:
                        logger.warning("Failed to send typosquat screenshot findings")
                        typosquat_success = False
                except Exception as e:
                    logger.error(f"Error sending typosquat screenshot findings: {e}")
                    typosquat_success = False

            # Send broken link findings to dedicated endpoint
            broken_link_success = True
            if broken_link_findings:
                try:
                    logger.info(f"Progressively sending {len(broken_link_findings)} broken link findings to /findings/broken-links")
                    broken_link_success = await self.async_data_api_client.post_broken_link_findings(
                        broken_link_findings, program_name
                    )
                    if broken_link_success:
                        logger.info(f"Progressively sent {len(broken_link_findings)} broken link findings")
                        findings_sent += len(broken_link_findings)
                    else:
                        logger.warning("Failed to send broken link findings")
                except Exception as e:
                    logger.error(f"Error sending broken link findings: {e}")
                    broken_link_success = False
            
            # Send WPScan findings to dedicated endpoint
            wpscan_success = True
            if wpscan_findings:
                try:
                    logger.info(f"Progressively sending {len(wpscan_findings)} WPScan findings to /findings/wpscan")
                    wpscan_response = await self.async_data_api_client.post_wpscan_findings_unified(
                        wpscan_findings, program_name,
                        workflow_id=None, step_name=step_name, execution_id=self.execution_id
                    )
                    wpscan_success = wpscan_response.get("status") != "error"
                    
                    if wpscan_success:
                        logger.info(f"Progressively sent {len(wpscan_findings)} WPScan findings to dedicated endpoint")
                        findings_sent += len(wpscan_findings)
                        
                        # Store API response data for workflow status updates
                        if wpscan_response and 'summary' in wpscan_response:
                            self._store_step_api_response(step_name, wpscan_response)
                        
                        # Register WPScan job with coordinator if it's async
                        processing_mode = wpscan_response.get("processing_mode", "unknown")
                        if processing_mode in ["background", "unified_async"]:
                            job_id = wpscan_response.get("job_id")
                            if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                                try:
                                    logger.info(f"🔍 DEBUG: Registering progressive WPScan findings job {job_id} with progressive streamer")
                                    self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                    logger.debug(f"Registered WPScan job {job_id} for step {step_name}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to register progressive WPScan findings job {job_id} with progressive streamer: {e}")
                                    logger.error(f"🔍 DEBUG: Registration error: {type(e).__name__}: {str(e)}")
                            else:
                                logger.warning(f"⚠️ Cannot register progressive WPScan findings job {job_id} - progressive streamer not available")
                                logger.debug("Progressive streamer not available for WPScan findings registration")
                    else:
                        logger.warning("Failed to send WPScan findings to dedicated endpoint")
                except Exception as e:
                    logger.error(f"Error sending WPScan findings to dedicated endpoint: {e}")
                    wpscan_success = False
            
            success = nuclei_success and typosquat_success and assets_success and screenshot_success and broken_link_success and wpscan_success

            if success:
                screenshot_count = len(screenshots) if 'screenshots' in locals() and screenshots else 0
                logger.debug(f"Progressively sent {assets_sent} assets from batch ({len(nuclei_findings)} nuclei, {len(broken_link_findings)} broken_links, {len(typosquat_domain_findings)} typosquat_domains, {len(typosquat_url_findings)} typosquat_urls, {len(typosquat_screenshot_findings)} typosquat_screenshots, {asset_count} regular, {screenshot_count} screenshots)")
                
                # Handle coordinator registration for unified jobs (both nuclei and regular)
                # Register nuclei job with coordinator if it's async
                # NOTE: Nuclei jobs are already registered in the dedicated nuclei processing section above
                # with the correct "findings" job type, so we skip registration here to avoid overwriting
                if nuclei_findings and nuclei_response:
                    processing_mode = nuclei_response.get("processing_mode", "unknown")
                    if processing_mode == "unified_async":
                        job_id = nuclei_response.get("job_id")
                        logger.info(f"ℹ️ Skipping duplicate registration of nuclei job {job_id} (already registered as findings type)")

                # Register typosquat domain findings job with coordinator if it's async
                if typosquat_domain_findings and typosquat_domain_response:
                    processing_mode = typosquat_domain_response.get("processing_mode", "unknown")
                    if processing_mode == "unified_async":
                        job_id = typosquat_domain_response.get("job_id")
                        if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                            try:
                                self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                logger.debug(f"Registered typosquat domain findings job {job_id} for step {step_name}")
                            except Exception as e:
                                logger.error(f"❌ Failed to register typosquat domain findings job {job_id}: {e}")
                        else:
                            logger.debug("Progressive streamer not available for typosquat domain findings registration")

                # Register typosquat URL findings job with coordinator if it's async
                if typosquat_url_findings and typosquat_url_response:
                    processing_mode = typosquat_url_response.get("processing_mode", "unknown")
                    if processing_mode == "unified_async":
                        job_id = typosquat_url_response.get("job_id")
                        if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                            try:
                                self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                logger.debug(f"Registered typosquat URL findings job {job_id} for step {step_name}")
                            except Exception as e:
                                logger.error(f"❌ Failed to register typosquat URL findings job {job_id}: {e}")
                        else:
                            logger.debug("Progressive streamer not available for typosquat URL findings registration")

                # Register typosquat screenshot findings job with coordinator if it's async
                if typosquat_screenshot_findings and typosquat_screenshot_response:
                    processing_mode = typosquat_screenshot_response.get("processing_mode", "unknown")
                    if processing_mode == "unified_async":
                        job_id = typosquat_screenshot_response.get("job_id")
                        if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                            try:
                                self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "findings")
                                logger.debug(f"Registered typosquat screenshot findings job {job_id} for step {step_name}")
                            except Exception as e:
                                logger.error(f"❌ Failed to register typosquat screenshot findings job {job_id}: {e}")
                        else:
                            logger.debug("Progressive streamer not available for typosquat screenshot findings registration")

                # Register regular assets job with progressive streamer if it's async
                if assets and api_response:
                    processing_mode = api_response.get("processing_mode", "unknown")
                    if processing_mode == "unified_async":
                        job_id = api_response.get("job_id")
                        if job_id and self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
                            try:
                                # Track job with progressive streamer
                                self.execution_manager.progressive_streamer._track_job_for_step(step_name, job_id, "assets")
                                logger.debug(f"Registered assets job {job_id} for step {step_name}")
                            except Exception as e:
                                logger.error(f"❌ Failed to register regular assets job {job_id} from WorkerJobManager with progressive streamer: {e}")

                # Set guard flag to prevent duplicate sends
                logger.debug(f"Setting progressive guard with key: {task_key}")
                self._task_assets_sent_guard.add(task_key)
            else:
                logger.warning("Failed to progressively send batch assets")

        except Exception as e:
            logger.error(f"Error sending batch assets progressively: {e}")
            logger.exception(f"Full traceback: {e}")

        return assets_sent

    def _store_step_api_response(self, step_name: str, api_response: Dict[str, Any]):
        """Store API response data for a step to be used in workflow status updates"""
        if step_name not in self._step_api_responses:
            self._step_api_responses[step_name] = []

        self._step_api_responses[step_name].append(api_response)

    def start_step_timing(self, step_name: str):
        """Start timing for a step"""
        from datetime import datetime
        self._step_timing[step_name] = {
            'started_at': datetime.utcnow().isoformat() + 'Z'
        }

    def complete_step_timing(self, step_name: str):
        """Complete timing for a step"""
        from datetime import datetime
        if step_name in self._step_timing:
            self._step_timing[step_name]['completed_at'] = datetime.utcnow().isoformat() + 'Z'
            logger.debug(f"Completed timing for step '{step_name}'")
        else:
            logger.warning(f"Cannot complete timing for step '{step_name}' - no start time recorded")

    def get_step_status_data(self, step_name: str, actual_step_outputs: Dict = None) -> Dict[str, Any]:
        """Get aggregated status data for a step including detailed asset counts"""
        responses = self._step_api_responses.get(step_name, [])
        has_responses = bool(responses)

        # Also check progressive streamer responses if available
        if self.execution_manager and hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
            # Check if progressive streamer has step responses (it should track them)
            if hasattr(self.execution_manager.progressive_streamer, '_step_api_responses'):
                streamer_responses = self.execution_manager.progressive_streamer._step_api_responses.get(step_name, [])
                if streamer_responses:
                    responses.extend(streamer_responses)
                    has_responses = True
                    logger.debug(f"Added {len(streamer_responses)} responses from progressive streamer")


        # Get timing information for this step (always available)
        timing_info = self._step_timing.get(step_name, {})

        # Aggregate all API responses for this step (only if responses exist)
        asset_types = {}
        detailed_counts = {}

        if has_responses:
            logger.debug(f"Processing {len(responses)} API responses for step status")
            for i, response in enumerate(responses):
                if 'summary' in response:
                    summary = response['summary']
                    # Skip aggregating total_assets from API responses as they're not deduplicated
                    # We'll calculate it from deduplicated detailed_counts instead

                    # Aggregate asset_types (legacy format)
                    if 'asset_types' in summary:
                        for asset_type, count in summary['asset_types'].items():
                            asset_types[asset_type] = asset_types.get(asset_type, 0) + count

                    # Also handle finding_types for findings responses
                    if 'finding_types' in summary:
                        for finding_type, count in summary['finding_types'].items():
                            asset_types[finding_type] = asset_types.get(finding_type, 0) + count

                    # Aggregate detailed_counts (new format)
                    if 'detailed_counts' in summary:

                        # For step 2 and later, don't apply race condition fixes
                        # since "updated" operations are legitimate
                        # Only apply fixes for step 1 if needed
                        # For now, use API counts as-is for all steps

                        # Now do the normal aggregation
                        for asset_type, counts in summary['detailed_counts'].items():
                            if asset_type not in detailed_counts:
                                # Handle both assets and findings formats
                                if 'created_findings' in counts:
                                    # This is a findings response - map findings fields to assets fields
                                    detailed_counts[asset_type] = {
                                        'total': counts.get('total_count', 0),
                                        'created': counts.get('created_count', 0),
                                        'updated': counts.get('updated_count', 0),
                                        'skipped': counts.get('skipped_count', 0),
                                        'out_of_scope': 0,  # Findings don't have out_of_scope
                                        'failed': counts.get('failed_count', 0),
                                        'created_assets': counts.get('created_findings', []),
                                        'updated_assets': counts.get('updated_findings', []),
                                        'skipped_assets': counts.get('skipped_findings', []),
                                        'failed_assets': counts.get('failed_findings', []),
                                        'errors': counts.get('errors', [])
                                    }
                                else:
                                    # This is an assets response - use standard fields
                                    detailed_counts[asset_type] = {
                                        'total': counts.get('total_count', counts.get('total', 0)),
                                        'created': counts.get('created_count', counts.get('created', 0)),
                                        'updated': counts.get('updated_count', counts.get('updated', 0)),
                                        'skipped': counts.get('skipped_count', counts.get('skipped', 0)),
                                        'out_of_scope': counts.get('out_of_scope_count', counts.get('out_of_scope', 0)),
                                        'failed': counts.get('failed_count', counts.get('failed', 0)),
                                        'created_assets': counts.get('created_assets', []),
                                        'updated_assets': counts.get('updated_assets', []),
                                        'skipped_assets': counts.get('skipped_assets', []),
                                        'failed_assets': counts.get('failed_assets', []),
                                        'errors': counts.get('errors', [])
                                    }
                            else:
                                # Check if this is a better response that should replace fallback data
                                current = detailed_counts[asset_type]

                                # If current has all zeros and this response has actual data, replace rather than accumulate
                                is_current_from_fallback = (current['total'] == 0 and current['created'] == 0 and
                                                           current['updated'] == 0 and current['skipped'] == 0)
                                has_actual_counts = (counts.get('total_count', counts.get('total', 0)) > 0 or
                                                   counts.get('created_count', counts.get('created', 0)) > 0 or
                                                   counts.get('updated_count', counts.get('updated', 0)) > 0 or
                                                   counts.get('skipped_count', counts.get('skipped', 0)) > 0)

                                if is_current_from_fallback and has_actual_counts:
                                    logger.debug(f"Replacing fallback data for {asset_type} with actual detailed counts")
                                    # Replace with actual data instead of accumulating
                                    if 'created_findings' in counts:
                                        # This is a findings response - replace with findings data
                                        detailed_counts[asset_type] = {
                                            'total': counts.get('total_count', 0),
                                            'created': counts.get('created_count', 0),
                                            'updated': counts.get('updated_count', 0),
                                            'skipped': counts.get('skipped_count', 0),
                                            'out_of_scope': 0,
                                            'failed': counts.get('failed_count', 0),
                                            'created_assets': counts.get('created_findings', []),
                                            'updated_assets': counts.get('updated_findings', []),
                                            'skipped_assets': counts.get('skipped_findings', []),
                                            'failed_assets': counts.get('failed_findings', []),
                                            'errors': counts.get('errors', [])
                                        }
                                    else:
                                        # This is an assets response - replace with assets data
                                        detailed_counts[asset_type] = {
                                            'total': counts.get('total_count', counts.get('total', 0)),
                                            'created': counts.get('created_count', counts.get('created', 0)),
                                            'updated': counts.get('updated_count', counts.get('updated', 0)),
                                            'skipped': counts.get('skipped_count', counts.get('skipped', 0)),
                                            'out_of_scope': counts.get('out_of_scope_count', counts.get('out_of_scope', 0)),
                                            'failed': counts.get('failed_count', counts.get('failed', 0)),
                                            'created_assets': counts.get('created_assets', []),
                                            'updated_assets': counts.get('updated_assets', []),
                                            'skipped_assets': counts.get('skipped_assets', []),
                                            'failed_assets': counts.get('failed_assets', []),
                                            'errors': counts.get('errors', [])
                                        }
                                else:
                                    # Normal accumulation for legitimate multiple responses
                                    current['total'] += counts.get('total_count', counts.get('total', 0))

                                # Handle both assets and findings formats for accumulation
                                if 'created_findings' in counts:
                                    # This is a findings response
                                    current['_temp_created_assets'] = current.get('_temp_created_assets', []) + counts.get('created_findings', [])
                                    current['_temp_updated_assets'] = current.get('_temp_updated_assets', []) + counts.get('updated_findings', [])
                                    current['_temp_skipped_assets'] = current.get('_temp_skipped_assets', []) + counts.get('skipped_findings', [])
                                    current['_temp_failed_assets'] = current.get('_temp_failed_assets', []) + counts.get('failed_findings', [])
                                else:
                                    # This is an assets response
                                    current['_temp_created_assets'] = current.get('_temp_created_assets', []) + counts.get('created_assets', [])
                                    current['_temp_updated_assets'] = current.get('_temp_updated_assets', []) + counts.get('updated_assets', [])
                                    current['_temp_skipped_assets'] = current.get('_temp_skipped_assets', []) + counts.get('skipped_assets', [])
                                    current['_temp_failed_assets'] = current.get('_temp_failed_assets', []) + counts.get('failed_assets', [])

                                current['errors'].extend(counts.get('errors', []))

                    # Fallback: Handle old format when detailed_counts is not available
                    elif ('asset_types' in summary and summary['asset_types']) or ('finding_types' in summary and summary['finding_types']):
                        # Handle both asset_types and finding_types fallbacks
                        fallback_types = {}
                        if 'asset_types' in summary and summary['asset_types']:
                            fallback_types.update(summary['asset_types'])
                            logger.debug(f"No detailed_counts in response, using asset_types fallback: {summary['asset_types']}")
                        if 'finding_types' in summary and summary['finding_types']:
                            fallback_types.update(summary['finding_types'])
                            logger.debug(f"No detailed_counts in response, using finding_types fallback: {summary['finding_types']}")

                        # Convert old format to detailed_counts format
                        # BUT ONLY if we don't already have detailed counts for this type
                        # This prevents overriding real data with fallback assumptions
                        for asset_type, total_count in fallback_types.items():
                            if total_count > 0:  # Only process types with actual counts
                                if asset_type not in detailed_counts:
                                    # Initialize with counts assuming all were created
                                    detailed_counts[asset_type] = {
                                        'total': total_count,
                                        'created': total_count,  # Assume all were created
                                        'updated': 0,
                                        'skipped': 0,
                                        'out_of_scope': 0,
                                        'failed': 0,
                                        'created_assets': [],  # We don't have individual asset details
                                        'updated_assets': [],
                                        'skipped_assets': [],
                                        'failed_assets': [],
                                        'errors': []
                                    }
                                # Don't add to existing counts from fallback - let detailed_counts override


        # Process all collected assets holistically to determine final actions
        #logger.debug(f"Detailed counts: {detailed_counts}")
        for asset_type, counts in detailed_counts.items():
            # Process all assets with precedence: created > updated > skipped > failed
            all_assets = {}

            # Collect all assets by name and determine the best action for each
            # Handle both single response (direct keys) and multiple responses (_temp_ keys)
            created_assets = counts.get('_temp_created_assets', counts.get('created_assets', []))
            updated_assets = counts.get('_temp_updated_assets', counts.get('updated_assets', []))
            skipped_assets = counts.get('_temp_skipped_assets', counts.get('skipped_assets', []))
            failed_assets = counts.get('_temp_failed_assets', counts.get('failed_assets', []))

            for asset in created_assets:
                # Handle both dictionary assets (from API) and object assets (from task execution)
                if isinstance(asset, dict):
                    asset_name = asset.get('name', str(asset))
                    # For nuclei findings, use record_id as unique key since multiple findings can have same URL
                    if asset_type == 'nuclei' and 'record_id' in asset:
                        asset_key = asset['record_id']
                    else:
                        asset_key = asset_name
                else:
                    asset_name = getattr(asset, 'name', str(asset))
                    # For nuclei findings, use record_id as unique key since multiple findings can have same URL
                    if asset_type == 'nuclei' and hasattr(asset, 'record_id'):
                        asset_key = getattr(asset, 'record_id')
                    else:
                        asset_key = asset_name
                if asset_key not in all_assets or all_assets[asset_key]['priority'] > 1:
                    all_assets[asset_key] = {'asset': asset, 'action': 'created', 'priority': 1}

            for asset in updated_assets:
                # Handle both dictionary assets (from API) and object assets (from task execution)
                if isinstance(asset, dict):
                    asset_name = asset.get('name', str(asset))
                    # logger.debug(f"UPDATED ASSET NAME: {asset_name}")
                    # logger.debug(f"UPDATED ASSET TYPE: {asset_type}")
                    # logger.debug(f"UPDATED ASSET: {asset}")
                    # For nuclei findings, use record_id as unique key since multiple findings can have same URL
                    if asset_type == 'nuclei' and 'record_id' in asset:
                        asset_key = asset['record_id']
                    else:
                        asset_key = asset_name
                else:
                    asset_name = getattr(asset, 'name', str(asset))
                    # For nuclei findings, use record_id as unique key since multiple findings can have same URL
                    if asset_type == 'nuclei' and hasattr(asset, 'record_id'):
                        asset_key = getattr(asset, 'record_id')
                    else:
                        asset_key = asset_name
                if asset_key not in all_assets or all_assets[asset_key]['priority'] > 2:
                    all_assets[asset_key] = {'asset': asset, 'action': 'updated', 'priority': 2}

            for asset in skipped_assets:
                # Handle both dictionary assets (from API) and object assets (from task execution)
                if isinstance(asset, dict):
                    asset_name = asset.get('name', str(asset))
                    # For nuclei findings, create unique key from constraint fields since skipped findings don't have record_id
                    if asset_type == 'nuclei':
                        # Use the same fields as the database constraint for uniqueness
                        url = asset.get('url', '')
                        template_id = asset.get('template_id', '')
                        matcher_name = asset.get('matcher_name', '')
                        matched_at = asset.get('matched_at', '')
                        program_name = asset.get('program_name', '')
                        asset_key = f"{url}|{template_id}|{matcher_name}|{matched_at}|{program_name}"
                    else:
                        asset_key = asset_name
                else:
                    asset_name = getattr(asset, 'name', str(asset))
                    # For nuclei findings, create unique key from constraint fields since skipped findings don't have record_id
                    if asset_type == 'nuclei':
                        # Use the same fields as the database constraint for uniqueness
                        url = getattr(asset, 'url', '')
                        template_id = getattr(asset, 'template_id', '')
                        matcher_name = getattr(asset, 'matcher_name', '')
                        matched_at = getattr(asset, 'matched_at', '')
                        program_name = getattr(asset, 'program_name', '')
                        asset_key = f"{url}|{template_id}|{matcher_name}|{matched_at}|{program_name}"
                    else:
                        asset_key = asset_name
                if asset_key not in all_assets or all_assets[asset_key]['priority'] > 3:
                    all_assets[asset_key] = {'asset': asset, 'action': 'skipped', 'priority': 3}

            for asset in failed_assets:
                # Handle both dictionary assets (from API) and object assets (from task execution)
                if isinstance(asset, dict):
                    asset_name = asset.get('name', str(asset))
                    # For nuclei findings, create unique key from constraint fields since failed findings don't have record_id
                    if asset_type == 'nuclei':
                        # Use the same fields as the database constraint for uniqueness
                        url = asset.get('url', '')
                        template_id = asset.get('template_id', '')
                        matcher_name = asset.get('matcher_name', '')
                        matched_at = asset.get('matched_at', '')
                        program_name = asset.get('program_name', '')
                        asset_key = f"{url}|{template_id}|{matcher_name}|{matched_at}|{program_name}"
                    else:
                        asset_key = asset_name
                else:
                    asset_name = getattr(asset, 'name', str(asset))
                    # For nuclei findings, create unique key from constraint fields since failed findings don't have record_id
                    if asset_type == 'nuclei':
                        # Use the same fields as the database constraint for uniqueness
                        url = getattr(asset, 'url', '')
                        template_id = getattr(asset, 'template_id', '')
                        matcher_name = getattr(asset, 'matcher_name', '')
                        matched_at = getattr(asset, 'matched_at', '')
                        program_name = getattr(asset, 'program_name', '')
                        asset_key = f"{url}|{template_id}|{matcher_name}|{matched_at}|{program_name}"
                    else:
                        asset_key = asset_name
                if asset_key not in all_assets or all_assets[asset_key]['priority'] > 4:
                    all_assets[asset_key] = {'asset': asset, 'action': 'failed', 'priority': 4}

            # Separate assets by final action
            counts['created_assets'] = [item['asset'] for item in all_assets.values() if item['action'] == 'created']
            counts['updated_assets'] = [item['asset'] for item in all_assets.values() if item['action'] == 'updated']
            counts['skipped_assets'] = [item['asset'] for item in all_assets.values() if item['action'] == 'skipped']
            counts['failed_assets'] = [item['asset'] for item in all_assets.values() if item['action'] == 'failed']

            # Calculate final counts
            counts['created'] = len(counts['created_assets'])
            counts['updated'] = len(counts['updated_assets'])
            counts['skipped'] = len(counts['skipped_assets'])
            counts['failed'] = len(counts['failed_assets'])
            counts['total'] = counts['created'] + counts['updated'] + counts['skipped'] + counts['failed']
            
            # Clean up temporary data (only remove temp keys if they exist)
            temp_keys = ['_temp_created_assets', '_temp_updated_assets', '_temp_skipped_assets', '_temp_failed_assets']
            for key in temp_keys:
                if key in counts:
                    counts.pop(key, None)


        # Calculate total_assets and total_findings - prefer actual step outputs if available, but use API response details
        # For the final workflow status, adjust the counts to reflect the deduplicated reality
        if actual_step_outputs and any(isinstance(assets, list) and assets for assets in actual_step_outputs.values()):
            # Separate assets from findings
            total_assets = 0
            total_findings = 0
            
            for asset_type, assets in actual_step_outputs.items():
                if isinstance(assets, list):
                    asset_type_str = asset_type.value if hasattr(asset_type, 'value') else str(asset_type)
                    if asset_type_str == 'nuclei':
                        # Don't count nuclei findings here - we'll use API response data for consistency
                        pass
                    else:
                        total_assets += len(assets)

            # Create asset_types combining actual totals with API response details
            actual_asset_types = {}
            api_created = 0
            api_updated = 0
            api_skipped = 0
            api_out_of_scope = 0
            api_failed = 0

            for asset_type, assets in actual_step_outputs.items():
                if isinstance(assets, list):
                    asset_type_str = asset_type.value if hasattr(asset_type, 'value') else str(asset_type)

                    # Get the actual count from deduplicated assets
                    actual_count = len(assets)

                    # Get the final counts from the aggregated (and possibly modified) detailed_counts
                    if asset_type_str in detailed_counts:
                        api_counts = detailed_counts[asset_type_str]

                        # Use API counts as-is - they should be correct for all steps
                        # The "updated" operations in step 2 are legitimate since assets exist from step 1
                        final_created = api_counts.get('created', 0)
                        final_updated = api_counts.get('updated', 0)
                        final_skipped = api_counts.get('skipped', 0)

                        actual_asset_types[asset_type_str] = {
                            'total': api_counts.get('total', 0),  # Use API processed total
                            'created': final_created,
                            'updated': final_updated,
                            'skipped': final_skipped,
                            'out_of_scope': api_counts.get('out_of_scope', 0),
                            'failed': api_counts.get('failed', 0),
                            'created_assets': api_counts.get('created_assets', []),
                            'updated_assets': api_counts.get('updated_assets', []),
                            'skipped_assets': api_counts.get('skipped_assets', []),
                            'failed_assets': api_counts.get('failed_assets', []),
                            'errors': api_counts.get('errors', [])
                        }
                        api_created += final_created
                        api_updated += final_updated
                        api_skipped += final_skipped
                        api_out_of_scope += api_counts.get('out_of_scope', 0)
                        api_failed += api_counts.get('failed', 0)
                    else:
                        # No API details available, use actual count as total
                        actual_asset_types[asset_type_str] = {
                            'total': actual_count,
                            'created': 0,
                            'updated': 0,
                            'skipped': actual_count,
                            'out_of_scope': 0,
                            'failed': 0,
                            'created_assets': [],
                            'updated_assets': [],
                            'skipped_assets': [],
                            'failed_assets': [],
                            'errors': []
                        }
                        api_skipped += actual_count

            # Separate assets from findings in the result
            asset_types = {}
            finding_types = {}
            
            for asset_type, counts in actual_asset_types.items():
                if asset_type == 'nuclei':
                    finding_types[asset_type] = counts
                else:
                    asset_types[asset_type] = counts

            # Calculate totals for assets and findings separately
            total_created_assets = sum(counts.get('created', 0) for counts in asset_types.values())
            total_updated_assets = sum(counts.get('updated', 0) for counts in asset_types.values())
            total_skipped_assets = sum(counts.get('skipped', 0) for counts in asset_types.values())
            total_failed_assets = sum(counts.get('failed', 0) for counts in asset_types.values())
            
            total_created_findings = sum(counts.get('created', 0) for counts in finding_types.values())
            total_updated_findings = sum(counts.get('updated', 0) for counts in finding_types.values())
            total_skipped_findings = sum(counts.get('skipped', 0) for counts in finding_types.values())
            total_failed_findings = sum(counts.get('failed', 0) for counts in finding_types.values())
            
            # Calculate total_findings from API response data for consistency
            total_findings = sum(counts.get('total', 0) for counts in finding_types.values())

            # Use processed detailed_counts for consistent summary
            result = {
                "total_assets": total_assets,
                "created_assets": total_created_assets,
                "updated_assets": total_updated_assets,
                "skipped_assets": total_skipped_assets,
                "out_of_scope_assets": 0,  # Not used in current implementation
                "failed_assets": total_failed_assets,
                "asset_types": asset_types,
                "total_findings": total_findings,
                "created_findings": total_created_findings,
                "updated_findings": total_updated_findings,
                "skipped_findings": total_skipped_findings,
                "failed_findings": total_failed_findings,
                "finding_types": finding_types
            }
        else:
            # Fallback to API response counts only - separate assets from findings
            asset_types = {}
            finding_types = {}
            total_assets = 0
            total_findings = 0
            
            for asset_type, counts in detailed_counts.items():
                if asset_type == 'nuclei':
                    finding_types[asset_type] = counts
                    total_findings += counts.get('total', 0)
                else:
                    asset_types[asset_type] = counts
                    total_assets += counts.get('total', 0)

            result = {
                "total_assets": total_assets,
                "created_assets": sum(counts.get('created', 0) for counts in asset_types.values()),
                "updated_assets": sum(counts.get('updated', 0) for counts in asset_types.values()),
                "skipped_assets": sum(counts.get('skipped', 0) for counts in asset_types.values()),
                "out_of_scope_assets": sum(counts.get('out_of_scope', 0) for counts in asset_types.values()),
                "failed_assets": sum(counts.get('failed', 0) for counts in asset_types.values()),
                "asset_types": asset_types,
                "total_findings": total_findings,
                "created_findings": sum(counts.get('created', 0) for counts in finding_types.values()),
                "updated_findings": sum(counts.get('updated', 0) for counts in finding_types.values()),
                "skipped_findings": sum(counts.get('skipped', 0) for counts in finding_types.values()),
                "out_of_scope_findings": sum(counts.get('out_of_scope', 0) for counts in finding_types.values()),
                "failed_findings": sum(counts.get('failed', 0) for counts in finding_types.values()),
                "finding_types": finding_types
            }

        # Always add timing information if available (even for steps with no input)
        if 'started_at' in timing_info:
            result['started_at'] = timing_info['started_at']
        if 'completed_at' in timing_info:
            result['completed_at'] = timing_info['completed_at']

        # Always return result with timing information if available
        if not result:
            # Create a minimal result if none was created
            result = {
                "total_assets": 0,
                "created_assets": 0,
                "updated_assets": 0,
                "skipped_assets": 0,
                "out_of_scope_assets": 0,
                "failed_assets": 0,
                "asset_types": {},
                "total_findings": 0,
                "created_findings": 0,
                "updated_findings": 0,
                "skipped_findings": 0,
                "out_of_scope_findings": 0,
                "failed_findings": 0,
                "finding_types": {}
            }

        return result

    def _deduplicate_assets(self, assets: Dict) -> Dict:
        """Deduplicate assets based on their unique identifiers"""
        if not assets:
            return assets

        deduplicated = {}

        for asset_type, asset_list in assets.items():
            if not asset_list:
                continue

            # Get unique identifier function for this asset type
            unique_key_func = self._get_unique_key_function(asset_type)

            if unique_key_func:
                # Deduplicate using the unique key function
                seen = set()
                unique_assets = []

                for asset in asset_list:
                    try:
                        key = unique_key_func(asset)
                        if key not in seen:
                            seen.add(key)
                            unique_assets.append(asset)
                    except Exception as e:
                        logger.warning(f"Error getting unique key for asset {asset}: {e}")
                        # Include asset anyway if we can't deduplicate it
                        unique_assets.append(asset)

                deduplicated[asset_type] = unique_assets
                logger.debug(f"Deduplicated {asset_type}: {len(asset_list)} -> {len(unique_assets)} unique assets")
            else:
                # No deduplication function available, keep as-is
                deduplicated[asset_type] = asset_list
                logger.debug(f"No deduplication available for {asset_type}, keeping {len(asset_list)} assets")

        return deduplicated

    def _get_unique_key_function(self, asset_type):
        """Get the function to extract unique key for an asset type"""
        # Handle both AssetType enum and string keys
        asset_type_str = asset_type.value if hasattr(asset_type, 'value') else str(asset_type)

        if asset_type_str == 'subdomain':
            return lambda asset: getattr(asset, 'name', str(asset))
        elif asset_type_str == 'ip':
            return lambda asset: getattr(asset, 'ip', str(asset))
        elif asset_type_str == 'url':
            return lambda asset: getattr(asset, 'url', str(asset))
        elif asset_type_str == 'service':
            return lambda asset: f"{getattr(asset, 'ip', '')}:{getattr(asset, 'port', '')}"
        elif asset_type_str == 'certificate':
            return lambda asset: getattr(asset, 'domain', str(asset))
        elif asset_type_str == 'nuclei':
            return lambda asset: getattr(asset, 'url', str(asset))
        elif asset_type_str == 'apex_domain':
            return lambda asset: (
                asset.get('name', str(asset)) if isinstance(asset, dict) else getattr(asset, 'name', str(asset))
            )
        else:
            # For unknown types, try to find a common unique field or use string representation
            return lambda asset: str(asset)

    def _check_asset_coordination_used(self, step_name: str) -> bool:
        """Check if asset coordination has already handled assets for this step"""
        if not self.execution_manager:
            logger.debug(f"No execution_manager available for step {step_name}")
            return False

        # Check if this step used asset coordination
        has_been_processed = self.execution_manager.was_asset_coordination_used(step_name)

        # Check for existing jobs in progressive streamer
        job_count = 0
        if hasattr(self.execution_manager, 'progressive_streamer') and self.execution_manager.progressive_streamer:
            job_count = len(self.execution_manager.progressive_streamer.step_jobs.get(step_name, []))

        has_jobs = job_count > 0
        result = has_been_processed or has_jobs
        logger.debug(f"Asset coordination check for step {step_name}: has_been_processed={has_been_processed}, job_count={job_count}, result={result}")
        return result



