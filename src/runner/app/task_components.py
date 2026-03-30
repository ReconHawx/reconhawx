#!/usr/bin/env python3
"""
Decomposed task execution components for improved performance and maintainability.
Implements Phase 1 > Item 1 from PERFORMANCE_RECOMMENDATIONS.md
"""

import logging
import asyncio
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Iterator, AsyncIterator, Set
from dataclasses import dataclass
import json
import requests
import aiohttp
from tasks.base import AssetType
from models.workflow import AssetStore
from services.kubernetes import KubernetesService
from task_queue_client import TaskQueueClient

logger = logging.getLogger('task_components')
logger.setLevel(logging.DEBUG)

# Proxy batch configuration - limits active API Gateways
PROXY_BATCH_SIZE = int(os.getenv('PROXY_BATCH_SIZE', '5'))
PROXY_RATE_LIMIT = float(os.getenv('PROXY_RATE_LIMIT', '5.0'))

@dataclass
class MemoryOptimizationConfig:
    """Configuration for memory optimization settings"""
    
    # Streaming thresholds
    streaming_asset_threshold: int = 2500  # Assets count threshold for streaming
    streaming_result_threshold: int = 500   # Result count threshold for streaming
    
    # Batch sizes
    asset_batch_size: int = 100             # Default batch size for asset processing
    streaming_batch_size: int = 1000        # Batch size for streaming operations
    memory_limit_mb: int = 500              # Memory limit per batch in MB
    
    # Large list thresholds
    large_list_threshold: int = 1000        # When to use generator-based merging
    gc_threshold: int = 50000               # When to trigger garbage collection
    
    # Fetching parameters
    standard_page_size: int = 100           # Page size for standard asset fetching
    streaming_page_size: int = 1000         # Page size for streaming asset fetching
    max_pages: int = 1000                   # Safety limit for pagination
    
    # Redis batch operations
    redis_batch_size: int = 1000            # Maximum keys to fetch in single Redis pipeline
    
    @classmethod
    def from_environment(cls) -> 'MemoryOptimizationConfig':
        """Load configuration from environment variables"""
        return cls(
            streaming_asset_threshold=int(os.getenv('STREAMING_ASSET_THRESHOLD', '10000')),
            streaming_result_threshold=int(os.getenv('STREAMING_RESULT_THRESHOLD', '500')),
            asset_batch_size=int(os.getenv('ASSET_BATCH_SIZE', '100')),
            streaming_batch_size=int(os.getenv('STREAMING_BATCH_SIZE', '1000')),
            memory_limit_mb=int(os.getenv('MEMORY_LIMIT_MB', '500')),
            large_list_threshold=int(os.getenv('LARGE_LIST_THRESHOLD', '1000')),
            gc_threshold=int(os.getenv('GC_THRESHOLD', '50000')),
            standard_page_size=int(os.getenv('STANDARD_PAGE_SIZE', '100')),
            streaming_page_size=int(os.getenv('STREAMING_PAGE_SIZE', '1000')),
            max_pages=int(os.getenv('MAX_PAGES', '1000')),
            redis_batch_size=int(os.getenv('REDIS_BATCH_SIZE', '1000'))
        )

@dataclass
class ProgressiveStreamingConfig:
    """Configuration for progressive asset streaming"""
    
    # Retry configuration
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    
    # Batch configuration
    min_assets_to_send: int = 1  # Send assets even for single results
    max_concurrent_sends: int = 5  # Limit concurrent API calls
    
    # Timeout configuration
    send_timeout: float = 30.0
    
    @classmethod
    def from_environment(cls) -> 'ProgressiveStreamingConfig':
        """Load configuration from environment variables"""
        return cls(
            max_retries=int(os.getenv('PROGRESSIVE_MAX_RETRIES', '3')),
            retry_delay=float(os.getenv('PROGRESSIVE_RETRY_DELAY', '1.0')),
            retry_backoff=float(os.getenv('PROGRESSIVE_RETRY_BACKOFF', '2.0')),
            min_assets_to_send=int(os.getenv('PROGRESSIVE_MIN_ASSETS', '1')),
            max_concurrent_sends=int(os.getenv('PROGRESSIVE_MAX_CONCURRENT', '5')),
            send_timeout=float(os.getenv('PROGRESSIVE_SEND_TIMEOUT', '30.0'))
        )
    
    def calculate_timeout_for_assets(self, asset_count: int) -> float:
        """Calculate timeout based on asset count for progressive streaming"""
        # Base timeout for small chunks
        if asset_count <= 1000:
            return self.send_timeout
        
        # Dynamic timeout: base + 10s per 1000 assets (more conservative than DataAPIClient)
        extra_timeout = ((asset_count - 1000) // 1000 + 1) * 10
        calculated_timeout = self.send_timeout + extra_timeout
        
        # Cap at reasonable maximum (3 minutes for progressive streaming)
        max_timeout = 180
        return min(calculated_timeout, max_timeout)

class ProgressiveAssetStreamer:
    """Unified progressive streaming with asset/findings separation and step coordination"""
    
    def __init__(self, data_api_client, asset_processor, config: Optional[ProgressiveStreamingConfig] = None, program_name: str = None):
        self.data_api_client = data_api_client
        self.asset_processor = asset_processor
        self.config = config or ProgressiveStreamingConfig.from_environment()
        self.program_name = program_name
        self.send_semaphore = asyncio.Semaphore(self.config.max_concurrent_sends)
        self.sent_assets_count = 0
        self.failed_sends = 0
        
        # Job tracking for step coordination (like AssetProcessingCoordinator)
        self.pending_jobs: Dict[str, Any] = {}  # job_id -> job info
        self.step_jobs: Dict[str, List[str]] = {}  # step_name -> [job_ids]
        self.job_status_cache: Dict[str, Dict[str, Any]] = {}  # job_id -> status
        self.processed_steps: Set[str] = set()  # Track processed steps
        
        # Configuration for coordination
        self.default_timeout = 3600  # 1 hour default timeout
        self.min_poll_interval = 2   # Minimum 2 seconds between polls
        self.max_poll_interval = 30  # Maximum 30 seconds between polls
        self.backoff_multiplier = 1.5  # Exponential backoff multiplier

        # Store API responses for step aggregation
        self._step_api_responses: Dict[str, List[Dict[str, Any]]] = {}
    
    async def shutdown(self):
        """Shutdown the progressive streamer and its data API client"""
        if self.data_api_client and hasattr(self.data_api_client, 'shutdown'):
            await self.data_api_client.shutdown()
        
    async def stream_chunk_assets(self, step_name: str, program_name: str, workflow_id: str, 
                                chunk_result: 'TaskResult') -> bool:
        """Stream assets from a single completed chunk"""
        if not chunk_result.success or not chunk_result.parsed_assets:
            return True  # No assets to send, but not an error
        
        # Check if we have enough assets to send
        total_assets = sum(len(assets) for assets in chunk_result.parsed_assets.values()) if chunk_result.parsed_assets else 0
        if total_assets < self.config.min_assets_to_send:
            logger.debug(f"Chunk {chunk_result.task_id} has {total_assets} assets, below threshold")
            return True
        
        async with self.send_semaphore:
            return await self._send_chunk_assets_with_retry(
                step_name, program_name, workflow_id, chunk_result
            )
    
    async def _send_chunk_assets_with_retry(self, step_name: str, program_name: str, 
                                          workflow_id: str, chunk_result: 'TaskResult') -> bool:
        """Send chunk assets with retry logic"""
        last_error = None
        delay = self.config.retry_delay
        
        # Calculate dynamic timeout based on asset count
        total_assets = sum(len(assets) for assets in chunk_result.parsed_assets.values()) if chunk_result.parsed_assets else 0
        dynamic_timeout = self.config.calculate_timeout_for_assets(total_assets)
        
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.info(f"Streaming {total_assets} assets from chunk {chunk_result.task_id} (attempt {attempt + 1}) with {dynamic_timeout}s timeout")
                
                # Use async timeout for the send operation
                success = await asyncio.wait_for(
                    self._send_single_chunk(step_name, program_name, workflow_id, chunk_result),
                    timeout=dynamic_timeout
                )
                
                if success:
                    if chunk_result.parsed_assets:
                        self.sent_assets_count += sum(len(assets) for assets in chunk_result.parsed_assets.values())
                    logger.info(f"Successfully streamed assets from chunk {chunk_result.task_id}")
                    return True
                else:
                    logger.warning(f"Failed to send assets from chunk {chunk_result.task_id}")
                    last_error = "API call returned failure"
                    
            except asyncio.TimeoutError:
                last_error = f"Timeout after {dynamic_timeout}s"
                logger.warning(f"Timeout sending assets from chunk {chunk_result.task_id}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Error sending assets from chunk {chunk_result.task_id}: {last_error}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.max_retries:
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay *= self.config.retry_backoff
        
        # All retries failed
        self.failed_sends += 1
        logger.error(f"Failed to send assets from chunk {chunk_result.task_id} after {self.config.max_retries + 1} attempts. Last error: {last_error}")
        return False
    
    async def _send_single_chunk(self, step_name: str, program_name: str, 
                               workflow_id: str, chunk_result: 'TaskResult') -> bool:
        """Send assets and findings from a single chunk with proper separation"""
        try:
            logger.info(f"Sending chunk {chunk_result.task_id} with separated assets and findings")
            
            # Separate assets from findings (like AssetProcessingCoordinator)
            regular_assets, nuclei_findings, screenshots = self._separate_assets_and_findings(chunk_result.parsed_assets)
            
            success = True
            
            # Send regular assets FIRST (if any)
            if regular_assets:
                total_assets = sum(len(assets) for assets in regular_assets.values())
                logger.info(f"Sending {total_assets} assets from chunk {chunk_result.task_id}")
                
                response = await self.data_api_client.post_assets_unified(
                    regular_assets,
                    program_name,
                    workflow_id,
                    step_name
                )
                
                # Track asset job for step coordination
                if response.get("processing_mode") == "unified_async":
                    job_id = response.get("job_id")
                    if job_id:
                        self._track_job_for_step(step_name, job_id, "asset", chunk_result.task_id)
                        logger.info(f"Tracked asset job {job_id} for step {step_name}")
                
                success = success and (response.get("status") != "error")
            
            # Send screenshots to dedicated endpoint
            if screenshots:
                logger.info(f"Sending {len(screenshots)} screenshots from chunk {chunk_result.task_id}")
                
                screenshot_response = await self.data_api_client._send_screenshot_assets(
                    screenshots, 
                    program_name, 
                    workflow_id, 
                    step_name
                )
                
                success = success and screenshot_response[0]  # Returns (success, responses)
            
            # Send nuclei findings LAST (if any) - after assets are created
            if nuclei_findings:
                logger.info(f"Sending {len(nuclei_findings)} nuclei findings from chunk {chunk_result.task_id}")
                
                findings_response = await self.data_api_client.post_nuclei_findings_unified(
                    nuclei_findings, 
                    program_name, 
                    workflow_id=workflow_id, 
                    step_name=step_name
                )
                
                # Track findings job for step coordination
                if findings_response.get("processing_mode") == "unified_async":
                    job_id = findings_response.get("job_id")
                    if job_id:
                        self._track_job_for_step(step_name, job_id, "findings", chunk_result.task_id)
                        logger.info(f"Tracked findings job {job_id} for step {step_name}")
                
                success = success and (findings_response.get("status") != "error")
            
            # Mark step as processed
            self.processed_steps.add(step_name)
            
            return success

        except Exception as e:
            logger.error(f"Error sending chunk {chunk_result.task_id}: {e}")
            return False
    
    async def wait_for_step_completion(self, step_name: str, timeout: Optional[int] = None) -> bool:
        """Wait for all jobs from a step to complete before proceeding to next step"""
        if step_name not in self.step_jobs or not self.step_jobs[step_name]:
            logger.info(f"No jobs to wait for in step {step_name}")
            return True
        
        if timeout is None:
            timeout = self.default_timeout
        
        logger.debug(f"Waiting for {len(self.step_jobs[step_name])} jobs from step {step_name} to complete...")
        
        try:
            # Wait for all jobs from this step
            job_futures = [
                self._wait_for_job_completion(job_id, step_name, timeout)
                for job_id in self.step_jobs[step_name]
            ]
            
            await asyncio.gather(*job_futures)
            logger.debug(f"All jobs from step {step_name} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error waiting for step {step_name} completion: {e}")
            raise
    
    async def _wait_for_job_completion(self, job_id: str, step_name: str, timeout: int) -> bool:
        """Wait for a specific job to complete"""
        import time
        
        start_time = time.time()
        poll_interval = self.min_poll_interval
                
        while time.time() - start_time < timeout:
            try:
                # Get job status from appropriate API endpoint based on job type
                if job_id in self.pending_jobs:
                    job_type = self.pending_jobs[job_id].get("job_type", "asset")
                else:
                    job_type = "asset"  # Default to asset job
                
                if job_type == "findings":
                    job_status = await self.data_api_client.get_findings_job_status(job_id)
                else:
                    job_status = await self.data_api_client.get_job_status(job_id)
                
                # Update cache
                self.job_status_cache[job_id] = job_status
                
                # Check job status
                status = job_status.get("status", "unknown")
                if status == "completed":
                    logger.debug(f"Job {job_id} completed successfully for step {step_name}")

                    # Store the job status we already retrieved for step aggregation
                    # The job_status already contains the detailed results we need
                    if job_status:
                        logger.info(f"Storing completed job status for {job_type} job {job_id} in step {step_name}")
                        self._store_step_api_response(step_name, job_status)
                    else:
                        logger.warning(f"No job status data to store for {job_type} job {job_id} in step {step_name}")

                    return True
                elif status == "not_found":
                    logger.debug(f"Job {job_id} not found (likely completed and cleaned up) for step {step_name}")

                    # Job not found - it was likely completed and cleaned up already
                    # We don't have detailed results for this case
                    logger.debug(f"No detailed results available for cleaned up {job_type} job {job_id}")

                    return True
                elif status == "failed":
                    error_msg = job_status.get("error", "Unknown error")
                    logger.error(f"Job {job_id} failed for step {step_name}: {error_msg}")
                    raise Exception(f"Job {job_id} failed: {error_msg}")
                
                # Job is still running, wait and poll again
                await asyncio.sleep(poll_interval)
                
                # Exponential backoff for polling
                poll_interval = min(poll_interval * self.backoff_multiplier, self.max_poll_interval)
                
            except Exception as e:
                logger.error(f"Error checking job {job_id} status: {e}")
                raise
        
        # Timeout reached
        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    def get_streaming_stats(self) -> Dict[str, Any]:
        """Get statistics about the streaming process"""
        return {
            "sent_assets_count": self.sent_assets_count,
            "failed_sends": self.failed_sends,
            "success_rate": (self.sent_assets_count / (self.sent_assets_count + self.failed_sends)) if (self.sent_assets_count + self.failed_sends) > 0 else 0,
            "pending_jobs": len(self.pending_jobs),
            "processed_steps": list(self.processed_steps),
            "step_jobs": {step: len(jobs) for step, jobs in self.step_jobs.items()}
        }
    
    def _separate_assets_and_findings(self, parsed_assets: Dict[Any, List[Any]]) -> tuple:
        """Separate assets from findings (copied from AssetProcessingCoordinator logic)"""
        from tasks.base import FindingType, AssetType
        
        nuclei_findings = []
        regular_assets = {}
        screenshots = []
        
        for k, v in parsed_assets.items():
            if k == FindingType.NUCLEI:
                nuclei_findings = v  # Extract nuclei findings
            elif k == AssetType.SCREENSHOT:
                screenshots = v  # Extract screenshots for separate handling
            elif k != FindingType.TYPOSQUAT_DOMAIN:  # Exclude typosquat assets
                regular_assets[k] = v  # Keep other assets
        
        return regular_assets, nuclei_findings, screenshots
    
    def _track_job_for_step(self, step_name: str, job_id: str, job_type: str, chunk_id: str = None):
        """Track a job for step coordination"""
        from datetime import datetime
        
        # Create job info
        job_info = {
            "job_id": job_id,
            "step_name": step_name,
            "job_type": job_type,  # "asset" or "findings"
            "chunk_id": chunk_id,
            "sent_at": datetime.utcnow(),
            "status": "pending"
        }
        
        # Track in pending jobs
        self.pending_jobs[job_id] = job_info
        
        # Track job for this step
        if step_name not in self.step_jobs:
            self.step_jobs[step_name] = []
        self.step_jobs[step_name].append(job_id)
        
        logger.debug(f"Tracked {job_type} job {job_id} for step {step_name}")

    def _store_step_api_response(self, step_name: str, api_response: Dict[str, Any]):
        """Store API response data for a step to be used in workflow status updates"""
        if step_name not in self._step_api_responses:
            self._step_api_responses[step_name] = []

        self._step_api_responses[step_name].append(api_response)

@dataclass
class TaskResult:
    """Result from a single task execution"""
    task_id: str
    success: bool
    output: str
    parsed_assets: Optional[Dict[str, List[Any]]]
    execution_time: float
    error: Optional[str] = None

class TaskExecutionManager:
    """Handles pure task execution logic with progressive streaming support"""
    
    def __init__(self, k8s_service: KubernetesService, docker_registry: str, workflow_id: str):
        self.k8s_service = k8s_service
        self.docker_registry = docker_registry
        self.workflow_id = workflow_id
        self.JOB_BATCH_SIZE = 150
        self.progressive_streamer = None  # Will be set when progressive streaming is enabled
        self.background_tasks = set()  # Track background tasks for proper cleanup

    def enable_progressive_streaming(self, data_api_client, asset_processor, program_name: str = None):
        """Enable unified progressive streaming for this task execution manager"""
        self.progressive_streamer = ProgressiveAssetStreamer(data_api_client, asset_processor, program_name=program_name)
        # Progressive streaming initialized with step coordination
    
    async def wait_for_step_completion(self, step_name: str, timeout: Optional[int] = None) -> bool:
        """Wait for all jobs from a step to complete before proceeding"""
        if self.progressive_streamer:
            return await self.progressive_streamer.wait_for_step_completion(step_name, timeout)
        else:
            logger.warning(f"No progressive streamer available to wait for step {step_name}")
            return True


    
    def _create_background_task(self, coro):
        """Create a background task and track it for proper cleanup"""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        # Clean up completed tasks automatically
        task.add_done_callback(self.background_tasks.discard)
        return task
    
    async def cleanup_background_tasks(self):
        """Wait for background tasks to complete, then cleanup"""
        if not self.background_tasks:
            return
        
        logger.info(f"Waiting for {len(self.background_tasks)} background tasks to complete")
        
        # First, wait for tasks to complete normally with a longer timeout
        if self.background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=10.0  # Give more time for tasks to complete naturally
                )
                logger.info("All background tasks completed successfully")
            except asyncio.TimeoutError:
                logger.warning("Some background tasks did not complete within timeout, cancelling remaining tasks")
                # Cancel only the tasks that are still running
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
                
                # Wait for cancellation to complete with shorter timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.background_tasks, return_exceptions=True),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some background tasks did not cancel within timeout")
                except Exception as e:
                    logger.warning(f"Error during background task cancellation: {e}")
            except Exception as e:
                logger.warning(f"Error during background task completion: {e}")
        
        self.background_tasks.clear()
        logger.info("Background task cleanup completed")
    
    def was_asset_coordination_used(self, step_name: str) -> bool:
        """Check if asset coordination was used for a specific step"""
        return hasattr(self, 'asset_coordination_used') and step_name in self.asset_coordination_used


class StreamingAssetProcessor:
    """Memory-efficient streaming asset processor with configurable batch sizes"""
    
    def __init__(self, config: Optional[MemoryOptimizationConfig] = None):
        self.config = config or MemoryOptimizationConfig.from_environment()
        self.processed_count = 0
    
    async def process_assets_streaming(self, task_results: List[TaskResult]) -> AsyncIterator[Dict[str, List[Any]]]:
        """Process assets in batches to control memory usage"""
        batch = []
        current_batch_size = 0
        
        for result in task_results:
            if result.success and result.parsed_assets:
                batch.append(result)
                current_batch_size += self._estimate_memory_usage(result.parsed_assets)
                
                # Yield batch when size limit reached or memory threshold exceeded
                if (len(batch) >= self.config.streaming_batch_size or 
                    current_batch_size > self.config.memory_limit_mb * 1024 * 1024):
                    
                    processed_batch = await self._process_batch(batch)
                    if processed_batch:
                        yield processed_batch
                    
                    batch.clear()
                    current_batch_size = 0
                    self.processed_count += len(batch)
        
        # Process remaining items
        if batch:
            processed_batch = await self._process_batch(batch)
            if processed_batch:
                yield processed_batch
            self.processed_count += len(batch)
    
    async def _process_batch(self, batch: List[TaskResult]) -> Dict[str, List[Any]]:
        """Process a batch of task results efficiently"""
        combined_assets = {}
        
        for result in batch:
            if result.success and result.parsed_assets:
                combined_assets = self._merge_assets_efficient(combined_assets, result.parsed_assets)
        
        return combined_assets
    
    def _merge_assets_efficient(self, existing: Dict[str, List[Any]], 
                               new: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """Memory-efficient asset merging using generators for large datasets"""
        for asset_type, new_assets in new.items():
            if asset_type not in existing:
                existing[asset_type] = []
            
            # Use memory-efficient merging for large asset lists
            if len(new_assets) > self.config.large_list_threshold:
                logger.info(f"Using generator-based merging for {len(new_assets)} {asset_type.value} assets")
                existing[asset_type] = list(self._merge_large_asset_list(
                    existing[asset_type], new_assets, asset_type
                ))
            else:
                existing[asset_type].extend(new_assets)
        
        return existing
    
    def _merge_large_asset_list(self, existing: List[Any], new: List[Any], 
                               asset_type: AssetType) -> Iterator[Any]:
        """Generator-based merging for large lists to minimize memory usage"""
        # Create lookup for existing assets to avoid duplicates
        existing_lookup = {}
        
        # Build lookup based on asset type
        if asset_type == "subdomain":
            existing_lookup = {self._get_domain_key(asset): asset for asset in existing 
                             if hasattr(asset, 'name')}
        elif asset_type == "ip":
            existing_lookup = {self._get_ip_key(asset): asset for asset in existing 
                             if hasattr(asset, 'ip')}
        elif asset_type == "url":
            existing_lookup = {self._get_url_key(asset): asset for asset in existing 
                             if hasattr(asset, 'url')}
        else:
            # For other types, use string representation as key
            existing_lookup = {str(asset): asset for asset in existing}
        
        # Yield existing assets first
        for asset in existing:
            yield asset
        
        # Process new assets and yield only unique ones
        for asset in new:
            key = self._get_asset_key(asset, asset_type)
            if key not in existing_lookup:
                yield asset
                existing_lookup[key] = asset
    
    def _get_asset_key(self, asset: Any, asset_type: AssetType) -> str:
        """Get unique key for asset based on its type"""
        if asset_type == "subdomain":
            return self._get_domain_key(asset)
        elif asset_type == "ip":
            return self._get_ip_key(asset)
        elif asset_type == "url":
            return self._get_url_key(asset)
        else:
            return str(asset)
    
    def _get_domain_key(self, asset: Any) -> str:
        """Get unique key for domain asset"""
        return getattr(asset, 'name', str(asset))
    
    def _get_ip_key(self, asset: Any) -> str:
        """Get unique key for IP asset"""
        return getattr(asset, 'ip', str(asset))
    
    def _get_url_key(self, asset: Any) -> str:
        """Get unique key for URL asset"""
        return getattr(asset, 'url', str(asset))
    
    def _estimate_memory_usage(self, assets: Dict[str, List[Any]]) -> int:
        """Rough estimate of memory usage for assets in bytes"""
        total_size = 0
        
        for asset_type, asset_list in assets.items():
            # Rough estimate: 500 bytes per asset on average
            total_size += len(asset_list) * 500
        
        return total_size


class AssetProcessor:
    """Enhanced asset processor with memory optimization capabilities"""
    
    def __init__(self, asset_store: AssetStore, enable_streaming: bool = True, 
                 config: Optional[MemoryOptimizationConfig] = None):
        self.asset_store = asset_store
        self.enable_streaming = enable_streaming
        self.config = config or MemoryOptimizationConfig.from_environment()
        self.streaming_processor = StreamingAssetProcessor(self.config) if enable_streaming else None
    
    async def process_results(self, results: List[TaskResult]) -> Dict[str, List[Any]]:
        """Process task results using streaming or standard processing based on data size"""
        if not results:
            return {}
        
        # Determine if we should use streaming based on result count and estimated memory usage
        total_asset_count = sum(
            sum(len(asset_list) for asset_list in result.parsed_assets.values()) 
            if result.success and result.parsed_assets else 0
            for result in results
        )
        
        # Use streaming for large datasets or when explicitly enabled
        if self.enable_streaming and (total_asset_count > self.config.streaming_asset_threshold or 
                                     len(results) > self.config.streaming_result_threshold):
            logger.info(f"Using streaming processing for {len(results)} results with {total_asset_count} total assets")
            return await self._process_results_streaming(results)
        else:
            logger.info(f"Using standard processing for {len(results)} results with {total_asset_count} total assets")
            return await self._process_results_standard(results)
    
    async def _process_results_streaming(self, results: List[TaskResult]) -> Dict[str, List[Any]]:
        """Process results using streaming to minimize memory usage"""
        combined_assets = {}
        
        if self.streaming_processor:
            async for batch_assets in self.streaming_processor.process_assets_streaming(results):
                # Merge each batch incrementally
                combined_assets = self.merge_assets_efficient(combined_assets, batch_assets)
                
                # Optional: Force garbage collection for large datasets
                import gc
                if len(combined_assets) > self.config.gc_threshold:
                    gc.collect()
            
            logger.info(f"Streaming processing completed. Total processed: {self.streaming_processor.processed_count}")
        else:
            logger.warning("Streaming processor is None, falling back to standard processing")
            return await self._process_results_standard(results)
        return combined_assets
    
    async def _process_results_standard(self, results: List[TaskResult]) -> Dict[str, List[Any]]:
        """Standard processing for smaller datasets"""
        combined_assets = {}
        
        for result in results:
            if result.success and result.parsed_assets:
                combined_assets = self.merge_assets(combined_assets, result.parsed_assets)
        
        return combined_assets
    
    def merge_assets_efficient(self, existing: Dict[str, List[Any]], 
                             new: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """Memory-efficient version of merge_assets for large datasets"""
        if not new:
            return existing
        
        for asset_type, new_asset_list in new.items():
            if not new_asset_list:
                continue
                
            if asset_type not in existing:
                existing[asset_type] = []
            
            # Use generator-based merging for large lists
            if (len(new_asset_list) > self.config.large_list_threshold or 
                len(existing[asset_type]) > self.config.large_list_threshold):
                logger.debug(f"Using memory-efficient merging for {asset_type.value} assets")
                existing[asset_type] = list(self._merge_large_asset_list_generator(
                    existing[asset_type], new_asset_list, asset_type
                ))
            else:
                # Use standard merging for smaller lists
                if asset_type == "subdomain":
                    existing[asset_type] = self._merge_domain_assets(existing[asset_type], new_asset_list)
                elif asset_type == "ip":
                    existing[asset_type] = self._merge_ip_assets(existing[asset_type], new_asset_list)
                elif asset_type == "url":
                    existing[asset_type] = self._merge_url_assets(existing[asset_type], new_asset_list)
                else:
                    existing[asset_type].extend(new_asset_list)
        
        return existing
    
    def _merge_large_asset_list_generator(self, existing: List[Any], new: List[Any], 
                                        asset_type: AssetType) -> Iterator[Any]:
        """Generator-based merging to reduce memory footprint for large asset lists"""
        # Create a set of keys for existing assets to check for duplicates
        existing_keys = set()
        
        # Yield existing assets and build lookup
        for asset in existing:
            key = self._get_asset_key_for_type(asset, asset_type)
            existing_keys.add(key)
            yield asset
        
        # Yield new assets that aren't duplicates
        for asset in new:
            key = self._get_asset_key_for_type(asset, asset_type)
            if key not in existing_keys:
                existing_keys.add(key)
                yield asset
    
    def _get_asset_key_for_type(self, asset: Any, asset_type: AssetType) -> str:
        """Get a unique key for an asset based on its type"""
        if asset_type == "subdomain":
            return getattr(asset, 'name', str(asset))
        elif asset_type == "ip":
            return getattr(asset, 'ip', str(asset))
        elif asset_type == "url":
            return getattr(asset, 'url', str(asset))
        elif asset_type == "service":
            # For services, use combination of ip and port
            ip = getattr(asset, 'ip', '')
            port = getattr(asset, 'port', '')
            return f"{ip}:{port}"
        else:
            return str(asset)
    
    def merge_assets(self, existing: Dict[str, List[Any]], 
                    new: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """Merge new assets with existing assets, deduplicating and combining properties"""
        result = existing.copy()
        
        for asset_type, new_asset_list in new.items():
            if asset_type not in result:
                result[asset_type] = []
            
            if asset_type == "subdomain":
                result[asset_type] = self._merge_domain_assets(result[asset_type], new_asset_list)
            elif asset_type == "ip":
                result[asset_type] = self._merge_ip_assets(result[asset_type], new_asset_list)
            elif asset_type == "url":
                result[asset_type] = self._merge_url_assets(result[asset_type], new_asset_list)
            else:
                # For other asset types, just append without deduplication
                result[asset_type].extend(new_asset_list)
        
        return result
    
    def _merge_domain_assets(self, existing: List[Any], new: List[Any]) -> List[Any]:
        """Merge domain assets with deduplication"""
        existing_lookup = {asset.name: asset for asset in existing if hasattr(asset, 'name')}
        
        for new_asset in new:
            if hasattr(new_asset, 'name'):
                if new_asset.name in existing_lookup:
                    # Merge properties
                    existing_asset = existing_lookup[new_asset.name]
                    if hasattr(new_asset, 'ip') and new_asset.ip:
                        existing_asset.ip = self._merge_list_field(existing_asset.ip, new_asset.ip)
                    if hasattr(new_asset, 'cname') and new_asset.cname:
                        existing_asset.cname = new_asset.cname
                    if hasattr(new_asset, 'is_wildcard') and new_asset.is_wildcard is not None:
                        existing_asset.is_wildcard = new_asset.is_wildcard
                else:
                    existing.append(new_asset)
                    existing_lookup[new_asset.name] = new_asset
        
        return existing
    
    def _merge_ip_assets(self, existing: List[Any], new: List[Any]) -> List[Any]:
        """Merge IP assets with deduplication"""
        existing_lookup = {asset.ip: asset for asset in existing if hasattr(asset, 'ip')}
        
        for new_asset in new:
            if hasattr(new_asset, 'ip'):
                if new_asset.ip in existing_lookup:
                    # Merge properties
                    existing_asset = existing_lookup[new_asset.ip]
                    if hasattr(new_asset, 'ptr') and new_asset.ptr:
                        existing_asset.ptr = self._merge_list_field(existing_asset.ptr, new_asset.ptr)
                else:
                    existing.append(new_asset)
                    existing_lookup[new_asset.ip] = new_asset
        
        return existing
    
    def _merge_url_assets(self, existing: List[Any], new: List[Any]) -> List[Any]:
        """Merge URL assets with deduplication"""
        existing_lookup = {asset.url: asset for asset in existing if hasattr(asset, 'url')}
        
        for new_asset in new:
            if hasattr(new_asset, 'url'):
                if new_asset.url in existing_lookup:
                    # Merge properties
                    existing_asset = existing_lookup[new_asset.url]
                    if hasattr(new_asset, 'techs') and new_asset.techs:
                        existing_asset.techs = self._merge_list_field(existing_asset.techs, new_asset.techs)
                    if hasattr(new_asset, 'favicon_hash') and new_asset.favicon_hash:
                        existing_asset.favicon_hash = new_asset.favicon_hash
                    if hasattr(new_asset, 'favicon_url') and new_asset.favicon_url:
                        existing_asset.favicon_url = new_asset.favicon_url
                else:
                    existing.append(new_asset)
                    existing_lookup[new_asset.url] = new_asset
        
        return existing
    
    def _merge_list_field(self, existing_field, new_field) -> List[Any]:
        """Merge list fields, handling string to list conversion"""
        if isinstance(new_field, str):
            new_field = [new_field]
        if existing_field and isinstance(existing_field, str):
            existing_field = [existing_field]
        
        if existing_field:
            return list(set(existing_field + new_field))
        else:
            return new_field
    
    def serialize_asset(self, asset: Any) -> Any:
        """Convert an asset object to a serializable type"""
        from pydantic import BaseModel
        from models.assets import Ip, Service as AssetService

        if isinstance(asset, datetime):
            return asset.isoformat()
        
        # Check if it's a Pydantic model
        elif isinstance(asset, BaseModel):
            try:
                # Use model_dump with json mode to ensure proper serialization and exclude None values
                serialized = asset.model_dump(mode='json', by_alias=True, exclude_none=True)
                # Recursively serialize any remaining datetime objects
                return self._recursively_serialize_datetime(serialized)
            except Exception as e:
                logger.warning(f"Failed to model_dump {type(asset)}: {e}")
                try:
                    asset_dict = asset.__dict__
                    return {k: self.serialize_asset(v) for k, v in asset_dict.items() if not k.startswith('_')}
                except Exception as e2:
                    logger.error(f"Could not serialize Pydantic model {type(asset)}: {e2}")
                    return str(asset)
        
        # Handle specific asset types
        elif isinstance(asset, AssetService):
            logger.debug(f"Serializing AssetService object: {asset}")
            serialized = {}
            if hasattr(asset, '__dict__'):
                return {k: self.serialize_asset(v) for k, v in asset.__dict__.items() if not k.startswith('_')}
            return str(asset)
        
        elif isinstance(asset, Ip):
            if hasattr(asset, 'ip'):
                serialized = {'ip': self.serialize_asset(asset.ip)}
                if hasattr(asset, 'ptr'):
                    serialized['ptr'] = self.serialize_asset(asset.ptr)
                return serialized
            return str(asset)
        
        # Handle collections
        elif isinstance(asset, list):
            return [self.serialize_asset(item) for item in asset]
        elif isinstance(asset, dict):
            return {str(k): self.serialize_asset(v) for k, v in asset.items()}
        
        # Handle primitives
        elif isinstance(asset, (str, int, float, bool, type(None))):
            return asset
        
        # Fallback
        else:
            logger.warning(f"Cannot properly serialize asset of type {type(asset)}")
            return str(asset)
    
    def _recursively_serialize_datetime(self, obj):
        """Recursively serialize datetime objects in any structure"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, list):
            return [self._recursively_serialize_datetime(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._recursively_serialize_datetime(v) for k, v in obj.items()}
        elif hasattr(obj, 'isoformat'):  # Handle other datetime-like objects
            return obj.isoformat()
        else:
            return obj
    
    def store_assets(self, step_name: str, assets: Dict[str, List[Any]]):
        """Store assets in the asset store"""
        for asset_type, asset_list in assets.items():
            # Skip non-asset type keys (like '_typosquat_urls')
            if not isinstance(asset_type, AssetType):
                logger.debug(f"Skipping non-asset type key: {asset_type}")
                continue
            self.asset_store.add_step_assets(step_name, asset_type.value, asset_list)


class OutputHandler:
    """Manages output collection and chunking"""
    
    def __init__(self, task_queue_client: TaskQueueClient):
        self.task_queue_client = task_queue_client
    
class AsyncDataApiClient:
    """Async HTTP client for Data API communication with connection pooling and caching"""
    
    def __init__(self, base_url: str, redis_client=None):
        self.base_url = base_url
        self.session = None
        self.connector = None
        self.redis_client = redis_client
        self.DATA_API_CHUNK_SIZE = 500
        self.cache_ttl = 3600  # 1 hour cache TTL
        self.internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.connector = aiohttp.TCPConnector(limit=100, limit_per_host=20)
        # Use longer default timeout for large asset volumes
        timeout = aiohttp.ClientTimeout(total=120, connect=15)
        
        headers = {'Content-Type': 'application/json'}
        if self.internal_api_key:
            headers['Authorization'] = f'Bearer {self.internal_api_key}'
        
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=timeout,
            headers=headers
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the HTTP session and connector"""
        if self.session:
            await self.session.close()
            self.session = None
        if self.connector:
            await self.connector.close()
            self.connector = None
        
    async def get_program_stats(self, program_name: str) -> Dict[str, Any]:
        """Get program statistics with caching"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {}
            
        cache_key = f"program_stats:{program_name}"
        
        # Try cache first
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    # Decode bytes to string before JSON parsing
                    cached_str = cached.decode('utf-8') if isinstance(cached, bytes) else cached
                    return json.loads(cached_str)
            except Exception as e:
                logger.warning(f"Cache read error for {cache_key}: {e}")
        
        try:
            async with self.session.get(f"{self.base_url}/assets/common/stats/{program_name}") as response:
                if response.status == 200:
                    result = await response.json()
                    
                    # Cache for 30 minutes (shorter TTL for stats)
                    if self.redis_client:
                        try:
                            self.redis_client.setex(cache_key, 1800, json.dumps(result))
                        except Exception as e:
                            logger.warning(f"Cache write error for {cache_key}: {e}")
                    
                    return result
                else:
                    logger.warning(f"Stats API request failed with status {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching program stats for {program_name}: {e}")
            return {}
    
    async def get_program_assets(self, asset_type: str, program_name: str, 
                                page_size: int = 100, skip: int = 0) -> Dict[str, Any]:
        """Get program assets with pagination using the new search endpoints"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {"items": [], "pagination": {}}
            
        try:
            # Map asset types to their search endpoints
            endpoint_mapping = {
                'apex-domain': '/assets/apex-domain/search',
                'subdomain': '/assets/subdomain/search',
                'ip': '/assets/ip/search',
                'service': '/assets/service/search',
                'url': '/assets/url/search',
                'certificate': '/assets/certificate/search'
            }
            
            endpoint = endpoint_mapping.get(asset_type)
            if not endpoint:
                logger.error(f"Unknown asset type: {asset_type}")
                return {"items": [], "pagination": {}}
            
            # Prepare search request payload
            search_payload = {
                "program": program_name,
                "page": (skip // page_size) + 1,
                "page_size": page_size,
                "sort_by": "updated_at",
                "sort_dir": "desc"
            }
            
            # Add asset-specific search parameters
            if asset_type == 'subdomain':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "apex_domain": None,
                    "wildcard": None,
                    "has_ips": None,
                    "has_cname": None,
                    "cname_contains": None
                })
            elif asset_type == 'ip':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "has_ptr": None,
                    "ptr_contains": None,
                    "service_provider": None
                })
            elif asset_type == 'url':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "protocol": None,
                    "status_code": None,
                    "only_root": None,
                    "technology_text": None,
                    "technology": None
                })
            elif asset_type == 'service':
                search_payload.update({
                    "ip_port_text": None,
                    "search_ip": None,
                    "exact_match_ip": None,
                    "exact_match": None,
                    "port": None,
                    "protocol": None,
                    "service_name": None,
                    "service_text": None,
                    "ip_port_or": False
                })
            elif asset_type == 'certificate':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "status": None,
                    "expiring_within_days": 30
                })
            
            async with self.session.post(
                f"{self.base_url}{endpoint}",
                json=search_payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Transform the response to match the expected format
                    if result.get("status") == "success":
                        return {
                            "items": result.get("items", []),
                            "pagination": result.get("pagination", {})
                        }
                    else:
                        logger.warning(f"Search API returned error status: {result}")
                        return {"items": [], "pagination": {}}
                else:
                    logger.warning(f"Assets search API request failed with status {response.status}")
                    return {"items": [], "pagination": {}}
        except Exception as e:
            logger.error(f"Error fetching {asset_type} assets for {program_name}: {e}")
            return {"items": [], "pagination": {}}
    
    async def get_program_metadata(self, program_name: str) -> Dict[str, Any]:
        """Get program metadata including CIDR blocks"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {}

        try:
            async with self.session.get(f"{self.base_url}/programs/{program_name}") as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    logger.warning(f"Program metadata API request failed with status {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching program metadata for {program_name}: {e}")
            return {}

    async def get_program_external_links(self, program_name: str, page_size: int = 100, page: int = 1) -> Dict[str, Any]:
        """Get program external links with pagination using the findings endpoint"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {"items": [], "pagination": {}}

        try:
            # Use the findings/external-links/search endpoint with program filter
            search_request = {
                "program": program_name,
                "page": page,
                "page_size": page_size,
                "sort_by": "url",
                "sort_dir": "asc"
            }

            logger.info(f"Fetching external links for program {program_name}, page {page}, page_size {page_size}")

            async with self.session.post(
                f"{self.base_url}/findings/external-links/search",
                json=search_request
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Retrieved {len(result.get('items', []))} external links for program {program_name}")
                    return result
                else:
                    error_text = await response.text()
                    logger.warning(f"External links API request failed with status {response.status}: {error_text}")
                    return {"items": [], "pagination": {}}
        except Exception as e:
            logger.error(f"Error fetching external links for program {program_name}: {e}")
            return {"items": [], "pagination": {}}

    async def get_program_typosquat_urls(self, program_name: str, page_size: int = 100, page: int = 1) -> Dict[str, Any]:
        """Get program typosquat URLs with pagination using the findings endpoint"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {"items": [], "pagination": {}}

        try:
            # Use the findings/typosquat-url search endpoint with program filter
            search_request = {
                "program": program_name,
                "page": page,
                "page_size": page_size,
                "sort_by": "url",
                "sort_dir": "asc"
            }

            logger.info(f"Fetching typosquat URLs for program {program_name}, page {page}, page_size {page_size}")

            async with self.session.post(
                f"{self.base_url}/findings/typosquat-url/search",
                json=search_request
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Retrieved {len(result.get('items', []))} typosquat URLs for program {program_name}")
                    return result
                else:
                    error_text = await response.text()
                    logger.warning(f"Typosquat URLs API request failed with status {response.status}: {error_text}")
                    return {"items": [], "pagination": {}}
        except Exception as e:
            logger.error(f"Error fetching typosquat URLs for program {program_name}: {e}")
            return {"items": [], "pagination": {}}

    async def get_program_typosquat_domains(self, program_name: str, limit: int = 1000000, skip: int = 0,
                                            exclude_status: Optional[str] = "dismissed",
                                            min_similarity_percent: Optional[float] = None,
                                            similarity_protected_domain: Optional[str] = None) -> Dict[str, Any]:
        """Get program typosquat domains with pagination using the findings endpoint.

        When used for task input, pass exclude_status='dismissed' so dismissed findings are not included.
        Optionally filter by minimum similarity with protected domains (0-100) and/or a specific protected domain.
        """
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return {"items": [], "pagination": {}}

        try:
            logger.info(f"Fetching typosquat domains for program {program_name}, limit {limit}, skip {skip}")

            params = {"program_name": program_name, "limit": limit, "skip": skip}
            if exclude_status:
                params["exclude_status"] = exclude_status
            if min_similarity_percent is not None:
                params["min_similarity_percent"] = min_similarity_percent
            if similarity_protected_domain:
                params["similarity_protected_domain"] = similarity_protected_domain

            async with self.session.get(
                f"{self.base_url}/findings/typosquat",
                params=params
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("status") == "success":
                        items = result.get("items", [])
                        pagination = result.get("pagination", {})
                        logger.info(f"Retrieved {len(items)} typosquat domains for program {program_name}")
                        return {"items": items, "pagination": pagination}
                    else:
                        logger.warning(f"Typosquat domains API returned error status: {result}")
                        return {"items": [], "pagination": {}}
                else:
                    error_text = await response.text()
                    logger.warning(f"Typosquat domains API request failed with status {response.status}: {error_text}")
                    return {"items": [], "pagination": {}}
        except Exception as e:
            logger.error(f"Error fetching typosquat domains for program {program_name}: {e}")
            return {"items": [], "pagination": {}}

    async def send_assets(self, step_name: str, program_name: str, workflow_id: str,
                         assets: Dict[str, List[Any]], asset_processor: AssetProcessor) -> tuple[bool, Dict[str, Any]]:
        """Send assets to the data-api service in chunks"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return False, {}

        try:
            # Convert assets to serializable format
            serialized_assets = {}
            for asset_type, asset_list in assets.items():
                # Handle both AssetType enum objects and string keys
                if hasattr(asset_type, 'value'):
                    asset_type_key = asset_type.value
                else:
                    asset_type_key = str(asset_type)

                    # Filter out None values and serialize valid assets
                    serialized_list = []
                    for asset in asset_list:
                        if asset is not None:
                            serialized_asset = asset_processor.serialize_asset(asset)
                            if serialized_asset is not None:
                                serialized_list.append(serialized_asset)
                    serialized_assets[asset_type_key] = serialized_list

            # Send assets in chunks
            success = True
            # Collect API response data
            api_responses = []
            
            for asset_type, asset_list in serialized_assets.items():
                
                # Handle special asset types differently
                if asset_type == "screenshot":
                    screenshot_success, screenshot_responses = await self._send_screenshot_assets(asset_list, program_name, workflow_id, step_name)
                    success = screenshot_success and success
                    api_responses.extend(screenshot_responses)
                elif asset_type == "typosquat_domain":
                    # Typosquat domains go to the findings endpoint
                    success = await self._send_typosquat_assets(asset_list, program_name, workflow_id, step_name) and success
                else:
                    # Add program_name to each asset and clean metadata
                    for asset in asset_list:
                        asset['program_name'] = program_name
                        asset.pop('_id', None)
                        asset.pop('created_at', None)
                        asset.pop('updated_at', None)
                    
                    # Send in chunks
                    for i in range(0, len(asset_list), self.DATA_API_CHUNK_SIZE):
                        chunk = asset_list[i:i + self.DATA_API_CHUNK_SIZE]
                        chunk_payload = {
                            "program_name": program_name,
                            "workflow_id": workflow_id,
                            "step_name": step_name,
                            "assets": {asset_type: chunk}
                        }
                        
                        # Validate JSON serialization before sending
                        try:
                            import json
                            json.dumps(chunk_payload)
                        except (TypeError, ValueError) as e:
                            logger.warning(f"JSON validation failed for chunk {i//self.DATA_API_CHUNK_SIZE + 1}: {e}")
                            # Try to fix any remaining serialization issues
                            chunk_payload = self._deep_clean_payload_for_json(chunk_payload)
                        
                        chunk_num = i // self.DATA_API_CHUNK_SIZE + 1
                        (len(asset_list) - 1) // self.DATA_API_CHUNK_SIZE + 1

                        async with self.session.post(f"{self.base_url}/assets", json=chunk_payload) as response:
                            response.raise_for_status()
                            response_data = await response.json()
                            api_responses.append(response_data)
                            logger.info(f"Successfully sent chunk {chunk_num} of {asset_type} assets")

            logger.info(f"Successfully sent all assets from step '{step_name}' to data-api")

            # Aggregate API responses to return detailed counts
            aggregated_response = self._aggregate_api_responses(api_responses)
            return success, aggregated_response

        except Exception as e:
            logger.error(f"Failed to send assets to data-api: {str(e)}")
            return False, {}
    
    def _aggregate_api_responses(self, api_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multiple API responses into a single response with combined detailed counts"""
        if not api_responses:
            return {}

        # Start with the first response as base
        aggregated = api_responses[0].copy()

        # If only one response, return it as-is
        if len(api_responses) == 1:
            return aggregated

        # Aggregate summary data from all responses
        total_assets = 0
        asset_types = {}
        detailed_counts = {}

        for response in api_responses:
            if 'summary' in response:
                summary = response['summary']

                # Aggregate total_assets
                if 'total_assets' in summary:
                    total_assets += summary['total_assets']

                # Aggregate asset_types (legacy format)
                if 'asset_types' in summary:
                    for asset_type, count in summary['asset_types'].items():
                        asset_types[asset_type] = asset_types.get(asset_type, 0) + count

                # Aggregate detailed_counts (new format)
                if 'detailed_counts' in summary:
                    for asset_type, counts in summary['detailed_counts'].items():
                        if asset_type not in detailed_counts:
                            detailed_counts[asset_type] = counts.copy()
                        else:
                            # Sum up the counts
                            current = detailed_counts[asset_type]
                            current['total'] += counts['total']
                            current['created'] += counts['created']
                            current['updated'] += counts['updated']
                            current['skipped'] += counts.get('skipped', 0)
                            current['failed'] += counts['failed']

        # Update the aggregated response
        if 'summary' in aggregated:
            aggregated['summary']['total_assets'] = total_assets
            aggregated['summary']['asset_types'] = asset_types
            aggregated['summary']['detailed_counts'] = detailed_counts

        logger.debug(f"Aggregated {len(api_responses)} API responses into combined summary")
        return aggregated

    async def _send_screenshot_assets(self, asset_list: List[Any], program_name: str,
                                    workflow_id: str, step_name: str) -> tuple[bool, List[Dict[str, Any]]]:
        """Send screenshot assets to the specific screenshot endpoint"""
        try:
            success = True
            api_responses = []

            for asset in asset_list:
                # Extract screenshot data
                url = asset.get('url', '')
                image_data = asset.get('image_data', '')
                filename = asset.get('filename', 'screenshot.png')
                extracted_text = asset.get('extracted_text')

                if not url or not image_data:
                    logger.warning("Invalid screenshot asset: missing url or image_data")
                    continue

                # Decode base64 image data
                import base64
                try:
                    image_bytes = base64.b64decode(image_data)
                except Exception as e:
                    logger.error(f"Failed to decode image data for {url}: {e}")
                    continue

                # Prepare form data for screenshot upload
                import aiohttp
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename=filename, content_type='image/png')
                data.add_field('url', url)
                data.add_field('program_name', program_name)
                data.add_field('workflow_id', workflow_id)
                data.add_field('step_name', step_name)
                data.add_field('bucket_type', 'findings')
                if extracted_text:
                    data.add_field('extracted_text', extracted_text)

                # Send to screenshot endpoint
                if not self.session:
                    logger.error("Session not initialized for screenshot upload")
                    return False, []
                async with self.session.post(f"{self.base_url}/assets/screenshot", data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        file_id = result.get('data', {}).get('file_id')
                        logger.info(f"Successfully uploaded screenshot for {url}, file_id: {file_id}")

                        # Create a synthetic API response in the format expected by aggregation
                        # Since screenshot endpoint doesn't return detailed counts, we create them
                        synthetic_response = {
                            "summary": {
                                "total_assets": 1,
                                "created_assets": 1,
                                "updated_assets": 0,
                                "skipped_assets": 0,
                                "failed_assets": 0,
                                "detailed_counts": {
                                    "screenshot": {
                                        "total": 1,
                                        "created": 1,
                                        "updated": 0,
                                        "skipped": 0,
                                        "failed": 0,
                                        "created_assets": [{"url": url, "filename": filename}],
                                        "updated_assets": [],
                                        "skipped_assets": [],
                                        "failed_assets": [],
                                        "errors": []
                                    }
                                }
                            },
                            "file_id": file_id
                        }
                        api_responses.append(synthetic_response)
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to upload screenshot for {url}: {response.status} - {error_text}")
                        success = False

                        # Add failed response for aggregation
                        failed_response = {
                            "summary": {
                                "total_assets": 1,
                                "created_assets": 0,
                                "updated_assets": 0,
                                "skipped_assets": 0,
                                "failed_assets": 1,
                                "detailed_counts": {
                                    "screenshot": {
                                        "total": 1,
                                        "created": 0,
                                        "updated": 0,
                                        "skipped": 0,
                                        "failed": 1,
                                        "created_assets": [],
                                        "updated_assets": [],
                                        "skipped_assets": [],
                                        "failed_assets": [{"url": url, "filename": filename}],
                                        "errors": [f"Upload failed: {response.status}"]
                                    }
                                }
                            }
                        }
                        api_responses.append(failed_response)

            return success, api_responses

        except Exception as e:
            logger.error(f"Error sending screenshot assets: {e}")
            return False, []
    
    def _deep_clean_payload_for_json(self, obj):
        """Deep clean object to ensure JSON serialization"""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                try:
                    cleaned[str(k)] = self._deep_clean_payload_for_json(v)
                except Exception as e:
                    logger.warning(f"Failed to serialize key {k}: {e}")
                    cleaned[str(k)] = str(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._deep_clean_payload_for_json(item) for item in obj]
        elif hasattr(obj, 'isoformat'):
            # Handle datetime objects
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # Handle objects with __dict__
            return self._deep_clean_payload_for_json(obj.__dict__)
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert anything else to string
            return str(obj)

    async def store_typosquat_url(self, url_data: Dict[str, Any]) -> bool:
        """Store a typosquat URL to the /findings/typosquat-url endpoint"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return False
            
        try:
            async with self.session.post(f"{self.base_url}/findings/typosquat-url", json=url_data) as response:
                if response.status == 200:
                    logger.debug(f"Successfully stored typosquat URL: {url_data.get('url', 'unknown')}")
                    return True
                else:
                    error_text = await response.text()
                    logger.warning(f"Failed to store typosquat URL {url_data.get('url', 'unknown')}: {response.status} - {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Error storing typosquat URL {url_data.get('url', 'unknown')}: {e}")
            return False
    
    async def store_typosquat_urls_batch(self, urls: List[Dict[str, Any]]) -> bool:
        """Store multiple typosquat URLs in batch"""
        if not self.session:
            logger.error("Session not initialized. Use async context manager.")
            return False
            
        try:
            success = True
            for url_data in urls:
                result = await self.store_typosquat_url(url_data)
                if not result:
                    success = False
            
            return success
        except Exception as e:
            logger.error(f"Error in batch typosquat URL storage: {e}")
            return False

    async def _send_typosquat_assets(self, asset_list: List[Any], program_name: str, 
                                    workflow_id: str, step_name: str) -> bool:
        """Send typosquat assets to the findings API endpoint"""
        try:
            success = True
            
            for asset in asset_list:
                # Convert asset to dictionary if it's an object
                if hasattr(asset, '__dict__'):
                    asset_dict = asset.__dict__.copy()
                elif isinstance(asset, dict):
                    asset_dict = asset.copy()
                else:
                    logger.warning(f"Unexpected asset type: {type(asset)}")
                    continue
                
                # Add metadata
                asset_dict['program_name'] = program_name
                asset_dict.pop('_id', None)
                asset_dict.pop('created_at', None)
                asset_dict.pop('updated_at', None)
                
                # Clean the payload for JSON serialization BEFORE validation
                asset_dict = self._deep_clean_payload_for_json(asset_dict)
                # Validate JSON serialization after cleaning
                try:
                    import json
                    json.dumps(asset_dict)
                except (TypeError, ValueError) as e:
                    logger.warning(f"JSON validation still failed after cleaning for typosquat asset: {e}")
                    # This shouldn't happen now, but log if it does
                
                # Send to typosquat findings endpoint
                try:
                    async with self.session.post(
                        f"{self.base_url}/findings/typosquat", 
                        json=asset_dict
                    ) as response:
                        if response.status == 200:
                            await response.json()
                            logger.info(f"Successfully sent typosquat finding: {asset_dict.get('typo_domain', 'unknown')}")
                        else:
                            error_text = await response.text()
                            logger.error(f"Failed to send typosquat finding: {response.status} - {error_text}")
                            success = False
                            
                except Exception as e:
                    logger.error(f"Error sending typosquat finding {asset_dict.get('typo_domain', 'unknown')}: {e}")
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending typosquat assets: {e}")
            return False


class SyncDataApiClient:
    """Synchronous fallback client for Data API communication"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.DATA_API_CHUNK_SIZE = 500
        self.internal_api_key = os.getenv('INTERNAL_SERVICE_API_KEY', '')

    def _deep_clean_for_json(self, obj):
        """Deep clean object to ensure JSON serialization"""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                try:
                    cleaned[str(k)] = self._deep_clean_for_json(v)
                except Exception as e:
                    logger.warning(f"Failed to serialize key {k}: {e}")
                    cleaned[str(k)] = str(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._deep_clean_for_json(item) for item in obj]
        elif hasattr(obj, 'isoformat'):
            # Handle datetime objects
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # Handle objects with __dict__
            return self._deep_clean_for_json(obj.__dict__)
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert anything else to string
            return str(obj)

    def get_program_assets(self, asset_type: str, program_name: str, 
                          page_size: int = 100, skip: int = 0) -> Dict[str, Any]:
        """Get program assets with pagination using the new search endpoints (synchronous version)"""
        try:
            # Map asset types to their search endpoints
            endpoint_mapping = {
                'apex-domain': '/assets/apex-domain/search',
                'subdomain': '/assets/subdomain/search',
                'ip': '/assets/ip/search',
                'service': '/assets/service/search',
                'url': '/assets/url/search',
                'certificate': '/assets/certificate/search'
            }
            
            endpoint = endpoint_mapping.get(asset_type)
            if not endpoint:
                logger.error(f"Unknown asset type: {asset_type}")
                return {"items": [], "pagination": {}}
            
            # Prepare search request payload
            search_payload = {
                "program": program_name,
                "page": (skip // page_size) + 1,
                "page_size": page_size,
                "sort_by": "updated_at",
                "sort_dir": "desc"
            }
            
            # Add asset-specific search parameters
            if asset_type == 'subdomain':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "apex_domain": None,
                    "wildcard": None,
                    "has_ips": None,
                    "has_cname": None,
                    "cname_contains": None
                })
            elif asset_type == 'ip':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "has_ptr": None,
                    "ptr_contains": None,
                    "service_provider": None
                })
            elif asset_type == 'url':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "protocol": None,
                    "status_code": None,
                    "only_root": None,
                    "technology_text": None,
                    "technology": None
                })
            elif asset_type == 'service':
                search_payload.update({
                    "ip_port_text": None,
                    "search_ip": None,
                    "exact_match_ip": None,
                    "exact_match": None,
                    "port": None,
                    "protocol": None,
                    "service_name": None,
                    "service_text": None,
                    "ip_port_or": False
                })
            elif asset_type == 'certificate':
                search_payload.update({
                    "search": None,
                    "exact_match": None,
                    "status": None,
                    "expiring_within_days": 30
                })
            
            headers = {}
            if self.internal_api_key:
                headers['Authorization'] = f'Bearer {self.internal_api_key}'
            
            response = requests.post(
                f"{self.base_url}{endpoint}",
                json=search_payload,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                # Transform the response to match the expected format
                if result.get("status") == "success":
                    return {
                        "items": result.get("items", []),
                        "pagination": result.get("pagination", {})
                    }
                else:
                    logger.warning(f"Search API returned error status: {result}")
                    return {"items": [], "pagination": {}}
            else:
                logger.warning(f"Assets search API request failed with status {response.status_code}")
                return {"items": [], "pagination": {}}
                
        except Exception as e:
            logger.error(f"Error fetching {asset_type} assets for {program_name}: {e}")
            return {"items": [], "pagination": {}}
    
    def send_assets(self, step_name: str, program_name: str, workflow_id: str,
                   assets: Dict[str, List[Any]], asset_processor: AssetProcessor) -> tuple[bool, Dict[str, Any]]:
        """Send assets to the data-api service in chunks (synchronous version)"""
        try:
            # Check if assets is empty and return early
            if not assets:
                return True, {"status": "success", "message": "No assets to send"}

            # Convert assets to serializable format
            serialized_assets = {}
            for asset_type, asset_list in assets.items():
                # Handle both AssetType enum objects and string keys
                if hasattr(asset_type, 'value'):
                    asset_type_key = asset_type.value
                else:
                    asset_type_key = str(asset_type)

                # Filter out None values and serialize valid assets
                serialized_list = []
                for asset in asset_list:
                    if asset is not None:
                        serialized_asset = asset_processor.serialize_asset(asset)
                        if serialized_asset is not None:
                            serialized_list.append(serialized_asset)
                serialized_assets[asset_type_key] = serialized_list
            
            # Send assets in chunks
            success = True
            # Collect API response data
            api_responses = []

            for asset_type, asset_list in serialized_assets.items():
                
                # Handle special asset types differently
                if asset_type == "screenshot":
                    screenshot_success, screenshot_responses = self._send_screenshot_assets(asset_list, program_name, workflow_id, step_name)
                    success = screenshot_success and success
                    api_responses.extend(screenshot_responses)
                elif asset_type == "typosquat_domain":
                    success = self._send_typosquat_assets(asset_list, program_name, workflow_id, step_name) and success
                else:
                    # Add program_name to each asset and clean metadata
                    # for asset in asset_list:
                    #     asset['program_name'] = program_name
                    #     asset.pop('_id', None)
                    #     asset.pop('created_at', None)
                    #     asset.pop('updated_at', None)
                    
                    # Send in chunks
                    for i in range(0, len(asset_list), self.DATA_API_CHUNK_SIZE):
                        chunk = asset_list[i:i + self.DATA_API_CHUNK_SIZE]
                        chunk_payload = {
                            "program_name": program_name,
                            "assets": {asset_type: chunk}
                        }
                        
                        # Validate JSON serialization before sending
                        try:
                            import json
                            json.dumps(chunk_payload)
                        except (TypeError, ValueError) as e:
                            logger.warning(f"JSON validation failed for chunk {i//self.DATA_API_CHUNK_SIZE + 1}: {e}")
                            # Try to fix any remaining serialization issues
                            chunk_payload = self._deep_clean_payload_for_json(chunk_payload)
                        
                        chunk_num = i // self.DATA_API_CHUNK_SIZE + 1
                        (len(asset_list) - 1) // self.DATA_API_CHUNK_SIZE + 1
                        
                        
                        headers = {}
                        if self.internal_api_key:
                            headers['Authorization'] = f'Bearer {self.internal_api_key}'
                        response = requests.post(f"{self.base_url}/assets", json=chunk_payload, headers=headers)
                        response.raise_for_status()
                        response_data = response.json()
                        api_responses.append(response_data)
                        logger.info(f"Successfully sent chunk {chunk_num} of {asset_type} assets")
            
            logger.info(f"Successfully sent all assets from step '{step_name}' to data-api")

            # Aggregate API responses to return detailed counts
            aggregated_response = self._aggregate_api_responses(api_responses)
            return success, aggregated_response

        except Exception as e:
            logger.error(f"Failed to send assets to data-api: {str(e)}")
            return False, {}
    
    def send_typosquat_findings(self, step_name: str, program_name: str, workflow_id: str,
                               typosquat_findings: List[Any], asset_processor: AssetProcessor) -> tuple[bool, Dict[str, Any]]:
        """Send typosquat findings to dedicated typosquat findings endpoint (synchronous version)"""
        try:
            if not typosquat_findings:
                logger.info("No typosquat findings to send")
                return True, {}

            logger.info(f"Sending {len(typosquat_findings)} typosquat findings via dedicated endpoint")

            # Clean metadata from all findings
            for finding in typosquat_findings:
                if isinstance(finding, dict):
                    finding.pop('_id', None)
                    finding.pop('created_at', None)
                    finding.pop('updated_at', None)
                # Serialize findings using the asset processor
                if hasattr(finding, '__dict__'):
                    finding = asset_processor.serialize_asset(finding)

            # Add program_name to each finding
            for finding in typosquat_findings:
                finding['program_name'] = program_name

            # Determine batch size
            batch_size = min(self.DATA_API_CHUNK_SIZE, 100)

            api_responses = []
            success = True

            # Send in chunks to prevent oversized HTTP payloads
            for i in range(0, len(typosquat_findings), batch_size):
                chunk = typosquat_findings[i:i + batch_size]

                chunk_payload = {
                    "program_name": program_name,
                    "workflow_id": workflow_id,
                    "step_name": step_name,
                    "findings": chunk
                }

                # Validate JSON serialization before sending
                try:
                    import json
                    json.dumps(chunk_payload)
                except (TypeError, ValueError) as e:
                    logger.warning(f"JSON validation failed for typosquat chunk {i//batch_size + 1}: {e}")
                    # Try to fix serialization issues
                    chunk_payload = self._deep_clean_payload_for_json(chunk_payload)

                # Send chunk to typosquat findings endpoint
                try:
                    import requests
                    url = f"{self.base_url}/findings/typosquat"
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }

                    logger.debug(f"Sending typosquat chunk {i//batch_size + 1} with {len(chunk)} findings")

                    response = requests.post(
                        url,
                        json=chunk_payload,
                        headers=headers,
                        timeout=self.timeout
                    )

                    if response.status_code == 200:
                        api_response = response.json()
                        api_responses.append(api_response)
                        logger.debug(f"Typosquat chunk {i//batch_size + 1} sent successfully")
                    else:
                        logger.warning(f"Failed to send typosquat chunk {i//batch_size + 1}: {response.status_code} - {response.text}")
                        success = False

                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error sending typosquat chunk {i//batch_size + 1}: {e}")
                    success = False
                except Exception as e:
                    logger.error(f"Unexpected error sending typosquat chunk {i//batch_size + 1}: {e}")
                    success = False

            # Aggregate API responses to return detailed counts
            aggregated_response = self._aggregate_api_responses(api_responses)
            return success, aggregated_response

        except Exception as e:
            logger.error(f"Failed to send typosquat findings to typosquat endpoint: {str(e)}")
            return False, {}
    
    def _send_screenshot_assets(self, asset_list: List[Any], program_name: str,
                               workflow_id: str, step_name: str) -> tuple[bool, List[Dict[str, Any]]]:
        """Send screenshot assets to the specific screenshot endpoint"""
        try:
            success = True
            api_responses = []

            for asset in asset_list:
                # Extract screenshot data
                url = asset.get('url', '')
                image_data = asset.get('image_data', '')
                filename = asset.get('filename', 'screenshot.png')
                extracted_text = asset.get('extracted_text')

                if not url or not image_data:
                    logger.warning("Invalid screenshot asset: missing url or image_data")
                    continue

                # Decode base64 image data
                import base64
                try:
                    image_bytes = base64.b64decode(image_data)
                except Exception as e:
                    logger.error(f"Failed to decode image data for {url}: {e}")
                    continue

                # Prepare form data for screenshot upload
                files = {'file': (filename, image_bytes, 'image/png')}
                data = {
                    'url': url,
                    'program_name': program_name,
                    'workflow_id': workflow_id,
                    'step_name': step_name,
                    'bucket_type': 'findings'
                }
                if extracted_text:
                    data['extracted_text'] = extracted_text

                # Send to screenshot endpoint
                headers = {}
                if self.internal_api_key:
                    headers['Authorization'] = f'Bearer {self.internal_api_key}'

                response = requests.post(f"{self.base_url}/assets/screenshot", files=files, data=data, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    file_id = result.get('data', {}).get('file_id')
                    logger.info(f"Successfully uploaded screenshot for {url}, file_id: {file_id}")

                    # Create a synthetic API response in the format expected by aggregation
                    # Since screenshot endpoint doesn't return detailed counts, we create them
                    synthetic_response = {
                        "summary": {
                            "total_assets": 1,
                            "created_assets": 1,
                            "updated_assets": 0,
                            "skipped_assets": 0,
                            "failed_assets": 0,
                            "detailed_counts": {
                                "screenshot": {
                                    "total": 1,
                                    "created": 1,
                                    "updated": 0,
                                    "skipped": 0,
                                    "failed": 0,
                                    "created_assets": [{"url": url, "filename": filename}],
                                    "updated_assets": [],
                                    "skipped_assets": [],
                                    "failed_assets": [],
                                    "errors": []
                                }
                            }
                        },
                        "file_id": file_id
                    }
                    api_responses.append(synthetic_response)
                else:
                    logger.error(f"Failed to upload screenshot for {url}: {response.status_code} - {response.text}")
                    success = False

                    # Add failed response for aggregation
                    failed_response = {
                        "summary": {
                            "total_assets": 1,
                            "created_assets": 0,
                            "updated_assets": 0,
                            "skipped_assets": 0,
                            "failed_assets": 1,
                            "detailed_counts": {
                                "screenshot": {
                                    "total": 1,
                                    "created": 0,
                                    "updated": 0,
                                    "skipped": 0,
                                    "failed": 1,
                                    "created_assets": [],
                                    "updated_assets": [],
                                    "skipped_assets": [],
                                    "failed_assets": [{"url": url, "filename": filename}],
                                    "errors": [f"Upload failed: {response.status_code}"]
                                }
                            }
                        }
                    }
                    api_responses.append(failed_response)

            return success, api_responses

        except Exception as e:
            logger.error(f"Error sending screenshot assets: {e}")
            return False, []

    def _send_typosquat_assets(self, asset_list: List[Any], program_name: str) -> bool:
        """Send typosquat assets to the findings API endpoint (synchronous version)"""
        try:
            success = True
            #for asset in asset_list:
                # Convert asset to dictionary if it's an object
            # if hasattr(asset, '__dict__'):
            #     asset_dict = asset.__dict__.copy()
            # elif isinstance(asset, dict):
            #     asset_dict = asset.copy()
            # else:
            #     logger.warning(f"Unexpected asset type: {type(asset)}")
            
            # Add metadata
            # asset_dict['program_name'] = program_name
            # asset_dict.pop('_id', None)
            # asset_dict.pop('created_at', None)
            # asset_dict.pop('updated_at', None)
            
            # Clean the payload for JSON serialization BEFORE validation
            #asset_dict = self._deep_clean_payload_for_json(asset_dict)
            # Validate JSON serialization after cleaning
            payload = {
                "program_name": program_name,
                "findings": {"typosquat_domain": asset_list}
            }
            # try:
            #     import json
            #     json.dumps(asset_dict)
            # except (TypeError, ValueError) as e:
            #     logger.warning(f"JSON validation still failed after cleaning for typosquat asset: {e}")
            #     # This shouldn't happen now, but log if it does
            
            # Send to typosquat findings endpoint
            headers = {}
            if self.internal_api_key:
                headers['Authorization'] = f'Bearer {self.internal_api_key}'
            response = requests.post(f"{self.base_url}/findings/typosquat", json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(f"Successfully sent typosquat finding: {payload.get('findings', 'unknown')}")
            else:
                logger.error(f"Failed to send typosquat finding: {response.status_code} - {response.text}")
                success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending typosquat assets: {e}")
            return False
    
    def _deep_clean_payload_for_json(self, obj):
        """Deep clean object to ensure JSON serialization"""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                try:
                    cleaned[str(k)] = self._deep_clean_payload_for_json(v)
                except Exception as e:
                    logger.warning(f"Failed to serialize key {k}: {e}")
                    cleaned[str(k)] = str(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._deep_clean_payload_for_json(item) for item in obj]
        elif hasattr(obj, 'isoformat'):
            # Handle datetime objects
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # Handle objects with __dict__
            return self._deep_clean_payload_for_json(obj.__dict__)
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert anything else to string
            return str(obj)
    
    def store_typosquat_url(self, url_data: Dict[str, Any]) -> bool:
        """Store a typosquat URL to the /findings/typosquat-url endpoint (synchronous version)"""
        try:
            headers = {}
            if self.internal_api_key:
                headers['Authorization'] = f'Bearer {self.internal_api_key}'
            
            response = requests.post(f"{self.base_url}/findings/typosquat-url", json=url_data, headers=headers, timeout=30)
            if response.status_code == 200:
                logger.debug(f"Successfully stored typosquat URL: {url_data.get('url', 'unknown')}")
                return True
            else:
                logger.warning(f"Failed to store typosquat URL {url_data.get('url', 'unknown')}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error storing typosquat URL {url_data.get('url', 'unknown')}: {e}")
            return False
    
    def post_broken_link_findings(self, broken_link_findings: List[Any], program_name: str) -> bool:
        """
        Post broken link findings to /findings/broken-links endpoint (synchronous version).

        Args:
            broken_link_findings: List of broken link findings to post
            program_name: Name of the program for the findings

        Returns:
            True if successful, False otherwise
        """
        if not broken_link_findings:
            logger.warning("No broken link findings to post")
            return True

        try:
            # Convert findings objects to dictionaries for JSON serialization
            serializable_findings = []
            for finding in broken_link_findings:
                if isinstance(finding, dict):
                    serializable_findings.append(self._deep_clean_for_json(finding))
                elif hasattr(finding, 'model_dump'):
                    finding_dict = finding.model_dump(by_alias=True, exclude_none=True)
                    serializable_findings.append(self._deep_clean_for_json(finding_dict))
                elif hasattr(finding, 'to_dict'):
                    serializable_findings.append(self._deep_clean_for_json(finding.to_dict()))
                elif hasattr(finding, '__dict__'):
                    serializable_findings.append(self._deep_clean_for_json(finding.__dict__))
                else:
                    serializable_findings.append(self._deep_clean_for_json(finding))

            finding_count = len(serializable_findings)
            dynamic_timeout = min(max(30, finding_count * 2), 300)

            logger.debug(f"Posting {finding_count} broken link findings to /findings/broken-links for program: {program_name}")

            headers = {}
            if self.internal_api_key:
                headers['Authorization'] = f'Bearer {self.internal_api_key}'

            # Post each finding individually
            success_count = 0
            for finding in serializable_findings:
                try:
                    finding['program_name'] = program_name
                    response = requests.post(
                        f"{self.base_url}/findings/broken-links",
                        json=finding,
                        headers=headers,
                        timeout=dynamic_timeout
                    )
                    if response.status_code in [200, 201]:
                        success_count += 1
                    else:
                        logger.error(f"API error posting broken link finding: {response.status_code} - {response.text}")
                except Exception as e:
                    logger.error(f"Error posting broken link finding: {e}")

            if success_count == finding_count:
                logger.debug(f"All {finding_count} broken link findings posted successfully")
                return True
            else:
                logger.warning(f"Posted {success_count}/{finding_count} broken link findings")
                return False

        except requests.RequestException as e:
            logger.error(f"Network error posting broken link findings: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error posting broken link findings: {e}")
            return False
    
    def _aggregate_api_responses(self, api_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multiple API responses into a single response with combined detailed counts"""
        if not api_responses:
            return {}

        # Start with the first response as base
        aggregated = api_responses[0].copy()

        # If only one response, return it as-is
        if len(api_responses) == 1:
            return aggregated

        # Aggregate summary data from all responses
        total_assets = 0
        asset_types = {}
        detailed_counts = {}

        for response in api_responses:
            if 'summary' in response:
                summary = response['summary']

                # Aggregate total_assets
                if 'total_assets' in summary:
                    total_assets += summary['total_assets']

                # Aggregate asset_types (legacy format)
                if 'asset_types' in summary:
                    for asset_type, count in summary['asset_types'].items():
                        asset_types[asset_type] = asset_types.get(asset_type, 0) + count

                # Aggregate detailed_counts (new format)
                if 'detailed_counts' in summary:
                    for asset_type, counts in summary['detailed_counts'].items():
                        if asset_type not in detailed_counts:
                            detailed_counts[asset_type] = counts.copy()
                        else:
                            # Sum up the counts
                            current = detailed_counts[asset_type]
                            current['total'] += counts['total']
                            current['created'] += counts['created']
                            current['updated'] += counts['updated']
                            current['skipped'] += counts.get('skipped', 0)
                            current['failed'] += counts['failed']

        # Update the aggregated response
        if 'summary' in aggregated:
            aggregated['summary']['total_assets'] = total_assets
            aggregated['summary']['asset_types'] = asset_types
            aggregated['summary']['detailed_counts'] = detailed_counts

        logger.debug(f"Aggregated {len(api_responses)} API responses into combined summary")
        return aggregated