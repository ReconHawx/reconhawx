#!/usr/bin/env python3
import sys
import json
import os
from typing import Dict, Any, List, Optional, Tuple

from runner_logging import configure_runner_logging

configure_runner_logging()

import logging
from kubernetes import client, config
import asyncio
import requests
import signal
from datetime import datetime

# Import our task system
from models.base import utcnow
from models.workflow import Workflow
from task_executor import TaskExecutor
from recon_tasks.base import parameter_manager
from data_api_client import DataAPIClient
from services.kubernetes import KubernetesService
from workflow_definition_snapshot import serialize_workflow_definition_snapshot

logger = logging.getLogger(__name__)

# Global flag to track if workflow was stopped externally
workflow_stopped_externally = False

def signal_handler(signum, frame):
    """Handle termination signals gracefully"""
    global workflow_stopped_externally
    logger.info(f"Received signal {signum}, marking workflow as externally stopped")
    workflow_stopped_externally = True

# Set up signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def get_current_workflow_status(workflow_id):
    """Check the current status of the workflow from the API"""
    try:
        headers = {}
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
        if internal_api_key:
            headers['Authorization'] = f'Bearer {internal_api_key}'
            logger.debug(f"Using internal API key for workflow status check (key length: {len(internal_api_key)})")
        else:
            logger.warning("No internal API key found for workflow status check")
        
        logger.debug(f"Making workflow status API request to: {os.getenv('API_URL')}/workflows/executions/{workflow_id}/logs")
        logger.debug(f"Request headers: {headers}")
        
        response = requests.get(
            f"{os.getenv('API_URL')}/workflows/executions/{workflow_id}/logs",
            headers=headers
        )
        
        logger.debug(f"Workflow status API response status: {response.status_code}")
        if response.status_code != 200:
            logger.debug(f"Workflow status API response text: {response.text[:200]}...")
        if response.status_code == 200:
            data = response.json()
            return data.get('result', 'unknown')
    except Exception as e:
        logger.warning(f"Failed to get current workflow status: {e}")
    return None

def get_k8s_client():
    """Create and return Kubernetes API client"""
    try:
        # Try to load in-cluster config first
        config.load_incluster_config()
    except config.ConfigException:
        # Fall back to local kubeconfig
        config.load_kube_config()

    # Test the connection
    try:
        api = client.BatchV1Api()
        api.get_api_resources()
        return api
    except Exception as e:
        logger.error(f"Failed to connect to Kubernetes API: {e}")
        raise

def _deduplicate_combined_outputs(combined_outputs):
    """Deduplicate assets in combined step outputs"""
    if not combined_outputs:
        return combined_outputs

    deduplicated = {}

    for asset_type, asset_list in combined_outputs.items():
        if not asset_list:
            continue

        # Get unique identifier function for this asset type
        unique_key_func = _get_unique_key_function(asset_type)

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
            logger.debug(f"Step deduplication for {asset_type}: {len(asset_list)} -> {len(unique_assets)} unique assets")
        else:
            # No deduplication function available, keep as-is
            deduplicated[asset_type] = asset_list

    return deduplicated

def _get_unique_key_function(asset_type):
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
    else:
        # For unknown types, try to find a common unique field or use string representation
        return lambda asset: str(asset)

def _log_step_outputs(step_name: str, step_outputs: Dict[str, Any]):
    """Log enhanced information about step outputs"""
    try:
        if step_name not in step_outputs:
            logger.info(f"Step '{step_name}' completed with no outputs")
            return

        step_data = step_outputs[step_name]
        if not step_data:
            logger.info(f"Step '{step_name}' completed with empty outputs")
            return

        # Separate assets from findings
        asset_counts = {}
        finding_counts = {}
        total_assets = 0
        total_findings = 0

        for asset_type, assets in step_data.items():
            if isinstance(assets, list):
                count = len(assets)
                if asset_type == 'nuclei':
                    # Nuclei findings are categorized as findings, not assets
                    finding_counts[str(asset_type)] = count
                    total_findings += count
                else:
                    # All other types are assets
                    asset_counts[str(asset_type)] = count
                    total_assets += count

        # Log assets and findings separately
        if total_assets > 0:
            logger.info(f"📦 Step '{step_name}' outputs: {total_assets} total assets")
            for asset_type, count in asset_counts.items():
                if count > 0:
                    logger.info(f"   • {asset_type}: {count} assets")
        
        if total_findings > 0:
            logger.info(f"🔍 Step '{step_name}' findings: {total_findings} total findings")
            for finding_type, count in finding_counts.items():
                if count > 0:
                    logger.info(f"   • {finding_type}: {count} findings")

        # Show examples for both assets and findings
        for asset_type, count in asset_counts.items():
            if count > 0:
                assets = step_data.get(asset_type, [])
                if assets and len(assets) > 0:
                    for i, asset in enumerate(assets[:3]):
                        if isinstance(asset, dict):
                            # Try to get a meaningful name
                            asset_name = asset.get('name') or asset.get('domain') or asset.get('ip') or asset.get('url')
                            # Handle service assets specifically
                            if not asset_name and asset.get('ip') and asset.get('port'):
                                service_name = asset.get('service_name', '')
                                if service_name:
                                    asset_name = f"{asset['ip']}:{asset['port']} ({service_name})"
                                else:
                                    asset_name = f"{asset['ip']}:{asset['port']}"
                            if not asset_name:
                                asset_name = str(asset)
                        elif hasattr(asset, 'name'):
                            asset_name = asset.name
                        elif hasattr(asset, 'domain'):
                            asset_name = asset.domain
                        elif hasattr(asset, 'ip') and hasattr(asset, 'port'):
                            # Handle Service model objects
                            service_name = getattr(asset, 'service_name', '')
                            if service_name:
                                asset_name = f"{asset.ip}:{asset.port} ({service_name})"
                            else:
                                asset_name = f"{asset.ip}:{asset.port}"
                        elif hasattr(asset, 'ip'):
                            asset_name = asset.ip
                        elif hasattr(asset, 'url'):
                            asset_name = asset.url
                        else:
                            asset_name = str(asset)

        # Show examples for findings
        for finding_type, count in finding_counts.items():
            if count > 0:
                findings = step_data.get(finding_type, [])
                if findings and len(findings) > 0:
                    examples = []
                    for i, finding in enumerate(findings[:3]):
                        if isinstance(finding, dict):
                            # For nuclei findings, try to get template name or URL
                            finding_name = finding.get('template_id') or finding.get('name') or finding.get('url')
                            if not finding_name:
                                finding_name = str(finding)
                        elif hasattr(finding, 'template_id'):
                            finding_name = finding.template_id
                        elif hasattr(finding, 'name'):
                            finding_name = finding.name
                        elif hasattr(finding, 'url'):
                            finding_name = finding.url
                        else:
                            finding_name = str(finding)

                        examples.append(finding_name)

                    if examples:
                        logger.info(f"     Examples: {', '.join(examples)}")
                        if len(findings) > 3:
                            logger.info(f"     ... and {len(findings) - 3} more")

    except Exception as e:
        logger.warning(f"Error logging step outputs for '{step_name}': {e}")


def _log_concise_asset_summary(step_name: str, step_status_data: Dict[str, Any]):
    """Log concise asset processing summary"""
    try:
        if not step_status_data or 'asset_types' not in step_status_data:
            return

        asset_types = step_status_data['asset_types']
        # Calculate totals
        asset_totals = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
        finding_totals = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

        for asset_type, counts in asset_types.items():
            if isinstance(counts, dict):
                if asset_type == 'nuclei':
                    for key in finding_totals.keys():
                        finding_totals[key] += counts.get(key, 0)
                else:
                    for key in asset_totals.keys():
                        asset_totals[key] += counts.get(key, 0)

        # Log concise summary only if there are assets/findings
        total_assets = sum(asset_totals.values())
        total_findings = sum(finding_totals.values())
        
        if total_assets > 0:
            logger.info(f"📊 {total_assets} assets: {asset_totals['created']} created, {asset_totals['updated']} updated, {asset_totals['skipped']} skipped, {asset_totals['failed']} failed")
        
        if total_findings > 0:
            logger.info(f"🔍 {total_findings} findings: {finding_totals['created']} created, {finding_totals['updated']} updated, {finding_totals['skipped']} skipped, {finding_totals['failed']} failed")

    except Exception as e:
        logger.error(f"Error logging summary for step {step_name}: {e}")


def _capture_pod_output(execution_id: str, step_name: Optional[str] = None) -> str:
    """Capture runner pod output/logs via Kubernetes API"""
    try:
        k8s_service = KubernetesService()
        logs = k8s_service.get_runner_pod_logs_by_execution_id(execution_id)
        
        if logs:
            if step_name:
                return f"\n--- Step: {step_name} ---\n{logs}\n\n--- End Step ---\n"
            return logs
        return ""
    except Exception as e:
        logger.warning(f"Failed to capture pod output for execution {execution_id}: {e}")
        return ""


def _waf_step_fully_blocked(ws: Dict[str, Any]) -> bool:
    """True when WAF precheck dropped all targets for this step's heavy HTTP task."""
    if not isinstance(ws, dict):
        return False
    if ws.get("skipped") == "waf_all_nodes_blocked":
        return True
    dk = ws.get("distinct_target_keys") or 0
    bloc = ws.get("blocked_all_nodes_keys") or []
    if dk > 0 and isinstance(bloc, list) and len(bloc) >= dk:
        return True
    return False


def _aggregate_waf_summary(step_waf_status: Optional[Dict[str, Dict[str, Any]]]) -> Tuple[Dict[str, Any], bool]:
    """
    Aggregate per-step `_step_waf_status` into a workflow-level summary for the API.

    Returns (summary_dict, any_skips). When ``any_skips`` is False, callers should omit ``waf_summary`` from payloads.
    """
    if not step_waf_status:
        return {}, False

    fully_skipped: List[str] = []
    partial_rows: List[Dict[str, Any]] = []
    total_skipped = 0

    blocked_seen: Dict[str, None] = {}
    cand_seen: Dict[str, None] = {}

    for step_name, raw in sorted(step_waf_status.items()):
        if not isinstance(raw, dict):
            continue
        skipped_in = int(raw.get("skipped_inputs") or 0)
        bloc = raw.get("blocked_all_nodes_keys")
        if isinstance(bloc, list):
            for k in bloc:
                if isinstance(k, str) and k not in blocked_seen:
                    blocked_seen[k] = None
        cands = raw.get("candidate_nodes")
        if isinstance(cands, list):
            for n in cands:
                if isinstance(n, str) and n not in cand_seen:
                    cand_seen[n] = None

        if skipped_in <= 0:
            continue

        total_skipped += skipped_in
        if _waf_step_fully_blocked(raw):
            fully_skipped.append(step_name)
        else:
            blocked_list = [str(x) for x in bloc] if isinstance(bloc, list) else []
            cand_list = [str(x) for x in cands] if isinstance(cands, list) else []
            partial_rows.append(
                {
                    "step": step_name,
                    "skipped_inputs": skipped_in,
                    "blocked_all_nodes_keys": blocked_list,
                    "candidate_nodes": cand_list,
                }
            )

    union_blocked = sorted(blocked_seen.keys())
    cand_union = sorted(cand_seen.keys())

    any_skips = bool(fully_skipped or partial_rows)
    if not any_skips:
        return {}, False

    summary = {
        "any_skips": True,
        "fully_skipped_steps": fully_skipped,
        "partial_skip_steps": partial_rows,
        "total_skipped_inputs": total_skipped,
        "total_blocked_target_keys": len(union_blocked),
        "candidate_nodes_union": cand_union,
    }
    return summary, True


def _derive_workflow_result(base_result: str, waf_summary: Optional[Dict[str, Any]]) -> str:
    """
    Refine terminal ``result`` when the workflow succeeded but WAF precheck skipped work.

    - ``success`` + any fully-skipped heavy step → ``cancelled_waf``
    - ``success`` + only partial skips → ``partial_waf``
    """
    low = (base_result or "").lower()
    if low != "success" or not waf_summary:
        return base_result

    fs = waf_summary.get("fully_skipped_steps") or []
    partial = waf_summary.get("partial_skip_steps") or []

    if fs:
        return "cancelled_waf"
    if partial:
        return "partial_waf"
    return base_result


def _apply_waf_to_workflow_outputs(
    workflow_outputs: Dict[str, Any],
    task_executor: Optional[Any],
) -> None:
    """Attach ``waf_summary`` and adjust ``result`` in place when WAF skips occurred."""
    if not workflow_outputs:
        return
    step_ws = getattr(task_executor, "_step_waf_status", None) if task_executor else None
    summary, any_skips = _aggregate_waf_summary(step_ws if isinstance(step_ws, dict) else None)
    if any_skips:
        workflow_outputs["waf_summary"] = summary
    else:
        workflow_outputs.pop("waf_summary", None)

    workflow_outputs["result"] = _derive_workflow_result(
        str(workflow_outputs.get("result") or ""),
        workflow_outputs.get("waf_summary"),
    )


def _serialize_input_data(input_data: Any) -> Any:
    """Serialize input data to JSON-serializable format"""
    if input_data is None:
        return None
    
    if isinstance(input_data, list):
        # Serialize each item in the list
        serialized = []
        for item in input_data:
            if isinstance(item, str):
                serialized.append(item)
            elif isinstance(item, (int, float, bool)):
                serialized.append(item)
            elif isinstance(item, dict):
                serialized.append(item)
            elif hasattr(item, '__dict__'):
                # Object with attributes - convert to dict
                serialized.append({k: v for k, v in vars(item).items() if not k.startswith('_')})
            else:
                # Fallback: convert to string
                serialized.append(str(item))
        return serialized
    
    elif isinstance(input_data, str):
        return input_data
    
    elif isinstance(input_data, (int, float, bool)):
        return input_data
    
    elif isinstance(input_data, dict):
        return input_data
    
    elif hasattr(input_data, '__dict__'):
        # Object with attributes - convert to dict
        return {k: v for k, v in vars(input_data).items() if not k.startswith('_')}
    
    else:
        # Fallback: convert to string
        return str(input_data)


async def _log_task_execution(
    execution_id: str,
    program_id: str,
    program_name: Optional[str],
    step_name: str,
    task_def,
    task_start_time: datetime,
    task_end_time: datetime,
    executed_input_data: Any,
    output: Dict[Any, List[Any]],
    status: str,
    error: Optional[str] = None
) -> None:
    """Log task execution details to the API"""
    try:
        # Calculate output counts
        output_count = sum(len(assets) for assets in output.values())
        output_asset_types = {}
        for asset_type, assets in output.items():
            asset_type_str = asset_type.value if hasattr(asset_type, 'value') else str(asset_type)
            output_asset_types[asset_type_str] = len(assets)
        
        # Get task type
        task_type = getattr(task_def, 'task_type', None) or task_def.name
        
        # Get task parameters
        params = getattr(task_def, 'params', {}) or {}
        
        # Calculate duration
        duration_seconds = (task_end_time - task_start_time).total_seconds()
        
        serialized_executed = _serialize_input_data(executed_input_data)
        if isinstance(executed_input_data, list):
            input_count = len(executed_input_data)
        elif executed_input_data is None:
            input_count = 0
        else:
            input_count = 1
        
        # Create task execution log entry
        task_log_entry = {
            "step_name": step_name,
            "task_name": task_def.name,
            "task_type": task_type,
            "params": params,
            "input_count": input_count,
            "input_data": serialized_executed,
            "executed_input_data": serialized_executed,
            "output_count": output_count,
            "output_asset_types": output_asset_types,
            "started_at": task_start_time.isoformat() + 'Z',
            "completed_at": task_end_time.isoformat() + 'Z',
            "duration_seconds": duration_seconds,
            "status": status,
            "error": error
        }
        
        # Send log entry to API
        headers = {}
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
        if internal_api_key:
            headers['Authorization'] = f'Bearer {internal_api_key}'
        
        log_object = {
            "execution_id": execution_id,
            "program_id": program_id,
            "task_execution_logs": [task_log_entry],
        }
        if program_name:
            log_object["program_name"] = program_name
        
        requests.post(
            f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs",
            json=log_object,
            headers=headers
        )
        
    except Exception as e:
        logger.warning(f"Failed to log task execution for {task_def.name}: {e}")
        # Don't fail workflow if logging fails


async def run_step(task_executor, program_id: str, program_name, workflow_id, step_num, step, step_outputs):
    """Run all tasks in a step concurrently and coordinate with asset processing"""
    execution_id = os.getenv('EXECUTION_ID')
    
    # Execute all tasks concurrently with per-task logging
    task_futures = []
    task_metadata = []  # Track task metadata for logging
    
    # Set program context early so execute_task can resolve inputs and ingest assets
    task_executor.program_id = program_id
    task_executor.program_name = program_name
    
    for task_def in step.tasks:
        task_start_time = utcnow()
        task_metadata.append({
            'task_def': task_def,
            'start_time': task_start_time,
        })
        
        def create_task_wrapper(td, start_time):
            async def execute_task_with_logging():
                try:
                    output = await task_executor.execute_task(step_num, step.name, td, program_name)
                    return output, None, 'success'
                except Exception as e:
                    return {}, str(e), 'failed'
            return execute_task_with_logging
        
        task_future = create_task_wrapper(task_def, task_start_time)()
        task_futures.append(task_future)
    
    try:
        # Wait for all tasks to complete - no timeout at step level
        results = await asyncio.gather(*task_futures, return_exceptions=True)
        # Track successful and failed tasks
        successful_outputs = []
        failed_tasks = []
        
        # Process each output and log task execution
        for i, result in enumerate(results):
            task_meta = task_metadata[i]
            task_def = task_meta['task_def']
            task_start_time = task_meta['start_time']
            executed_input = task_executor.get_task_executed_input(step.name, task_def.name)
            task_end_time = utcnow()

            def _resolve_log_status(base_status: str) -> str:
                if base_status == 'success' and not executed_input:
                    return 'skipped'
                return base_status
            
            if isinstance(result, Exception):
                logger.error(f"Task {i+1} in step {step.name} failed with error: {result}")
                failed_tasks.append(i + 1)
                # Log failed task execution
                if execution_id:
                    await _log_task_execution(
                        execution_id,
                        program_id,
                        program_name,
                        step.name,
                        task_def,
                        task_start_time,
                        task_end_time,
                        executed_input,
                        {},
                        'failed',
                        str(result)
                    )
            elif isinstance(result, tuple):
                output, error, status = result
                if error:
                    logger.error(f"Task {task_def.name} in step {step.name} failed: {error}")
                    failed_tasks.append(i + 1)
                    if execution_id:
                        await _log_task_execution(
                            execution_id,
                            program_id,
                            program_name,
                            step.name,
                            task_def,
                            task_start_time,
                            task_end_time,
                            executed_input,
                            {},
                            'failed',
                            error,
                        )
                elif isinstance(output, str):
                    # If output is a string (task ID), treat it as a successful output with no assets
                    logger.debug(f"Task {task_def.name} in step {step.name} completed successfully with no assets")
                    successful_outputs.append({})
                    if execution_id:
                        await _log_task_execution(
                            execution_id,
                            program_id,
                            program_name,
                            step.name,
                            task_def,
                            task_start_time,
                            task_end_time,
                            executed_input,
                            {},
                            _resolve_log_status('success'),
                        )
                else:
                    successful_outputs.append(output)
                    if execution_id:
                        await _log_task_execution(
                            execution_id,
                            program_id,
                            program_name,
                            step.name,
                            task_def,
                            task_start_time,
                            task_end_time,
                            executed_input,
                            output,
                            _resolve_log_status('success'),
                        )
            else:
                # Handle unexpected result format
                logger.warning(f"Unexpected result format for task {task_def.name}: {type(result)}")
                successful_outputs.append({})
                if execution_id:
                    await _log_task_execution(
                        execution_id,
                        program_id,
                        program_name,
                        step.name,
                        task_def,
                        task_start_time,
                        task_end_time,
                        executed_input,
                        {},
                        _resolve_log_status('success'),
                    )
        # Log summary of task execution only if there are failures
        if failed_tasks:
            logger.warning(f"Step {step.name} completed with {len(failed_tasks)} failed tasks: {failed_tasks}")
        
        # Wait for asset processing to complete for step coordination
        logger.debug(f"Waiting for asset processing to complete for step {step.name}")
        try:
            await task_executor.execution_manager.wait_for_step_completion(step.name)
            logger.debug(f"Asset processing completed for step {step.name}")
        except Exception as e:
            logger.error(f"Asset processing failed for step {step.name}: {e}")
            raise Exception(f"Asset processing failed for step {step.name}: {e}")
        
        # Combine successful outputs
        combined_outputs = {}
        for output in successful_outputs:
            if not output:  # Skip empty outputs
                continue

            # Handle the new output format where assets are at the top level
            if hasattr(output, 'items'):  # It's a dict-like object
                for key, value in output.items():
                    # Check if this is an AssetType key with a list of assets
                    if hasattr(key, 'value') and isinstance(value, list):
                        # This is an AssetType enum key with assets
                        asset_type = key.value  # Get the string value of the enum
                        if asset_type not in combined_outputs:
                            combined_outputs[asset_type] = []

                        # Deduplicate when extending
                        for asset in value:
                            if asset_type == 'subdomain':
                                asset_name = getattr(asset, 'name', str(asset))
                                if not any(getattr(existing, 'name', str(existing)) == asset_name for existing in combined_outputs[asset_type]):
                                    combined_outputs[asset_type].append(asset)
                            elif asset_type == 'ip':
                                asset_ip = getattr(asset, 'ip_address', str(asset))
                                if not any(getattr(existing, 'ip_address', str(existing)) == asset_ip for existing in combined_outputs[asset_type]):
                                    combined_outputs[asset_type].append(asset)
                            elif asset_type == 'url':
                                asset_url = getattr(asset, 'url', str(asset))
                                if not any(getattr(existing, 'url', str(existing)) == asset_url for existing in combined_outputs[asset_type]):
                                    combined_outputs[asset_type].append(asset)
                            else:
                                # For other asset types, use string representation
                                asset_str = str(asset)
                                if asset_str not in [str(existing) for existing in combined_outputs[asset_type]]:
                                    combined_outputs[asset_type].append(asset)
                       # logger.info(f"Added {len(value)} assets of type {asset_type}")
                    elif isinstance(key, str) and isinstance(value, list):
                        # This is a string key with assets
                        if key not in combined_outputs:
                            combined_outputs[key] = []

                        # Deduplicate when extending (use string key as asset type)
                        for asset in value:
                            if key == 'subdomain':
                                asset_name = getattr(asset, 'name', str(asset))
                                if not any(getattr(existing, 'name', str(existing)) == asset_name for existing in combined_outputs[key]):
                                    combined_outputs[key].append(asset)
                            elif key == 'ip':
                                asset_ip = getattr(asset, 'ip_address', str(asset))
                                if not any(getattr(existing, 'ip_address', str(existing)) == asset_ip for existing in combined_outputs[key]):
                                    combined_outputs[key].append(asset)
                            elif key == 'url':
                                asset_url = getattr(asset, 'url', str(asset))
                                if not any(getattr(existing, 'url', str(existing)) == asset_url for existing in combined_outputs[key]):
                                    combined_outputs[key].append(asset)
                            else:
                                # For other asset types, use string representation
                                asset_str = str(asset)
                                if asset_str not in [str(existing) for existing in combined_outputs[key]]:
                                    combined_outputs[key].append(asset)
                        #logger.info(f"Added {len(value)} assets of type {key}")
                    else:
                        # Legacy format: nested task structure
                        if isinstance(value, dict) and 'assets' in value:
                            for asset_type, assets in value['assets'].items():
                                if asset_type not in combined_outputs:
                                    combined_outputs[asset_type] = []

                                # Deduplicate when extending (legacy format)
                                for asset in assets:
                                    if asset_type == 'subdomain':
                                        asset_name = getattr(asset, 'name', str(asset))
                                        if not any(getattr(existing, 'name', str(existing)) == asset_name for existing in combined_outputs[asset_type]):
                                            combined_outputs[asset_type].append(asset)
                                    elif asset_type == 'ip':
                                        asset_ip = getattr(asset, 'ip_address', str(asset))
                                        if not any(getattr(existing, 'ip_address', str(existing)) == asset_ip for existing in combined_outputs[asset_type]):
                                            combined_outputs[asset_type].append(asset)
                                    elif asset_type == 'url':
                                        asset_url = getattr(asset, 'url', str(asset))
                                        if not any(getattr(existing, 'url', str(existing)) == asset_url for existing in combined_outputs[asset_type]):
                                            combined_outputs[asset_type].append(asset)
                                    else:
                                        # For other asset types, use string representation
                                        asset_str = str(asset)
                                        if asset_str not in [str(existing) for existing in combined_outputs[asset_type]]:
                                            combined_outputs[asset_type].append(asset)
                                #logger.info(f"Added {len(assets)} legacy assets of type {asset_type}")

        # Deduplicate combined outputs to avoid duplicate assets across tasks
        deduplicated_outputs = _deduplicate_combined_outputs(combined_outputs)

        #total_assets = sum(len(assets) for assets in deduplicated_outputs.values())
        return deduplicated_outputs
        
    except Exception as e:
        logger.error(f"Error executing tasks in step {step.name}: {e}")
        raise

async def run_workflow(workflow_data):
    """Run a workflow"""
    global workflow_stopped_externally
    task_executor = None
    workflow_outputs = {}
    
    try:
        # Parse workflow
        if isinstance(workflow_data, str):
            workflow_data = json.loads(workflow_data)
        
        # Debug: Log the workflow data received by the runner
        logger.info(f"Runner received workflow data type: {type(workflow_data)}")
        logger.info(f"Runner received workflow data keys: {list(workflow_data.keys()) if isinstance(workflow_data, dict) else 'Not a dict'}")
        logger.info(f"Runner received workflow data: {workflow_data}")
        # Debug: Check use_proxy in raw workflow data before parsing
        if isinstance(workflow_data, dict) and 'steps' in workflow_data:
            for step_idx, step in enumerate(workflow_data['steps']):
                logger.info(f"🔍 DEBUG: Raw step {step_idx}: {step.get('name')}")
                for task_idx, task in enumerate(step.get('tasks', [])):
                    logger.info(f"  Raw task {task_idx}: {task.get('name')}")
                    logger.info(f"    use_proxy in raw JSON: {task.get('use_proxy', 'NOT IN RAW JSON')}")
        
        # # Check if this is the new format with definition
        # if isinstance(workflow_data, dict):
        #     if 'definition' in workflow_data:
        #         logger.info("Detected new workflow format with definition")
        #         definition = workflow_data['definition']
        #         logger.info(f"Definition keys: {list(definition.keys()) if isinstance(definition, dict) else 'Not a dict'}")
                
        #         if 'inputs' in definition:
        #             logger.info(f"Workflow has {len(definition['inputs'])} centralized inputs:")
        #             for input_name, input_def in definition['inputs'].items():
        #                 logger.info(f"  Input {input_name}: type={input_def.get('type')}, asset_type={input_def.get('asset_type')}")
                
        #         if 'steps' in definition:
        #             logger.info(f"Workflow has {len(definition['steps'])} steps")
        #             for i, step in enumerate(definition['steps']):
        #                 logger.info(f"Step {i}: {step.get('name')} with {len(step.get('tasks', []))} tasks")
        #                 for j, task in enumerate(step.get('tasks', [])):
        #                     logger.info(f"  Task {j}: {task.get('name')} (type: {task.get('task_type')})")
        #                     if 'input_mapping' in task:
        #                         logger.info(f"    Input mapping: {task.get('input_mapping')}")
        #                     logger.info(f"    Task keys: {list(task.keys()) if isinstance(task, dict) else 'Not a dict'}")
        #     elif 'steps' in workflow_data:
        #         logger.info("Detected legacy workflow format")
        #     logger.info(f"Workflow has {len(workflow_data['steps'])} steps")
        #     for i, step in enumerate(workflow_data['steps']):
        #         logger.info(f"Step {i}: {step.get('name')} with {len(step.get('tasks', []))} tasks")
        #         for j, task in enumerate(step.get('tasks', [])):
        #             logger.info(f"  Task {j}: {task.get('name')}, input_filter: {task.get('input_filter')}")
        #             logger.info(f"  Task {j} keys: {list(task.keys()) if isinstance(task, dict) else 'Not a dict'}")
        
        workflow = Workflow(**workflow_data)

        wf_program_id = (workflow_data.get("program_id") or "").strip()
        if not wf_program_id:
            raise ValueError(
                "workflow_data must include program_id (UUID). "
                "Upgrade the API/workflow snapshot; name-only workflows are no longer supported for runner ingestion."
            )

        # Debug: Check if output_mode and use_proxy are preserved after parsing
        for step_idx, step in enumerate(workflow.steps):
            logger.info(f"  Step {step_idx}: {step.name}")
            for task_idx, task in enumerate(step.tasks):
                logger.info(f"    Task {task_idx}: {task.name}")

        # Get Kubernetes client
        batch_v1 = get_k8s_client()
        
        # Use EXECUTION_ID for logging (always valid) and WORKFLOW_ID for workflow definition reference (can be empty for custom workflows)
        execution_id = os.getenv('EXECUTION_ID')
        workflow_id = os.getenv('WORKFLOW_ID')
        
        if not execution_id:
            logger.error("EXECUTION_ID environment variable is not set")
            raise ValueError("EXECUTION_ID environment variable is required")
        
        logger.debug(f"Using execution_id: {execution_id}, workflow_id: {workflow_id}")

        # Initialize asset processing coordinator
        api_url = os.getenv('API_URL')
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
        
        if not api_url:
            logger.error("API_URL environment variable is not set")
            raise ValueError("API_URL environment variable is required")
        
        if not internal_api_key:
            logger.error("INTERNAL_SERVICE_API_KEY environment variable is not set")
            raise ValueError("INTERNAL_SERVICE_API_KEY environment variable is required")

        try:
            parameter_manager.load_all_from_api()
        except RuntimeError as e:
            logger.error("%s", e)
            raise

        # Create API client for unified progressive streaming
        api_client = DataAPIClient(api_url, internal_api_key)
        logger.debug(f"Initialized API client for {api_url}")
        
        # Initialize task executor
        task_executor = TaskExecutor(batch_v1)
        await task_executor.initialize()
        
        # Set workflow context for input mapping resolution
        task_executor.set_workflow_context(workflow)
        task_executor.program_id = wf_program_id

        # Enable unified progressive streaming in task execution manager
        if hasattr(task_executor, 'execution_manager') and task_executor.execution_manager:
            task_executor.execution_manager.enable_progressive_streaming(
                api_client, None, workflow.program_name, wf_program_id
            )
        
        workflow_outputs = {
            "program_name": workflow.program_name,
            "program_id": wf_program_id,
            "workflow_name": workflow.name,
            "workflow_id": workflow_id,  # Can be None for custom workflows
            "execution_id": execution_id,  # Always valid
            "result": "running",
            "workflow_steps": [],
            "total_steps": len(workflow.steps),
            "total_assets": 0,
            "total_findings": 0,
            "workflow_definition": serialize_workflow_definition_snapshot(workflow, workflow_data),
        }
        headers = {}
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
        if internal_api_key:
            headers['Authorization'] = f'Bearer {internal_api_key}'
        
        requests.post(
            f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs", 
            json=workflow_outputs,
            headers=headers
        )
        # Track outputs from each step
        step_outputs = {}
        
        # Run each step in sequence
        for step_num, step in enumerate(workflow.steps, 1):
            # Check if workflow was stopped externally before starting each step
            if workflow_stopped_externally:
                logger.info("Workflow was stopped externally, terminating execution")
                workflow_outputs["result"] = "stopped"
                _apply_waf_to_workflow_outputs(workflow_outputs, task_executor)
                return False
            logger.info(f"Starting step {step_num}: {step.name}")

            # Start step timing
            if task_executor:
                task_executor.start_step_timing(step.name)

            # Send initial workflow status update to show step has started
            # Include all previously completed steps plus the current starting step
            current_step_data = task_executor.get_step_status_data(step.name, {})
            if current_step_data:
                temp_workflow_outputs = workflow_outputs.copy()
                # Add the current step to the existing steps for the update
                existing_steps = temp_workflow_outputs["workflow_steps"].copy()
                existing_steps.append({step.name: current_step_data})
                temp_workflow_outputs["workflow_steps"] = existing_steps
                await send_step_started_update(temp_workflow_outputs, step.name, workflow_id, execution_id)

            try:
                step_outputs[step.name] = await run_step(
                    task_executor,
                    wf_program_id,
                    workflow.program_name,
                    workflow_id,
                    step_num,
                    step,
                    step_outputs
                )
                # Log enhanced step output information
                _log_step_outputs(step.name, step_outputs)
                logger.info(f"Completed step {step_num}: {step.name}")

                # Complete step timing
                if task_executor:
                    task_executor.complete_step_timing(step.name)

                # Get detailed step data from task_executor if available
                if task_executor:
                    # Pass the actual deduplicated step outputs to get correct counts
                    actual_step_assets = step_outputs.get(step.name, {})
                    step_status_data = task_executor.get_step_status_data(step.name, actual_step_assets)
                    if step_status_data:
                        # Use detailed step data from API responses
                        workflow_outputs["workflow_steps"].append({
                            step.name: step_status_data
                        })

                        # Log concise asset processing summary only if there are results
                        if step_status_data.get('total_assets', 0) > 0 or step_status_data.get('total_findings', 0) > 0:
                            _log_concise_asset_summary(step.name, step_status_data)
                    else:
                        # Fallback to basic asset counts if no API response data
                        serialized_step_output = {}
                        for asset_type, assets in step_outputs[step.name].items():
                            # Handle both AssetType enum and string keys
                            if hasattr(asset_type, 'value'):
                                # AssetType enum
                                key = str(asset_type.value)
                            else:
                                # Already a string
                                key = str(asset_type)
                            serialized_step_output[key] = len(assets)

                        workflow_outputs["workflow_steps"].append({
                            step.name: serialized_step_output
                        })
                else:
                    # Fallback if no task_executor available
                    logger.debug("No task_executor available, using basic counts")
                    serialized_step_output = {}
                    for asset_type, assets in step_outputs[step.name].items():
                        # Handle both AssetType enum and string keys
                        if hasattr(asset_type, 'value'):
                            # AssetType enum
                            key = str(asset_type.value)
                        else:
                            # Already a string
                            key = str(asset_type)
                        serialized_step_output[key] = len(assets)

                    workflow_outputs["workflow_steps"].append({
                        step.name: serialized_step_output
                    })
                logger.debug(f"Updating workflow outputs: {workflow_outputs}")
                _apply_waf_to_workflow_outputs(workflow_outputs, task_executor)
                headers = {}
                internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
                if internal_api_key:
                    headers['Authorization'] = f'Bearer {internal_api_key}'
                
                requests.post(
                    f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs", 
                    json=workflow_outputs,
                    headers=headers
                )
            except Exception as e:
                logger.error(f"Step {step_num} ({step.name}) failed: {e}")
                raise
        
        # Progressive streaming cleanup handled by TaskExecutionManager

        # Only set success if we weren't stopped externally
        if not workflow_stopped_externally:
            workflow_outputs["result"] = "success"
            logger.info("Workflow completed successfully")
        else:
            workflow_outputs["result"] = "stopped"
            logger.info("Workflow was stopped externally")
        _apply_waf_to_workflow_outputs(workflow_outputs, task_executor)
        return True
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        logger.exception(e)

        # Progressive streaming cleanup handled by TaskExecutionManager

        if not workflow_stopped_externally:
            workflow_outputs["result"] = "failed"
        else:
            workflow_outputs["result"] = "stopped"
        _apply_waf_to_workflow_outputs(workflow_outputs, task_executor)
        return False
    finally:
        # Check current status before updating - don't overwrite if already stopped
        execution_id = os.getenv('EXECUTION_ID')
        current_status = get_current_workflow_status(execution_id)
        
        if current_status == "stopped":
            logger.info("Workflow was stopped externally, not updating final status")
        else:
            # Capture final pod output before workflow completion
            final_pod_output = _capture_pod_output(execution_id)
            if final_pod_output:
                headers = {}
                internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
                if internal_api_key:
                    headers['Authorization'] = f'Bearer {internal_api_key}'
                
                log_object = {
                    "execution_id": execution_id,
                    "runner_pod_output": f"\n--- Final Workflow Output ---\n{final_pod_output}\n\n--- End Workflow ---\n",
                }
                _pod_pid = (
                    workflow_outputs.get("program_id")
                    if isinstance(workflow_outputs, dict)
                    else None
                ) or (os.getenv("PROGRAM_ID") or "").strip()
                if _pod_pid:
                    log_object["program_id"] = str(_pod_pid)
                _pod_pname = (
                    workflow_outputs.get("program_name")
                    if isinstance(workflow_outputs, dict)
                    else None
                ) or os.getenv("PROGRAM_NAME")
                if _pod_pname:
                    log_object["program_name"] = _pod_pname
                try:
                    requests.post(
                        f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs",
                        json=log_object,
                        headers=headers
                    )
                except Exception as e:
                    logger.warning(f"Failed to log final pod output: {e}")
            
            # Only update status if it wasn't stopped externally
            if isinstance(workflow_outputs, dict):
                _apply_waf_to_workflow_outputs(workflow_outputs, task_executor)
            logger.info(f"Updating final workflow status: {workflow_outputs.get('result', 'unknown')}")
            headers = {}
            internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
            if internal_api_key:
                headers['Authorization'] = f'Bearer {internal_api_key}'
            
            requests.post(
                f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs", 
                json=workflow_outputs,
                headers=headers
            )
        
        if task_executor:
            try:
                await task_executor.shutdown()
                logger.info("Task executor shut down successfully")
            except Exception as e:
                logger.error(f"Error during task executor shutdown: {e}")
        
        # Progressive streaming cleanup handled by TaskExecutionManager

async def send_step_started_update(workflow_outputs, step_name, workflow_id, execution_id):
    """Send workflow status update when a step starts"""
    try:
        # Send the status update to show step has started
        headers = {}
        internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY')
        if internal_api_key:
            headers['Authorization'] = f'Bearer {internal_api_key}'

        response = requests.post(
            f"{os.getenv('API_URL')}/workflows/executions/{execution_id}/logs",
            json=workflow_outputs,
            headers=headers
        )

        if response.status_code == 200:
            logger.debug(f"Sent step started update for '{step_name}' with {len(workflow_outputs.get('workflow_steps', []))} total steps")
        else:
            logger.warning(f"Failed to send step started update for '{step_name}': {response.status_code}")
    except Exception as e:
        logger.warning(f"Error sending step started update for '{step_name}': {e}")


def main():
    # Check if workflow data was provided
    if len(sys.argv) != 2:
        logger.error("Usage: python run-workflow.py <workflow.json or JSON string>")
        sys.exit(1)
    
    workflow_data = sys.argv[1]
    
    # If the argument looks like a file path (doesn't start with {), try to read it
    if not workflow_data.strip().startswith('{'):
        try:
            with open(workflow_data, 'r') as f:
                workflow_data = f.read()
        except Exception as e:
            logger.error(f"Failed to read workflow file: {e}")
            sys.exit(1)
    
    # Run the workflow
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create a task for the workflow
        workflow_task = loop.create_task(run_workflow(workflow_data))
        
        try:
            success = loop.run_until_complete(workflow_task)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, cancelling tasks...")
            workflow_task.cancel()
            try:
                loop.run_until_complete(workflow_task)
            except asyncio.CancelledError:
                pass
            success = False
        finally:
            # Cancel all remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Run loop until all tasks are cancelled
            if pending:
                logger.info(f"Cancelling {len(pending)} pending tasks")
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            # Give time for async cleanup to complete
            loop.run_until_complete(asyncio.sleep(0.1))
            
            # Close the loop
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        
        if success:
            logger.info("Workflow completed successfully")
            # Force exit to terminate any lingering threads
            sys.exit(0)
        else:
            logger.error("Workflow failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    # Ensure process exits even if there are still running threads
    sys.exit(0) 