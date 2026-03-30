#!/usr/bin/env python3
"""
Reusable WorkerJobManager for spawning and managing worker tasks.

This class consolidates the common patterns for:
- Spawning worker jobs via KubernetesService
- Setting up NATS output handlers
- Waiting for job completion with timeout
- Collecting and aggregating results
- Batch processing with progress tracking
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, Union
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class JobResult:
    """Container for job execution results"""

    def __init__(self, task_id: str, job_name: str, status: str = "pending"):
        self.task_id = task_id
        self.job_name = job_name
        self.status = status  # pending, running, completed, failed, timeout
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

        # Task information for output parsing
        self.task_name: Optional[str] = None
        self.task_params: Optional[Dict[str, Any]] = None
        
    @property
    def duration(self) -> Optional[float]:
        """Get job duration in seconds"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
        
    @property
    def is_completed(self) -> bool:
        """Check if job has completed (successfully or failed)"""
        return self.status in ["completed", "failed", "timeout"]
        
    @property
    def is_successful(self) -> bool:
        """Check if job completed successfully"""
        return self.status == "completed" and self.output is not None


class BatchResult:
    """Container for batch execution results"""
    
    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        self.jobs: Dict[str, JobResult] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
    def add_job(self, job_result: JobResult):
        """Add a job result to this batch"""
        self.jobs[job_result.task_id] = job_result
        
    @property
    def total_jobs(self) -> int:
        return len(self.jobs)
        
    @property
    def completed_jobs(self) -> int:
        return sum(1 for job in self.jobs.values() if job.is_completed)
        
    @property
    def successful_jobs(self) -> int:
        return sum(1 for job in self.jobs.values() if job.is_successful)
        
    @property
    def failed_jobs(self) -> int:
        return sum(1 for job in self.jobs.values() if job.status in ["failed", "timeout"])
        
    @property
    def is_completed(self) -> bool:
        return self.completed_jobs == self.total_jobs
        
    @property
    def success_rate(self) -> float:
        if self.total_jobs == 0:
            return 1.0
        return self.successful_jobs / self.total_jobs
        
    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class WorkerJobManager:
    """
    Reusable manager for spawning and monitoring worker jobs.
    
    This class provides a unified interface for:
    - Single job spawning and monitoring
    - Batch job processing
    - Output collection via NATS
    - Progress tracking and error handling
    """
    
    def __init__(self, task_queue_client=None, k8s_service=None):
        """
        Initialize the WorkerJobManager.
        
        Args:
            task_queue_client: TaskQueueClient for NATS communication
            k8s_service: KubernetesService for job queuing
        """
        self.task_queue_client = task_queue_client
        self.k8s_service = k8s_service
        
        # Job tracking
        self.active_jobs: Dict[str, JobResult] = {}
        self.active_batches: Dict[str, BatchResult] = {}
        self.output_handlers: Dict[str, Callable] = {}
        
        # Configuration
        self.default_timeout = 1800  # 30 minutes
        self.check_interval = 2  # seconds
        self.batch_spawn_delay = 0.5  # seconds between batch spawns
        
        # Environment context - refresh from current environment
        self._refresh_environment_context()
        
        logger.debug(f"WorkerJobManager initialized - workflow_id: {self.workflow_id}, execution_id: {self.execution_id}")
    
    def _refresh_environment_context(self):
        """Refresh environment context from current environment variables"""
        self.workflow_id = os.getenv('WORKFLOW_ID', 'unknown')
        self.execution_id = os.getenv('EXECUTION_ID', self.workflow_id)
        self.program_name = os.getenv('PROGRAM_NAME', 'default')
    
    def _ensure_k8s_service(self):
        """Lazily initialize KubernetesService if not provided"""
        if not self.k8s_service:
            try:
                from services.kubernetes import KubernetesService
                self.k8s_service = KubernetesService()
                logger.debug("Initialized KubernetesService for WorkerJobManager")
            except Exception as e:
                logger.error(f"Failed to initialize KubernetesService: {e}")
                raise RuntimeError("KubernetesService required but not available")
    
    def _make_rfc1123_compliant(self, name: str) -> str:
        """Make a name RFC 1123 compliant for Kubernetes"""
        # Replace underscores with hyphens
        safe_name = name.replace('_', '-').lower()
        # Remove any non-alphanumeric characters except hyphens
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '-')
        # Ensure it starts and ends with alphanumeric characters
        safe_name = safe_name.strip('-')
        # If empty, use default name
        if not safe_name:
            safe_name = 'job'
        # Ensure it starts with a letter (not a digit)
        if safe_name and not safe_name[0].isalpha():
            safe_name = 'job-' + safe_name
        # Ensure it ends with alphanumeric  
        if safe_name and not safe_name[-1].isalnum():
            safe_name = safe_name + '-job'
        return safe_name
    
    def _build_job_params(self, task_name: str, command: str, 
                         timeout: int = None, **kwargs) -> Dict[str, Any]:
        """
        Build standardized job parameters for worker tasks.
        
        Args:
            task_name: Name of the task to spawn
            command: Command to execute
            timeout: Job timeout in seconds
            **kwargs: Additional job parameters
            
        Returns:
            Job parameters dictionary
        """
        safe_task_name = self._make_rfc1123_compliant(task_name)
        job_name = kwargs.get('job_name', f"{safe_task_name}-{str(uuid.uuid4())[:8]}")
        
        job_params = {
            "workflow_id": self.execution_id,  # Use execution_id for output routing
            "workflow_name": self.program_name,
            "program_name": self.program_name,
            "task_name": safe_task_name,
            "step_num": kwargs.get('step_num', 0),
            "step_name": kwargs.get('step_name', f"{safe_task_name}-{int(time.time())}"),
            "job_name": job_name,
            "image": os.getenv('WORKER_IMAGE', 'worker:latest'),
            "image_pull_policy": os.getenv('IMAGE_PULL_POLICY', 'Always'),
            "args": [command],  # Command string passed to command_wrapper.py
            "timeout": timeout or self.default_timeout,
            "env": kwargs.get('env', [])
        }
        
        # Ensure NATS output routing is configured
        env_vars = job_params.get("env", [])
        # Add required environment variables for output routing
        required_env = [
            {"name": "OUTPUT_QUEUE_SUBJECT", "value": f"tasks.output.{self.execution_id}"},
            {"name": "EXECUTION_ID", "value": self.execution_id},
            {"name": "WORKFLOW_ID", "value": self.workflow_id},
            {"name": "PROGRAM_NAME", "value": self.program_name}
        ]
        
        for env_var in required_env:
            # Only add if not already present
            if not any(e.get("name") == env_var["name"] for e in env_vars):
                env_vars.append(env_var)
        
        job_params["env"] = env_vars
        
        # Update with any additional parameters
        job_params.update(kwargs)
        
        return job_params
    
    def _setup_output_handler(self, task_id: str, job_result: JobResult, result_processor: Optional[Callable] = None, batch_num: int = 0):
        """Set up NATS output handler for a job"""
        if not self.task_queue_client:
            logger.warning(f"No task_queue_client available for output handling of job {task_id}")
            return

        def output_handler(output):
            logger.debug(f"Received output from job {task_id}")
            job_result.output = output
            job_result.status = "completed"
            job_result.end_time = time.time()
            logger.debug(f"Job {task_id} marked as completed")

            # If we have a result processor for progressive streaming, call it immediately
            if result_processor and output:
                try:
                    logger.debug(f"Calling result processor for completed job {task_id}")
                    result_processor({task_id: output}, batch_num)
                except Exception as e:
                    logger.error(f"Error in result processor for job {task_id}: {e}")

        self.task_queue_client.output_handlers[task_id] = output_handler
        self.output_handlers[task_id] = output_handler
        logger.debug(f"Set up output handler for job {task_id}")
    
    async def spawn_task_batch(self, task_name: str, input_data_list: List[Any],
                              task_params: Dict[str, Any] = None, batch_size: int = 20,
                              timeout: int = None, process_incrementally: bool = False,
                              result_processor: Optional[Callable] = None,
                              parse_output: bool = False,
                              sequential_batches: bool = False,
                              **kwargs) -> BatchResult:
        """
        Spawn multiple worker jobs for a specific task, delegating command generation to the task.

        Args:
            task_name: Name of the task to spawn (e.g., 'resolve_ip')
            input_data_list: List of input data chunks, each becomes a separate job
            task_params: Parameters to pass to the task's get_command method
            batch_size: Number of jobs to spawn per batch
            timeout: Job timeout in seconds
            process_incrementally: Whether to process results after each batch
            result_processor: Optional function to process results incrementally
            parse_output: Whether to use the task's parse_output method to return parsed assets
            sequential_batches: Whether to process batches sequentially (wait for each batch to complete before starting the next)
            **kwargs: Additional job parameters

        Returns:
            BatchResult object for tracking the entire batch
        """
        # Import task dynamically to get the actual task class
        try:
            task_class = self._get_task_class(task_name)
            task_instance = task_class()
        except Exception as e:
            logger.error(f"Failed to load task {task_name}: {e}")
            raise RuntimeError(f"Cannot spawn jobs for unknown task: {task_name}")
        
        # Generate commands using the task's get_command method
        commands = []
        for i, input_data in enumerate(input_data_list):
            try:
                command = task_instance.get_command(input_data, task_params)

                # Handle both single commands and arrays of commands
                if isinstance(command, list):
                    commands.extend(command)
                else:
                    commands.append(command)
            except Exception as e:
                logger.error(f"Failed to generate command for task {task_name} with input {input_data}: {e}")
                logger.error(f"Input data type: {type(input_data)}")
                if hasattr(input_data, '__len__'):
                    logger.error(f"Input data length: {len(input_data)}")
                raise RuntimeError(f"Command generation failed for task {task_name}")

        logger.info(f"Generated {len(commands)} commands for task {task_name}")

        # Store task information for later use if parsing is enabled
        if parse_output:
            kwargs['task_params'] = task_params

        # Delegate to the existing spawn_batch method
        return await self.spawn_batch(
            task_name=task_name,
            commands=commands,
            batch_size=batch_size,
            timeout=timeout,
            process_incrementally=process_incrementally,
            result_processor=result_processor,
            parse_output=parse_output,
            sequential_batches=sequential_batches,
            **kwargs
        )
    
    def _get_task_class(self, task_name: str):
        """Dynamically import and return the task class"""
        try:
            # Try multiple import paths to handle different deployment environments
            import_paths = [
                # Production environment (from /app)
                f"tasks.{task_name}",
                # Development environment (from runner/app)
                f"runner.app.tasks.{task_name}",
                # Full path fallback
                f"src.runner.app.tasks.{task_name}",
            ]

            for module_name in import_paths:
                try:
                    import importlib
                    module = importlib.import_module(module_name)

                    # Generate class name from task name
                    # Handle special cases and use proper capitalization
                    if task_name == "resolve_ip":
                        class_name = "ResolveIP"
                    elif task_name == "resolve_ip_cidr":
                        class_name = "ResolveIPCIDR"
                    elif task_name == "typosquat_detection":
                        class_name = "TyposquatDetection"
                    else:
                        # Generic conversion for other tasks
                        class_name = ''.join(word.capitalize() for word in task_name.split('_'))

                    # Try to get the class from the module
                    task_class = getattr(module, class_name)
                    logger.info(f"Successfully loaded task {task_name} from {module_name}")
                    return task_class

                except (ImportError, AttributeError) as e:
                    logger.debug(f"Failed to load {task_name} from {module_name}: {e}")
                    continue

            # If no path worked, raise the error
            raise ImportError(f"Could not find task {task_name} in any known location")

        except Exception as e:
            logger.error(f"Failed to import task {task_name}: {e}")
            raise ImportError(f"Task {task_name} not found")

    def parse_job_output_with_task(self, task_name: str, raw_output: Any, task_params: Optional[Dict[str, Any]] = None) -> Dict:
        """
        Parse job output using the task's parse_output method.

        Args:
            task_name: Name of the task to use for parsing
            raw_output: Raw output from the job (string or already parsed dict)
            task_params: Parameters to pass to the task

        Returns:
            Dict mapping AssetType to list of parsed assets
        """
        try:
            # Get the task class and create an instance
            task_class = self._get_task_class(task_name)
            task_instance = task_class()

            # Handle different output formats
            logger.debug(f"Using {task_name}.parse_output() to parse job output")
            logger.debug(f"Raw output type: {type(raw_output)}")

            # Pass the output directly to the task's parse_output method
            # The task will handle both string (JSON) and dict (already parsed) inputs
            logger.debug(f"Passing {type(raw_output)} output to {task_name}.parse_output()")
            parsed_result = task_instance.parse_output(raw_output)

            logger.debug(f"Task {task_name} parsed output into {len(parsed_result)} asset types")
            return parsed_result

        except Exception as e:
            logger.error(f"Failed to parse output with task {task_name}: {e}")
            # Handle both string and dict types for logging
            if isinstance(raw_output, str):
                logger.error(f"Raw output preview: {raw_output[:200]}...")
            elif isinstance(raw_output, dict):
                logger.error(f"Raw output keys: {list(raw_output.keys())[:10]}")
                logger.error(f"Raw output sample: {str(raw_output)[:200]}...")
            else:
                logger.error(f"Raw output type: {type(raw_output)}, value: {str(raw_output)[:200]}...")
            # Return empty result on parsing failure
            return {}

    async def spawn_batch(self, task_name: str, commands: List[str],
                         batch_size: int = 20, timeout: int = None,
                         process_incrementally: bool = False,
                         result_processor: Optional[Callable] = None,
                         parse_output: bool = False,
                         sequential_batches: bool = False,
                         **kwargs) -> BatchResult:
        """
        Spawn multiple worker jobs in batches.

        Args:
            task_name: Name of the task to spawn
            commands: List of commands to execute
            batch_size: Number of jobs to spawn per batch
            timeout: Job timeout in seconds
            process_incrementally: Whether to process results after each batch
            result_processor: Optional function to process results incrementally
            sequential_batches: Whether to process batches sequentially (wait for each batch to complete before starting the next)
            **kwargs: Additional job parameters

        Returns:
            BatchResult object for tracking the entire batch
        """
        self._ensure_k8s_service()
        
        batch_id = f"{task_name}-batch-{str(uuid.uuid4())[:8]}"
        batch_result = BatchResult(batch_id)
        batch_result.start_time = time.time()
        
        self.active_batches[batch_id] = batch_result
        
        total_batches = (len(commands) + batch_size - 1) // batch_size
        logger.debug(f"Spawning {len(commands)} {task_name} jobs in {total_batches} batches of {batch_size}")
        
        try:
            # Track current batch for sequential processing
            current_batch_jobs = []

            # Process commands in batches
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(commands))
                batch_commands = commands[start_idx:end_idx]

                logger.debug(f"Processing batch {batch_num + 1}/{total_batches}: {len(batch_commands)} jobs")

                # If sequential_batches is enabled and this isn't the first batch, wait for previous batch to complete
                if sequential_batches and current_batch_jobs:
                    logger.info(f"Sequential mode: waiting for previous batch ({len(current_batch_jobs)} jobs) to complete")
                    await self._wait_for_batch_completion([job.task_id for job in current_batch_jobs], timeout or self.default_timeout)
                    current_batch_jobs = []

                # Create job parameters for this batch
                job_params_list = []
                for j, command in enumerate(batch_commands):
                    batch_kwargs = kwargs.copy()
                    batch_kwargs.update({
                        "step_name": f"{task_name.replace('_', '-')}-batch-{batch_num}-{j}",
                        "job_name": f"{task_name.replace('_', '-')}-batch-{batch_num}-{j}",
                    })

                    # Add result processor to job params for progressive streaming
                    if process_incrementally and result_processor:
                        batch_kwargs['result_processor'] = result_processor
                        batch_kwargs['batch_num'] = batch_num + 1

                    job_params = self._build_job_params(task_name, command, timeout, **batch_kwargs)
                    job_params_list.append(job_params)

                # Queue current batch
                if job_params_list:
                    def queue_batch_in_thread():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(self.k8s_service.queue_worker_tasks(job_params_list))
                        finally:
                            loop.close()

                    with ThreadPoolExecutor() as executor:
                        future = executor.submit(queue_batch_in_thread)
                        task_ids = future.result(timeout=60)

                    if task_ids:
                        # Set up tracking for spawned jobs
                        batch_jobs = []
                        for i, task_id in enumerate(task_ids):
                            job_name = job_params_list[i]['job_name']
                            job_result = JobResult(task_id, job_name, "running")
                            job_result.start_time = time.time()

                            # Store task information for parsing if enabled
                            if parse_output:
                                job_result.task_name = task_name
                                job_result.task_params = kwargs.get('task_params')

                            self.active_jobs[task_id] = job_result
                            batch_result.add_job(job_result)
                            batch_jobs.append(job_result)

                            # Set up output handler with result processor for progressive streaming
                            if process_incrementally and result_processor:
                                self._setup_output_handler(task_id, job_result, result_processor, batch_num + 1)
                            else:
                                self._setup_output_handler(task_id, job_result)

                        logger.debug(f"Successfully spawned batch {batch_num + 1} with {len(task_ids)} jobs")

                        # Track current batch jobs for sequential processing
                        current_batch_jobs.extend(batch_jobs)

                        if sequential_batches:
                            logger.debug(f"Sequential mode: batch {batch_num + 1} jobs spawned, will wait for completion before next batch")
                        elif process_incrementally:
                            logger.debug(f"Parallel mode: batch {batch_num + 1} jobs spawned - running in parallel")
                            logger.debug("Will process results incrementally when jobs complete")
                        else:
                            logger.debug(f"Parallel mode: batch {batch_num + 1} spawned, will wait for completion")
                    else:
                        logger.error(f"Failed to spawn batch {batch_num + 1}")

                # Delay between batches
                if batch_num + 1 < total_batches:
                    if sequential_batches:
                        # No delay needed in sequential mode since we wait for completion
                        pass
                    else:
                        # Minimal delay between batches for parallel spawning
                        await asyncio.sleep(0.1)  # Reduced from default batch_spawn_delay

            # If sequential_batches is enabled, wait for the final batch to complete
            if sequential_batches and current_batch_jobs:
                logger.info(f"Sequential mode: waiting for final batch ({len(current_batch_jobs)} jobs) to complete")
                await self._wait_for_batch_completion([job.task_id for job in current_batch_jobs], timeout or self.default_timeout)
            
            batch_result.end_time = time.time()
            logger.debug(f"Batch spawning completed for {batch_id} in {batch_result.duration:.1f}s")
            
            return batch_result
            
        except Exception as e:
            logger.error(f"Error spawning batch {batch_id}: {e}")
            batch_result.end_time = time.time()
            raise
    
    async def wait_for_batch(self, batch_result: BatchResult, timeout: int = None,
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        Wait for all jobs in a batch to complete.

        Args:
            batch_result: BatchResult to wait for
            timeout: Timeout in seconds
            progress_callback: Optional callback for progress updates (completed, total)

        Returns:
            True if all jobs completed successfully, False otherwise
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        logger.debug(f"Waiting for batch {batch_result.batch_id} to complete "
                   f"({batch_result.total_jobs} jobs, timeout: {timeout}s)")

        last_completed = 0

        while not batch_result.is_completed:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Batch {batch_result.batch_id} timed out after {timeout}s")
                # Mark incomplete jobs as timed out
                for job in batch_result.jobs.values():
                    if not job.is_completed:
                        job.status = "timeout"
                        job.end_time = time.time()
                break

            # Check Kubernetes job status for jobs that haven't completed yet
            await self._check_kubernetes_job_statuses(batch_result)

            # Check for progress
            completed = batch_result.completed_jobs
            if completed > last_completed:
                logger.debug(f"Batch progress: {completed}/{batch_result.total_jobs} jobs completed")
                if progress_callback:
                    progress_callback(completed, batch_result.total_jobs)
                last_completed = completed

            await asyncio.sleep(self.check_interval)

        success_rate = batch_result.success_rate
        logger.info(f"Batch {batch_result.batch_id} completed: "
                   f"{batch_result.successful_jobs}/{batch_result.total_jobs} successful "
                   f"({success_rate:.1%} success rate)")

        return success_rate == 1.0
    
    async def _check_kubernetes_job_statuses(self, batch_result: BatchResult):
        """Check Kubernetes job status for jobs that haven't completed yet"""
        if not self.k8s_service:
            logger.debug("No K8s service available for status checking")
            return

        for job in batch_result.jobs.values():
            # Skip jobs that are already completed (success, failed, timeout)
            if job.is_completed:
                continue

            try:
                # Get the Kubernetes job status
                k8s_status = await self.k8s_service.get_job_status_async(type="worker", id=job.task_id)

                # Update job status based on Kubernetes status
                if k8s_status == "Completed":
                    # Job completed successfully - mark as completed to prevent repeated checking
                    logger.info(f"Job {job.task_id} completed successfully according to Kubernetes")
                    job.status = "completed"
                    job.end_time = time.time()
                elif k8s_status == "Failed":
                    # Job failed - update status and mark as completed
                    logger.warning(f"Job {job.task_id} failed according to Kubernetes")
                    job.status = "failed"
                    job.end_time = time.time()
                    job.error = "Kubernetes job failed"
                elif k8s_status == "TimedOut":
                    # Job timed out - update status and mark as completed
                    logger.warning(f"Job {job.task_id} timed out according to Kubernetes")
                    job.status = "timeout"
                    job.end_time = time.time()
                    job.error = "Kubernetes job timed out"
                elif k8s_status == "Running":
                    # Job is still running - update status if needed
                    if job.status != "running":
                        job.status = "running"
                        logger.debug(f"Job {job.task_id} is running")
                elif k8s_status == "Pending":
                    # Job is pending - keep current status
                    pass
                else:
                    logger.warning(f"Unknown Kubernetes job status for {job.task_id}: {k8s_status}")

            except Exception as e:
                logger.debug(f"Error checking Kubernetes status for job {job.task_id}: {e}")
                # Don't fail the entire batch if we can't check one job's status

    async def _wait_for_batch_completion(self, task_ids: List[str], timeout: int):
        """Wait for specific task IDs to complete (internal helper)"""
        start_time = time.time()
        completed = set()

        while len(completed) < len(task_ids):
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Timeout waiting for task completion after {timeout}s")
                break

            for task_id in task_ids:
                if task_id in completed:
                    continue
                if task_id in self.active_jobs and self.active_jobs[task_id].is_completed:
                    completed.add(task_id)

            await asyncio.sleep(self.check_interval)
    
    def get_job_outputs(self, job_results: Union[JobResult, List[JobResult], BatchResult], parse_output: bool = False) -> Dict[str, Any]:
        """
        Get outputs from completed jobs.

        Args:
            job_results: JobResult, list of JobResults, or BatchResult
            parse_output: Whether to parse outputs using task's parse_output method

        Returns:
            Dictionary mapping task_id to output (raw or parsed)
        """
        outputs = {}

        if isinstance(job_results, JobResult):
            if job_results.is_successful:
                output = job_results.output

                if parse_output and hasattr(job_results, 'task_name') and job_results.task_name:
                    # For parsed output, extract the 'output' field from the wrapper dict
                    if isinstance(output, dict) and 'output' in output:
                        logger.debug("Extracting 'output' field from wrapper dict for parsing")
                        actual_output = output['output']
                    else:
                        logger.debug("Output is not a wrapper dict, using as-is")
                        actual_output = output

                    # Parse output using the task's parse_output method
                    task_params = getattr(job_results, 'task_params', None)
                    output = self.parse_job_output_with_task(job_results.task_name, actual_output, task_params)
                outputs[job_results.task_id] = output
        elif isinstance(job_results, BatchResult):
            for job in job_results.jobs.values():
                if job.is_successful:
                    output = job.output
                    if parse_output and hasattr(job, 'task_name') and job.task_name:
                        # For parsed output, extract the 'output' field from the wrapper dict
                        if isinstance(output, dict) and 'output' in output:
                            logger.debug("Extracting 'output' field from wrapper dict for parsing")
                            actual_output = output['output']
                        else:
                            logger.debug("Output is not a wrapper dict, using as-is")
                            actual_output = output

                        # Parse output using the task's parse_output method
                        task_params = getattr(job, 'task_params', None)
                        output = self.parse_job_output_with_task(job.task_name, actual_output, task_params)
                    outputs[job.task_id] = output
        elif isinstance(job_results, list):
            for job in job_results:
                if job.is_successful:
                    output = job.output
                    if parse_output and hasattr(job, 'task_name') and job.task_name:
                        # For parsed output, extract the 'output' field from the wrapper dict
                        if isinstance(output, dict) and 'output' in output:
                            logger.debug("Extracting 'output' field from wrapper dict for parsing")
                            actual_output = output['output']
                        else:
                            logger.debug("Output is not a wrapper dict, using as-is")
                            actual_output = output

                        # Parse output using the task's parse_output method
                        task_params = getattr(job, 'task_params', None)
                        output = self.parse_job_output_with_task(job.task_name, actual_output, task_params)
                    outputs[job.task_id] = output

        return outputs
    
    def get_job_statistics(self, batch_result: BatchResult) -> Dict[str, Any]:
        """Get comprehensive statistics for a batch"""
        return {
            "batch_id": batch_result.batch_id,
            "total_jobs": batch_result.total_jobs,
            "completed_jobs": batch_result.completed_jobs,
            "successful_jobs": batch_result.successful_jobs,
            "failed_jobs": batch_result.failed_jobs,
            "success_rate": batch_result.success_rate,
            "duration": batch_result.duration,
            "is_completed": batch_result.is_completed
        }
    
    def cleanup_job(self, job_result: JobResult):
        """Clean up resources for a completed job"""
        task_id = job_result.task_id
        
        # Remove from active tracking
        self.active_jobs.pop(task_id, None)
        
        # Clean up output handler
        if self.task_queue_client and task_id in self.output_handlers:
            self.task_queue_client.output_handlers.pop(task_id, None)
            self.output_handlers.pop(task_id, None)
        
        logger.debug(f"Cleaned up resources for job {task_id}")
    
    def cleanup_batch(self, batch_result: BatchResult):
        """Clean up resources for a completed batch"""
        batch_id = batch_result.batch_id
        
        # Clean up all jobs in the batch
        for job in batch_result.jobs.values():
            self.cleanup_job(job)
        
        # Remove batch from active tracking
        self.active_batches.pop(batch_id, None)
        
        logger.debug(f"Cleaned up resources for batch {batch_id}")
    
    def cleanup_all(self):
        """Clean up all active jobs and batches"""
        logger.debug("Cleaning up all WorkerJobManager resources")

        for batch in list(self.active_batches.values()):
            self.cleanup_batch(batch)

        for job in list(self.active_jobs.values()):
            self.cleanup_job(job)

        logger.debug("WorkerJobManager cleanup completed")


# Test helper for simulating job failures (for testing purposes)
class MockK8sService:
    """Mock Kubernetes service for testing"""

    def __init__(self, fail_jobs: List[str] = None):
        self.fail_jobs = fail_jobs or []
        self.job_states = {}  # Track state per job
        self.call_count = 0

    async def get_job_status_async(self, type: str, id: str):
        """Mock async job status check"""
        self.call_count += 1

        if id not in self.job_states:
            self.job_states[id] = "Running"

        # Fail specific jobs immediately
        if id in self.fail_jobs:
            self.job_states[id] = "Failed"

        # Progress other jobs to completion after a few calls
        elif self.job_states[id] == "Running" and self.call_count > 2:
            self.job_states[id] = "Completed"

        return self.job_states[id]


async def test_job_failure_detection():
    """Test that job failures are properly detected and don't cause hanging"""
    logger.info("Testing job failure detection...")

    # Create mock K8s service that will fail specific jobs immediately
    mock_k8s = MockK8sService(fail_jobs=["task-fail-1", "task-fail-2"])

    # Create WorkerJobManager with mock service
    job_manager = WorkerJobManager(k8s_service=mock_k8s)

    # Create a batch with only failing jobs (simpler test)
    batch = BatchResult("test-batch")

    # Add only failing jobs to the batch
    failing_jobs = ["task-fail-1", "task-fail-2"]

    for task_id in failing_jobs:
        job_result = JobResult(task_id, f"job-{task_id}", "running")
        job_result.start_time = time.time()
        job_manager.active_jobs[task_id] = job_result
        batch.add_job(job_result)

    logger.info(f"Created test batch with {len(failing_jobs)} failing jobs")

    # Wait for the batch to complete (this should not hang)
    start_time = time.time()
    success = await job_manager.wait_for_batch(batch, timeout=5)  # Very short timeout for test

    elapsed = time.time() - start_time
    logger.info(f"Batch completed in {elapsed:.1f}s, success: {success}")
    logger.info(f"Final batch status: {batch.successful_jobs} successful, {batch.failed_jobs} failed")

    # Log all job statuses for debugging
    for job in batch.jobs.values():
        logger.info(f"Job {job.task_id}: status={job.status}, is_completed={job.is_completed}")

    # Verify that failed jobs were properly detected
    failed_job_count = sum(1 for job in batch.jobs.values() if job.status == "failed")
    assert failed_job_count == len(failing_jobs), f"Expected {len(failing_jobs)} failed jobs, got {failed_job_count}"

    # Verify that the batch is completed (not hanging)
    assert batch.is_completed, "Batch should be completed"

    logger.info("Job failure detection test passed!")


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_job_failure_detection())
