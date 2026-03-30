import logging
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Dict, Any, List
import os
import uuid
import asyncio
logger = logging.getLogger(__name__)

class KubernetesService:
    def __init__(self):
        try:
            config.load_incluster_config()  # When running inside cluster
        except config.ConfigException:
            config.load_kube_config()  # When running locally
        
        self.batch_api = client.BatchV1Api()
        self.core_api = client.CoreV1Api()
        self.kubernetes_namespace = os.getenv('KUBERNETES_NAMESPACE', '')
        self.docker_registry = os.getenv('DOCKER_REGISTRY', '')
        
    def get_pod_logs(self, type: str, id: str) -> str:
        """Get logs from a pod even if it failed"""
        try:
            if type == "runner":
                selector = f"app={type},workflow-id={id}"
            elif type == "worker":
                selector = f"app={type},task-id={id}"
            else:
                return "Invalid pod type. Must be runner or worker"

            pods = self.core_api.list_namespaced_pod(
                namespace=self.kubernetes_namespace,
                label_selector=selector
            ).items

            if not pods:
                logger.warning(f"No pods found for {type} {id}")
                return "No pods found"

            pods.sort(key=lambda x: x.metadata.creation_timestamp, reverse=True)
            pod = pods[0]

            try:
                logs = self.core_api.read_namespaced_pod_log(
                    name=pod.metadata.name,
                    namespace=self.kubernetes_namespace
                )
                return logs if logs else "No logs available for this workflow"
            except Exception as e:
                logger.error(f"Error getting logs for pod {pod.metadata.name}: {str(e)}")
                return f"Error getting logs: {str(e)}"
        except Exception as e:
            logger.error(f"Error accessing pod for {type} {id}: {str(e)}")
            return f"Error accessing pod: {str(e)}"

    def get_runner_pod_logs_by_execution_id(self, execution_id: str) -> str:
        """Get logs from runner pod using execution-id label selector"""
        try:
            # Try execution-id selector first (preferred for runner pods)
            selector = f"app=workflow-runner,execution-id={execution_id}"
            
            pods = self.core_api.list_namespaced_pod(
                namespace=self.kubernetes_namespace,
                label_selector=selector
            ).items

            if not pods:
                # Fallback to workflow-id selector for backward compatibility
                logger.debug(f"No pods found with execution-id={execution_id}, trying workflow-id selector")
                selector = f"app=workflow-runner,workflow-id={execution_id}"
                pods = self.core_api.list_namespaced_pod(
                    namespace=self.kubernetes_namespace,
                    label_selector=selector
                ).items

            if not pods:
                logger.warning(f"No runner pods found for execution_id {execution_id}")
                return ""

            pods.sort(key=lambda x: x.metadata.creation_timestamp, reverse=True)
            pod = pods[0]

            try:
                logs = self.core_api.read_namespaced_pod_log(
                    name=pod.metadata.name,
                    namespace=self.kubernetes_namespace
                )
                return logs if logs else ""
            except Exception as e:
                logger.error(f"Error getting logs for pod {pod.metadata.name}: {str(e)}")
                return ""
        except Exception as e:
            logger.error(f"Error accessing runner pod for execution_id {execution_id}: {str(e)}")
            return ""


    def get_job_status(self, type: str, id: str):
        """Get the status of a workflow job"""
        try:
            job_details = self.batch_api.read_namespaced_job_status(
                name=f"{type}-{id}",
                namespace=self.kubernetes_namespace
            )
            status = job_details.status  # type: ignore
            if status.active:
                return "Running"
            elif status.failed:
                if status.conditions[-1].reason == "DeadlineExceeded":
                    return "TimedOut"
                else:
                    return "Failed"
            elif status.succeeded:
                return "Completed"
            else:
                return "Pending"
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Job {type}-{id} not found, considering it completed")
                return "Completed"
            raise

    async def get_job_status_async(self, type: str, id: str):
        """Get the status of a workflow job asynchronously"""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.get_job_status(type, id)
        )

    async def queue_worker_tasks(self, job_params_list: List[Dict[str, Any]]) -> List[str]:
        """Submit multiple tasks to the queue and return their task IDs"""
        task_ids = []
        for job_params in job_params_list:
            task_id = str(uuid.uuid4())
            job_params["job_id"] = task_id
            task_ids.append(task_id)
        
        logger.info(f"Creating {len(task_ids)} jobs in batch")
        try:
            # Create all jobs in parallel using asyncio.gather
            await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda p=job_params: self.batch_api.create_namespaced_job(
                        self.kubernetes_namespace, 
                        self.generate_job_crd(p)
                    )
                )
                for job_params in job_params_list
            ])
            return task_ids
        except Exception as e:
            logger.error(f"Failed to create jobs in batch: {e}")
            logger.exception(e)
            raise

    def generate_job_crd(self, job_params: Dict[str, Any]):
        """
        Generate an equivalent job CRD to sample-job.yaml
        """
        metadata = client.V1ObjectMeta(
            name=f"worker-{job_params['job_id']}",
            labels={
                "kueue.x-k8s.io/queue-name": "recon-worker-queue",
                "app": "worker",
                "task-id": job_params["job_id"],
                "workflow-id": job_params["workflow_id"],
                "workflow-name": job_params["workflow_name"],
                "program-name": job_params["program_name"],
                "task-name": job_params["task_name"],
                "step-num": str(job_params["step_num"]),
                "step-name": job_params["step_name"]
            }
        )

        # Always use sh -c to avoid JSON marshaling issues with args array
        shell_command = job_params["args"][0] if job_params["args"] else ""

        # Properly quote the shell command to handle pipes and special characters
        quoted_command = f"'{shell_command}'" if '|' in shell_command or '&' in shell_command else shell_command

        container = client.V1Container(
            image=job_params["image"],
            image_pull_policy=os.getenv('IMAGE_PULL_POLICY'),
            name=job_params["job_name"],
            command=["sh", "-c", f"python3 /usr/local/bin/command_wrapper.py {quoted_command}"],
            args=[],
        )

        container.env = [
            client.V1EnvVar(
                name="API_URL",
                value=os.getenv('API_URL')
            ),
                client.V1EnvVar(
                    name="INTERNAL_SERVICE_API_KEY",
                    value=os.getenv('INTERNAL_SERVICE_API_KEY')
                ),
                client.V1EnvVar(
                    name="NATS_URL",
                    value=os.getenv('NATS_URL')
                ),
                client.V1EnvVar(
                    name="TASK_ID",
                    value=job_params["job_id"]
                ),
                client.V1EnvVar(
                    name="OUTPUT_QUEUE_SUBJECT",
                    value=f"tasks.output.{job_params['workflow_id']}"
                ),
                client.V1EnvVar(
                    name="STEP_NAME",
                    value=job_params["step_name"]
                ),
                client.V1EnvVar(
                    name="WORKFLOW_ID",
                    value=job_params["workflow_id"]
                ),
                client.V1EnvVar(
                    name="PROGRAM_NAME",
                    value=job_params["program_name"]
                ),
                client.V1EnvVar(
                    name="STEP_NUM",
                    value=str(job_params["step_num"])
                ),
                client.V1EnvVar(
                    name="TASK_NAME",
                    value=job_params["task_name"]
                )
        ]

        container.resources = {
            "requests": {
                "cpu": "800m",
                "memory": "200Mi",
            },
            "limits": {
                "cpu": "1000m",
                "memory": "4096Mi",
            }
        }

        # Job template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": "worker",
                    "task-id": job_params["job_id"],
                    "workflow-id": job_params["workflow_id"],
                    "program-name": job_params["program_name"],
                    "task-name": job_params["task_name"],
                    "step-num": str(job_params["step_num"]),
                    "step-name": job_params["step_name"]
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                restart_policy="Never",
                
            )
        )

        template.spec.node_selector = {"reconhawx.worker": "true"}

        return client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=metadata,
            spec=client.V1JobSpec(
                parallelism=1, completions=1, suspend=True, ttl_seconds_after_finished=300, template=template, active_deadline_seconds=job_params["timeout"], backoff_limit=0
            ),
        )
    
    async def wait_for_jobs_completion(self, job_names: List[str], timeout: int = 3600, check_interval: int = 30) -> Dict[str, str]:
        """
        Wait for a list of jobs to complete and return their final statuses.
        
        Args:
            job_names: List of job names to monitor
            timeout: Maximum time to wait in seconds (default: 1 hour)
            check_interval: How often to check job status in seconds (default: 30 seconds)
            
        Returns:
            Dict mapping job names to their final status ('succeeded', 'failed', 'unknown')
        """
        if not job_names:
            return {}
            
        logger.info(f"Waiting for {len(job_names)} jobs to complete: {job_names}")
        
        start_time = asyncio.get_event_loop().time()
        job_statuses = {job_name: 'running' for job_name in job_names}
        # Track jobs that have already been marked as not-found to avoid repeated logging
        not_found_jobs = set()
        
        while True:
            # Check current time against timeout
            elapsed_time = asyncio.get_event_loop().time() - start_time
            if elapsed_time >= timeout:
                logger.warning(f"Timeout reached ({timeout}s) while waiting for jobs")
                break
            
            # Check status of each job
            completed_jobs = 0
            for job_name in job_names:
                # Skip jobs that are already completed (including 'unknown' status)
                if job_statuses[job_name] in ['succeeded', 'failed', 'unknown']:
                    completed_jobs += 1
                    continue
                    
                logger.debug(f"Checking status of job {job_name} (current status: {job_statuses[job_name]})")
                try:
                    # Parse job name to extract type and id for existing method
                    if job_name.startswith('worker-'):
                        job_id = job_name[7:]  # Remove 'worker-' prefix
                        status = self.get_job_status('worker', job_id)
                        
                        # Map status to our format
                        if status == 'Completed':
                            job_statuses[job_name] = 'succeeded'
                            logger.info(f"Job {job_name} completed successfully")
                            completed_jobs += 1
                        elif status in ['Failed', 'TimedOut']:
                            job_statuses[job_name] = 'failed'
                            logger.warning(f"Job {job_name} failed with status: {status}")
                            completed_jobs += 1
                        elif status in ['Running', 'Pending']:
                            # Job is still running, keep checking
                            logger.debug(f"Job {job_name} is still {status}")
                            pass
                        else:
                            logger.warning(f"Unknown job status for {job_name}: {status}")
                            job_statuses[job_name] = 'unknown'
                            completed_jobs += 1
                    else:
                        logger.warning(f"Unexpected job name format: {job_name}")
                        job_statuses[job_name] = 'unknown'
                        completed_jobs += 1
                            
                except ApiException as e:
                    if e.status == 404:
                        if job_name not in not_found_jobs:
                            # Only log once when a job is first discovered as not found
                            logger.info(f"Job {job_name} not found, considering it completed")
                            not_found_jobs.add(job_name)
                        job_statuses[job_name] = 'unknown'
                        completed_jobs += 1
                    else:
                        logger.error(f"Error checking status of job {job_name}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error checking job {job_name}: {e}")
                    # Mark as unknown to prevent repeated checking
                    job_statuses[job_name] = 'unknown'
                    completed_jobs += 1
            
            # If all jobs are complete, exit the loop
            if completed_jobs == len(job_names):
                logger.info("All monitored jobs have completed")
                break
                
            # Wait before checking again
            logger.debug(f"Waiting {check_interval}s before next check. "
                        f"{completed_jobs}/{len(job_names)} jobs complete. "
                        f"Elapsed: {elapsed_time:.1f}s/{timeout}s")
            await asyncio.sleep(check_interval)
        
        # Final status report
        succeeded = sum(1 for status in job_statuses.values() if status == 'succeeded')
        failed = sum(1 for status in job_statuses.values() if status == 'failed')
        unknown = sum(1 for status in job_statuses.values() if status == 'unknown')
        
        logger.info(f"Job completion summary: {succeeded} succeeded, {failed} failed, {unknown} unknown")
        return job_statuses
    