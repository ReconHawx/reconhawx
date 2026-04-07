from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import os
import logging
import json
from typing import Dict, Any, List, Optional
from repository import AdminRepository

logger = logging.getLogger(__name__)

# Suppress noisy filelock DEBUG logs and tldextract filelock logs
logging.getLogger("kubernetes.client.rest").setLevel(logging.WARNING)

# Kueue status mapping
KUEUE_STATUS_MAPPING = {
    'Pending': 'Queued',           # Waiting in queue
    'Admitted': 'Admitted',        # Admitted to cluster queue
    'Running': 'Running',          # Job created and running
    'Finished': 'Completed',       # Workload completed
    'Failed': 'Failed',            # Workload failed
    'Rejected': 'Rejected'         # Rejected by admission controller
}


class KubernetesService:
    def __init__(self):
        try:
            # Try to load in-cluster config first
            config.load_incluster_config()
            logger.debug("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                # Fall back to kubeconfig file
                config.load_kube_config()
                logger.debug("Loaded kubeconfig file")
            except config.ConfigException:
                logger.warning("Could not load Kubernetes configuration")

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.custom_objects_v1 = client.CustomObjectsApi()

        # Kueue configuration
        self.kueue_enabled = os.getenv('KUEUE_ENABLED', 'true').lower() == 'true'
        self.kueue_workflow_queue = os.getenv('KUEUE_WORKFLOW_QUEUE', 'recon-runner-queue')
        self.kueue_cluster_queue = os.getenv('KUEUE_CLUSTER_QUEUE', 'runner-cluster-queue')
        self.kueue_priority_class = os.getenv('KUEUE_PRIORITY_CLASS', 'workflow-priority')
        self.workflow_default_priority = os.getenv('WORKFLOW_DEFAULT_PRIORITY', 'normal')

        # Resource requirements
        self.workflow_resource_requests = {
            'cpu': os.getenv('WORKFLOW_CPU_REQUEST', '500m'),
            'memory': os.getenv('WORKFLOW_MEMORY_REQUEST', '1Gi')
        }
        self.workflow_resource_limits = {
            'cpu': os.getenv('WORKFLOW_CPU_LIMIT', '2000m'),
            'memory': os.getenv('WORKFLOW_MEMORY_LIMIT', '4Gi')
        }

        logger.info(f"KubernetesService initialized - Kueue enabled: {self.kueue_enabled}")

    async def _get_aws_credentials(self) -> Optional[Dict[str, str]]:
        """
        Fetch active AWS credentials from the database

        Returns:
            Dictionary with access_key, secret_access_key, and default_region, or None if not found
        """
        try:
            admin_repo = AdminRepository()
            credentials = await admin_repo.list_aws_credentials()

            # Find the first active credential
            for cred in credentials:
                if cred.get('is_active', False):
                    return {
                        'access_key': cred.get('access_key', ''),
                        'secret_access_key': cred.get('secret_access_key', ''),
                        'default_region': cred.get('default_region', 'us-east-1')
                    }

            logger.warning("No active AWS credentials found in database")
            return None

        except Exception as e:
            logger.error(f"Error fetching AWS credentials: {str(e)}")
            return None

    def _cleanup_existing_resources(self, execution_id: str, namespace: str):
        """Clean up any existing resources for the execution ID"""
        try:
            # Clean up existing ConfigMap
            configmap_name = f"workflow-data-{execution_id}"
            try:
                self.v1.delete_namespaced_config_map(
                    name=configmap_name,
                    namespace=namespace
                )
                logger.debug(f"Cleaned up existing ConfigMap {configmap_name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Failed to cleanup ConfigMap {configmap_name}: {e}")
            
            # Clean up existing workload
            workload_name = f"workflow-{execution_id}"
            try:
                self.custom_objects_v1.delete_namespaced_custom_object(
                    group="kueue.x-k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="workloads",
                    name=workload_name
                )
                logger.debug(f"Cleaned up existing workload {workload_name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Failed to cleanup workload {workload_name}: {e}")
            
            # Clean up existing job
            job_name = f"workflow-{execution_id}"
            try:
                self.batch_v1.delete_namespaced_job(
                    name=job_name,
                    namespace=namespace,
                    propagation_policy='Background'
                )
                logger.debug(f"Cleaned up existing job {job_name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Failed to cleanup job {job_name}: {e}")
                    
        except Exception as e:
            logger.warning(f"Error during resource cleanup: {e}")

    def _patch_workflow_configmap_owner_to_job(
        self,
        namespace: str,
        configmap_name: str,
        job_name: str,
        job_uid: Optional[str],
    ) -> None:
        """Link workflow ConfigMap lifecycle to the Batch Job so GC deletes it with the Job (e.g. ttlSecondsAfterFinished)."""
        if not job_uid:
            logger.error(
                f"Cannot set ConfigMap owner: Job {job_name} has no uid; {configmap_name} may be orphaned"
            )
            return
        # Use typed models + default patch type (no _content_type: unsupported in some client versions).
        owner_ref = client.V1OwnerReference(
            api_version="batch/v1",
            kind="Job",
            name=job_name,
            uid=job_uid,
            controller=True,
        )
        patch_body = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(owner_references=[owner_ref]),
        )
        try:
            self.v1.patch_namespaced_config_map(
                name=configmap_name,
                namespace=namespace,
                body=patch_body,
            )
            logger.debug(
                f"Set ownerReferences on ConfigMap {configmap_name} -> Job {job_name} ({job_uid})"
            )
        except ApiException as e:
            logger.error(
                f"Failed to patch ConfigMap {configmap_name} with Job ownerReference: {e}"
            )
            raise

    def delete_workflow_configmap(self, execution_id: str) -> None:
        """Delete workflow-data ConfigMap for an execution; no-op if already absent."""
        namespace = os.getenv("KUBERNETES_NAMESPACE", "default")
        configmap_name = f"workflow-data-{execution_id}"
        try:
            self.v1.delete_namespaced_config_map(name=configmap_name, namespace=namespace)
            logger.debug(f"Deleted ConfigMap {configmap_name}")
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Failed to delete ConfigMap {configmap_name}: {e}")
                raise

    async def create_runner_workload(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Kueue Workload for workflow execution queuing"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            execution_id = workflow_data.get('execution_id', workflow_data['workflow_id'])
            priority = workflow_data.get('priority', self.workflow_default_priority)
            
            logger.info(f"Creating Kueue workload for workflow {execution_id} with priority {priority}")
            
            # Clean up any existing resources for this execution ID
            self._cleanup_existing_resources(execution_id, namespace)
            
            # Create ConfigMap with workflow data (same as before)
            configmap_name = f"workflow-data-{execution_id}"
            workflow_json = json.dumps(workflow_data)
            
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "workflow-runner",
                        "workflow-id": execution_id,
                        "execution-id": execution_id
                    }
                ),
                data={
                    "workflow.json": workflow_json
                }
            )
            
            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for workflow data")
            except ApiException as e:
                if e.status == 409:  # Conflict - ConfigMap already exists
                    logger.warning(f"ConfigMap {configmap_name} already exists, updating instead")
                    try:
                        # Update existing ConfigMap
                        self.v1.patch_namespaced_config_map(
                            name=configmap_name,
                            namespace=namespace,
                            body=configmap
                        )
                        logger.debug(f"Updated existing ConfigMap {configmap_name}")
                    except ApiException as update_error:
                        logger.error(f"Failed to update ConfigMap {configmap_name}: {update_error}")
                        raise
                else:
                    logger.error(f"Failed to create ConfigMap: {e}")
                    raise
            
            # Create workload metadata
            workload_metadata = {
                "name": f"workflow-{execution_id}",
                "namespace": namespace,
                "labels": {
                    "app": "workflow-runner",
                    "workflow-id": execution_id,
                    "execution-id": execution_id,
                    "program": workflow_data['program_name'],
                    "priority": priority
                }
            }
            
            # Create pod template (same as before but with resource requirements)
            pod_template = await self._create_workflow_pod_template(workflow_data, execution_id, configmap_name)
            
            # Create workload spec
            workload_spec = {
                "queueName": self.kueue_workflow_queue,
                "priority": self._get_priority_value(priority),
                "podSets": [
                    {
                        "name": "workflow-runner",
                        "count": 1,
                        "template": pod_template
                    }
                ],
                "admission": {
                    "clusterQueue": self.kueue_cluster_queue
                }
            }
            
            # Create workload body
            workload_body = {
                "apiVersion": "kueue.x-k8s.io/v1beta1",
                "kind": "Workload",
                "metadata": workload_metadata,
                "spec": workload_spec
            }
            
            # Create the workload in Kubernetes
            created_workload = self.custom_objects_v1.create_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                body=workload_body
            )
            
            workload_name = created_workload.get('metadata', {}).get('name', 'unknown')
            logger.info(f"Created Kueue workload: {workload_name}")
            
            return created_workload
            
        except Exception as e:
            logger.error(f"Error creating Kueue workload: {str(e)}")
            raise

    async def _create_workflow_pod_template(self, workflow_data: Dict[str, Any], execution_id: str, configmap_name: str) -> Dict[str, Any]:
        """Create pod template for workflow runner with resource requirements"""
        from services.workflow_kubernetes_settings import get_workflow_kubernetes_merged

        namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
        wk = await get_workflow_kubernetes_merged()
        runner_image = wk["runner_image"]
        worker_image = wk["worker_image"]
        image_pull_policy = wk["image_pull_policy"]
        service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')

        # Fetch AWS credentials from database
        aws_creds = await self._get_aws_credentials()

        # Build environment variables list
        env_vars = [
            # Core workflow configuration
            {"name": "WORKFLOW_ID", "value": workflow_data.get('workflow_id', '')},
            {"name": "EXECUTION_ID", "value": execution_id},
            {"name": "PROGRAM_NAME", "value": workflow_data['program_name']},
            {"name": "WORKFLOW_NAME", "value": workflow_data['name']},
            {"name": "WORKFLOW_STEPS", "value": str(workflow_data['steps'])},

            # Service URLs
            {"name": "NATS_URL", "value": os.getenv('NATS_URL')},
            {"name": "API_URL", "value": os.getenv('API_URL')},
            {"name": "REDIS_URL", "value": os.getenv('REDIS_URL')},

            # Internal API authentication (kubelet resolves from Secret; matches API bootstrap)
            {
                "name": "INTERNAL_SERVICE_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": os.getenv("INTERNAL_SERVICE_SECRET_NAME", "internal-service-secret"),
                        "key": "token",
                    }
                },
            },

            # Kubernetes configuration
            {"name": "KUBERNETES_NAMESPACE", "value": namespace},
            {"name": "WORKER_IMAGE", "value": worker_image},
            {"name": "IMAGE_PULL_POLICY", "value": image_pull_policy},

            # Progressive Asset Streaming Configuration
            {"name": "ENABLE_PROGRESSIVE_STREAMING", "value": os.getenv('ENABLE_PROGRESSIVE_STREAMING', 'true')},
            {"name": "PROGRESSIVE_MAX_RETRIES", "value": os.getenv('PROGRESSIVE_MAX_RETRIES', '3')},
            {"name": "PROGRESSIVE_RETRY_DELAY", "value": os.getenv('PROGRESSIVE_RETRY_DELAY', '1.0')},
            {"name": "PROGRESSIVE_RETRY_BACKOFF", "value": os.getenv('PROGRESSIVE_RETRY_BACKOFF', '2.0')},
            {"name": "PROGRESSIVE_MIN_ASSETS", "value": os.getenv('PROGRESSIVE_MIN_ASSETS', '1')},
            {"name": "PROGRESSIVE_MAX_CONCURRENT", "value": os.getenv('PROGRESSIVE_MAX_CONCURRENT', '5')},
            {"name": "PROGRESSIVE_SEND_TIMEOUT", "value": os.getenv('PROGRESSIVE_SEND_TIMEOUT', '30.0')},

            # Memory Optimization Configuration
            {"name": "STREAMING_ASSET_THRESHOLD", "value": os.getenv('STREAMING_ASSET_THRESHOLD', '2500')},
            {"name": "STREAMING_RESULT_THRESHOLD", "value": os.getenv('STREAMING_RESULT_THRESHOLD', '500')},
            {"name": "ASSET_BATCH_SIZE", "value": os.getenv('ASSET_BATCH_SIZE', '100')},
            {"name": "STREAMING_BATCH_SIZE", "value": os.getenv('STREAMING_BATCH_SIZE', '1000')},
            {"name": "MEMORY_LIMIT_MB", "value": os.getenv('MEMORY_LIMIT_MB', '500')},
            {"name": "LARGE_LIST_THRESHOLD", "value": os.getenv('LARGE_LIST_THRESHOLD', '1000')},
            {"name": "GC_THRESHOLD", "value": os.getenv('GC_THRESHOLD', '50000')},
            {"name": "STANDARD_PAGE_SIZE", "value": os.getenv('STANDARD_PAGE_SIZE', '100')},
            {"name": "STREAMING_PAGE_SIZE", "value": os.getenv('STREAMING_PAGE_SIZE', '1000')},
            {"name": "MAX_PAGES", "value": os.getenv('MAX_PAGES', '1000')},
            # Runner typosquat caching configuration
            {"name": "TYPOSQUAT_CACHE_TTL", "value": os.getenv('TYPOSQUAT_CACHE_TTL', '2592000')},
            {"name": "TYPOSQUAT_USE_CACHE", "value": os.getenv('TYPOSQUAT_USE_CACHE', 'true')}
        ]

        # Add AWS credentials if available
        if aws_creds:
            logger.info("Adding AWS credentials to runner pod environment")
            env_vars.extend([
                {"name": "AWS_ACCESS_KEY_ID", "value": aws_creds['access_key']},
                {"name": "AWS_SECRET_ACCESS_KEY", "value": aws_creds['secret_access_key']},
                {"name": "AWS_DEFAULT_REGION", "value": aws_creds['default_region']}
            ])
        else:
            logger.warning("No active AWS credentials found - pods will not have AWS access")

        # Create container with resource requirements
        container = {
            "name": "workflow-runner",
            "image": runner_image,
            "imagePullPolicy": image_pull_policy,
            "command": ["/usr/local/bin/python"],
            "args": ["/app/run-workflow.py", "/workflow-data/workflow.json"],
            "env": env_vars,
            "resources": {
                "requests": self.workflow_resource_requests,
                "limits": self.workflow_resource_limits
            },
            "volumeMounts": [
                {
                    "name": "workflow-data",
                    "mountPath": "/workflow-data"
                }
            ]
        }
        
        # Create pod template
        pod_template = {
            "metadata": {
                "labels": {
                    "app": "workflow-runner",
                    "workflow-id": execution_id,
                    "execution-id": execution_id
                }
            },
            "spec": {
                "containers": [container],
                "serviceAccountName": service_account,
                "restartPolicy": "Never",
                "nodeSelector": {
                    "reconhawx.runner": "true"
                },
                "volumes": [
                    {
                        "name": "workflow-data",
                        "configMap": {
                            "name": configmap_name,
                            "items": [
                                {
                                    "key": "workflow.json",
                                    "path": "workflow.json"
                                }
                            ]
                        }
                    }
                ]
            }
        }
        
        return pod_template

    def _get_priority_value(self, priority: str) -> int:
        """Convert priority string to integer value"""
        priority_values = {
            'low': 1,
            'normal': 5,
            'high': 10,
            'critical': 20
        }
        return priority_values.get(priority.lower(), 5)

    def get_workload_status(self, execution_id: str) -> Dict[str, Any]:
        """Get comprehensive workload status including queue position"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            workload_name = f"workflow-{execution_id}"
            
            workload = self.custom_objects_v1.get_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                name=workload_name
            )
            
            # Extract status information
            status_conditions = workload.get('status', {}).get('conditions', [])
            current_condition = status_conditions[-1] if status_conditions else {}
            
            status = current_condition.get('type', 'Pending')
            mapped_status = KUEUE_STATUS_MAPPING.get(status, status)
            
            # Get queue position
            queue_position = self._get_queue_position(execution_id)
            
            # Get resource requirements
            resource_requirements = {}
            pod_sets = workload.get('spec', {}).get('podSets', [])
            if pod_sets:
                containers = pod_sets[0].get('template', {}).get('spec', {}).get('containers', [])
                if containers:
                    resources = containers[0].get('resources', {})
                    resource_requirements = {
                        'requests': resources.get('requests', {}),
                        'limits': resources.get('limits', {})
                    }
            
            return {
                'status': mapped_status,
                'kueue_status': status,
                'queue_position': queue_position,
                'priority': workload.get('spec', {}).get('priority', 5),
                'queue_name': workload.get('spec', {}).get('queueName', ''),
                'resource_requirements': resource_requirements,
                'created_at': workload.get('metadata', {}).get('creationTimestamp', ''),
                'conditions': status_conditions
            }
            
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Workload for execution {execution_id} not found")
                return {'status': 'NotFound', 'error': 'Workload not found'}
            logger.error(f"Error getting workload status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting workload status: {str(e)}")
            raise

    def _get_queue_position(self, execution_id: str) -> int:
        """Get position of workflow in queue"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            
            # Get all workloads in the same queue
            workloads = self.custom_objects_v1.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                label_selector="app=workflow-runner"
            )
            
            # Filter workloads by queue and sort by priority and creation time
            queue_workloads = []
            for workload in workloads.get('items', []):
                if workload.get('spec', {}).get('queueName') == self.kueue_workflow_queue:
                    queue_workloads.append(workload)
            
            # Sort by priority (descending) and creation time (ascending)
            queue_workloads.sort(key=lambda w: (
                -w.get('spec', {}).get('priority', 5),  # Higher priority first
                w.get('metadata', {}).get('creationTimestamp', '')  # Earlier creation first
            ))
            
            # Find position of our workload
            for i, workload in enumerate(queue_workloads):
                if workload.get('metadata', {}).get('name') == f"workflow-{execution_id}":
                    return i + 1
            
            return -1  # Not found in queue
            
        except Exception as e:
            logger.error(f"Error getting queue position: {e}")
            return -1

    def list_workloads(self, program_name: str = None) -> List[Dict[str, Any]]:
        """List all workflow workloads with optional filtering"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            
            # Build label selector
            label_selector = "app=workflow-runner"
            if program_name:
                label_selector += f",program={program_name}"
            
            workloads = self.custom_objects_v1.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                label_selector=label_selector
            )
            
            # Process workloads and add status information
            processed_workloads = []
            for workload in workloads.get('items', []):
                execution_id = workload.get('metadata', {}).get('name', '').replace('workflow-', '')
                status_info = self.get_workload_status(execution_id)
                
                processed_workload = {
                    'execution_id': execution_id,
                    'workflow_id': workload.get('metadata', {}).get('labels', {}).get('workflow-id', ''),
                    'program_name': workload.get('metadata', {}).get('labels', {}).get('program', ''),
                    'priority': workload.get('spec', {}).get('priority', 5),
                    'queue_name': workload.get('spec', {}).get('queueName', ''),
                    'created_at': workload.get('metadata', {}).get('creationTimestamp', ''),
                    'status': status_info.get('status', 'Unknown'),
                    'queue_position': status_info.get('queue_position', -1)
                }
                processed_workloads.append(processed_workload)
            
            return processed_workloads
            
        except Exception as e:
            logger.error(f"Error listing workloads: {str(e)}")
            raise

    def update_workload_priority(self, execution_id: str, priority: str) -> bool:
        """Update workflow priority in queue"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            workload_name = f"workflow-{execution_id}"
            
            # Create patch body
            patch_body = {
                "spec": {
                    "priority": self._get_priority_value(priority)
                }
            }
            
            # Patch the workload
            self.custom_objects_v1.patch_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                name=workload_name,
                body=patch_body
            )
            
            logger.info(f"Updated workload {workload_name} priority to {priority}")
            return True
            
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Workload {execution_id} not found for priority update")
                return False
            logger.error(f"Error updating workload priority: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating workload priority: {str(e)}")
            raise

    def delete_workload(self, execution_id: str) -> bool:
        """Delete a workflow workload"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            workload_name = f"workflow-{execution_id}"
            
            self.custom_objects_v1.delete_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                name=workload_name
            )
            
            logger.info(f"Deleted workload {workload_name}")
            return True
            
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Workload {execution_id} not found for deletion")
                return False
            logger.error(f"Error deleting workload: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting workload: {str(e)}")
            raise

    def check_queue_capacity(self, resource_requirements: Dict[str, str] = None) -> Dict[str, Any]:
        """Check if queue has capacity for new workload"""
        try:
            # For now, return basic capacity info
            # In a full implementation, this would query cluster queue capacity
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            
            # Get current queue length
            workloads = self.custom_objects_v1.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                label_selector="app=workflow-runner"
            )
            
            queue_length = len(workloads.get('items', []))
            
            return {
                'queue_length': queue_length,
                'has_capacity': queue_length < 100,  # Simple capacity check
                'estimated_wait_time': queue_length * 5,  # Rough estimate in minutes
                'queue_name': self.kueue_workflow_queue
            }
            
        except Exception as e:
            logger.error(f"Error checking queue capacity: {str(e)}")
            return {
                'queue_length': -1,
                'has_capacity': True,
                'estimated_wait_time': 0,
                'error': str(e)
            }
        
    async def create_runner_job(self, workflow_data: Dict[str, Any]):
        """Create a Kubernetes job for workflow execution with Kueue support"""
        try:
            # If Kueue is enabled, create job with Kueue annotations
            if self.kueue_enabled:
                logger.info("Kueue enabled, creating job with Kueue annotations")
                return await self._create_kueue_job(workflow_data)
            else:
                logger.info("Kueue disabled, creating direct job")
                return await self._create_direct_job(workflow_data)

        except Exception as e:
            logger.error(f"Error creating runner job: {str(e)}")
            # Fallback to direct job creation if Kueue job creation fails
            if self.kueue_enabled:
                logger.warning("Kueue job creation failed, falling back to direct job creation")
                try:
                    return await self._create_direct_job(workflow_data)
                except Exception as fallback_error:
                    logger.error(f"Fallback job creation also failed: {fallback_error}")
                    raise
            else:
                raise

    async def _create_kueue_job(self, workflow_data: Dict[str, Any]):
        """Create a Kubernetes job with Kueue annotations for queue management"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            execution_id = workflow_data.get('execution_id')
            if not execution_id:
                raise ValueError("execution_id is required in workflow_data")
            
            # Clean up any existing resources first
            self._cleanup_existing_resources(execution_id, namespace)
            
            # Create ConfigMap for workflow data
            configmap_name = f"workflow-data-{execution_id}"
            configmap = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": configmap_name,
                    "namespace": namespace,
                    "labels": {
                        "app": "workflow-runner",
                        "execution-id": execution_id,
                        "workflow-id": execution_id
                    }
                },
                "data": {
                    "workflow.json": json.dumps(workflow_data, indent=2)
                }
            }
            
            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for workflow data")
            except ApiException as e:
                if e.status == 409:  # Conflict - ConfigMap already exists
                    logger.warning(f"ConfigMap {configmap_name} already exists, updating instead")
                    try:
                        self.v1.patch_namespaced_config_map(
                            name=configmap_name,
                            namespace=namespace,
                            body=configmap
                        )
                        logger.debug(f"Updated existing ConfigMap {configmap_name}")
                    except ApiException as update_error:
                        logger.error(f"Failed to update ConfigMap {configmap_name}: {update_error}")
                        raise
                else:
                    logger.error(f"Failed to create ConfigMap: {e}")
                    raise
            
            # Create pod template with Kueue annotations
            pod_template = await self._create_workflow_pod_template(workflow_data, execution_id, configmap_name)
            
            # Create Kubernetes Job with Kueue annotations
            job_name = f"workflow-{execution_id}"
            job = {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {
                    "name": job_name,
                    "namespace": namespace,
                    "labels": {
                        "app": "workflow-runner",
                        "execution-id": execution_id,
                        "workflow-id": execution_id,
                        "program": workflow_data.get('program_name', ''),
                        "priority": workflow_data.get('priority', 'normal')
                    },
                    "annotations": {
                        "kueue.x-k8s.io/queue-name": self.kueue_workflow_queue,
                        "kueue.x-k8s.io/priority-class": self.kueue_priority_class
                    }
                },
                "spec": {
                    "parallelism": 1,
                    "completions": 1,
                    "backoffLimit": 0,
                    "ttlSecondsAfterFinished": 300,
                    #"activeDeadlineSeconds": 15,  # 1 hour timeout
                    "template": pod_template
                }
            }
            
            # Create the job
            created_job = self.batch_v1.create_namespaced_job(
                namespace=namespace,
                body=job
            )

            job_uid = getattr(getattr(created_job, "metadata", None), "uid", None)
            self._patch_workflow_configmap_owner_to_job(
                namespace, configmap_name, job_name, job_uid
            )
            
            logger.debug(f"Created Kubernetes job with Kueue annotations: {job_name}")
            return created_job
            
        except Exception as e:
            logger.error(f"Error creating Kueue job: {str(e)}")
            raise

    async def _create_direct_job(self, workflow_data: Dict[str, Any]):
        """Create a direct Kubernetes job (original implementation)"""
        try:
            from services.workflow_kubernetes_settings import get_workflow_kubernetes_merged

            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            wk = await get_workflow_kubernetes_merged()
            runner_image = wk["runner_image"]
            worker_image = wk["worker_image"]
            image_pull_policy = wk["image_pull_policy"]
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')
            job_ttl = int(os.getenv('JOB_TTL_SECONDS', '300'))
            
            # Create ConfigMap with workflow data
            # Use execution_id for naming Kubernetes resources (always valid)
            # Use workflow_id for workflow definition reference (can be None for custom workflows)
            execution_id = workflow_data.get('execution_id', workflow_data['workflow_id'])
            
            # Clean up any existing resources for this execution ID
            self._cleanup_existing_resources(execution_id, namespace)
            
            configmap_name = f"workflow-data-{execution_id}"
            
            # Debug: Log the workflow data before JSON serialization
            if 'steps' in workflow_data:
                logger.debug(f"Workflow has {len(workflow_data['steps'])} steps")
                for i, step in enumerate(workflow_data['steps']):
                    logger.debug(f"Step {i}: {step.get('name')} with {len(step.get('tasks', []))} tasks")
                    for j, task in enumerate(step.get('tasks', [])):
                        logger.debug(f"  Task {j}: {task.get('name')}, input_filter: {task.get('input_filter')}")
            
            workflow_json = json.dumps(workflow_data)
            
            # Debug: Log the JSON string to see if input_filter is preserved
            logger.debug(f"Serialized workflow JSON: {workflow_json}")
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "workflow-runner",
                        "workflow-id": execution_id,
                        "execution-id": execution_id
                    }
                ),
                data={
                    "workflow.json": workflow_json
                }
            )
            
            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for workflow data")
            except ApiException as e:
                if e.status == 409:  # Conflict - ConfigMap already exists
                    logger.warning(f"ConfigMap {configmap_name} already exists, updating instead")
                    try:
                        # Update existing ConfigMap
                        self.v1.patch_namespaced_config_map(
                            name=configmap_name,
                            namespace=namespace,
                            body=configmap
                        )
                        logger.debug(f"Updated existing ConfigMap {configmap_name}")
                    except ApiException as update_error:
                        logger.error(f"Failed to update ConfigMap {configmap_name}: {update_error}")
                        raise
                else:
                    logger.error(f"Failed to create ConfigMap: {e}")
                    raise
            
            # Create job metadata
            metadata = client.V1ObjectMeta(
                name=f"workflow-{execution_id}",
                namespace=namespace,
                labels={
                    "app": "workflow-runner",
                    "workflow-id": execution_id,
                    "execution-id": execution_id,
                    "program": workflow_data['program_name']
                }
            )
            
            # Fetch AWS credentials from database
            aws_creds = await self._get_aws_credentials()

            # Build environment variables list
            env_vars = [
                # Core workflow configuration
                client.V1EnvVar(name="WORKFLOW_ID", value=workflow_data.get('workflow_id', '')),
                client.V1EnvVar(name="EXECUTION_ID", value=execution_id),
                client.V1EnvVar(name="PROGRAM_NAME", value=workflow_data['program_name']),
                client.V1EnvVar(name="WORKFLOW_NAME", value=workflow_data['name']),
                client.V1EnvVar(name="WORKFLOW_STEPS", value=str(workflow_data['steps'])),

                # Service URLs
                client.V1EnvVar(name="NATS_URL", value=os.getenv('NATS_URL')),
                client.V1EnvVar(name="API_URL", value=os.getenv('API_URL')),
                client.V1EnvVar(name="REDIS_URL", value=os.getenv('REDIS_URL')),

                # Internal API authentication (kubelet resolves from Secret; matches API bootstrap)
                client.V1EnvVar(
                    name="INTERNAL_SERVICE_API_KEY",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            name=os.getenv("INTERNAL_SERVICE_SECRET_NAME", "internal-service-secret"),
                            key="token",
                        )
                    ),
                ),

                # Kubernetes configuration
                client.V1EnvVar(name="KUBERNETES_NAMESPACE", value=namespace),
                client.V1EnvVar(name="WORKER_IMAGE", value=worker_image),
                client.V1EnvVar(name="IMAGE_PULL_POLICY", value=image_pull_policy),

                # Progressive Asset Streaming Configuration
                client.V1EnvVar(name="ENABLE_PROGRESSIVE_STREAMING", value=os.getenv('ENABLE_PROGRESSIVE_STREAMING', 'true')),
                client.V1EnvVar(name="PROGRESSIVE_MAX_RETRIES", value=os.getenv('PROGRESSIVE_MAX_RETRIES', '3')),
                client.V1EnvVar(name="PROGRESSIVE_RETRY_DELAY", value=os.getenv('PROGRESSIVE_RETRY_DELAY', '1.0')),
                client.V1EnvVar(name="PROGRESSIVE_RETRY_BACKOFF", value=os.getenv('PROGRESSIVE_RETRY_BACKOFF', '2.0')),
                client.V1EnvVar(name="PROGRESSIVE_MIN_ASSETS", value=os.getenv('PROGRESSIVE_MIN_ASSETS', '1')),
                client.V1EnvVar(name="PROGRESSIVE_MAX_CONCURRENT", value=os.getenv('PROGRESSIVE_MAX_CONCURRENT', '5')),
                client.V1EnvVar(name="PROGRESSIVE_SEND_TIMEOUT", value=os.getenv('PROGRESSIVE_SEND_TIMEOUT', '30.0')),

                # Memory Optimization Configuration
                client.V1EnvVar(name="STREAMING_ASSET_THRESHOLD", value=os.getenv('STREAMING_ASSET_THRESHOLD', '2500')),
                client.V1EnvVar(name="STREAMING_RESULT_THRESHOLD", value=os.getenv('STREAMING_RESULT_THRESHOLD', '500')),
                client.V1EnvVar(name="ASSET_BATCH_SIZE", value=os.getenv('ASSET_BATCH_SIZE', '100')),
                client.V1EnvVar(name="STREAMING_BATCH_SIZE", value=os.getenv('STREAMING_BATCH_SIZE', '1000')),
                client.V1EnvVar(name="MEMORY_LIMIT_MB", value=os.getenv('MEMORY_LIMIT_MB', '500')),
                client.V1EnvVar(name="LARGE_LIST_THRESHOLD", value=os.getenv('LARGE_LIST_THRESHOLD', '1000')),
                client.V1EnvVar(name="GC_THRESHOLD", value=os.getenv('GC_THRESHOLD', '50000')),
                client.V1EnvVar(name="STANDARD_PAGE_SIZE", value=os.getenv('STANDARD_PAGE_SIZE', '100')),
                client.V1EnvVar(name="STREAMING_PAGE_SIZE", value=os.getenv('STREAMING_PAGE_SIZE', '1000')),
                client.V1EnvVar(name="MAX_PAGES", value=os.getenv('MAX_PAGES', '1000')),

                # Typosquat caching configuration
                client.V1EnvVar(name="TYPOSQUAT_CACHE_TTL", value=os.getenv('TYPOSQUAT_CACHE_TTL', '2592000')),
                client.V1EnvVar(name="TYPOSQUAT_USE_CACHE", value=os.getenv('TYPOSQUAT_USE_CACHE', 'true'))
            ]

            # Add AWS credentials if available
            if aws_creds:
                logger.info("Adding AWS credentials to direct runner pod environment")
                env_vars.extend([
                    client.V1EnvVar(name="AWS_ACCESS_KEY_ID", value=aws_creds['access_key']),
                    client.V1EnvVar(name="AWS_SECRET_ACCESS_KEY", value=aws_creds['secret_access_key']),
                    client.V1EnvVar(name="AWS_DEFAULT_REGION", value=aws_creds['default_region'])
                ])
            else:
                logger.warning("No active AWS credentials found - direct pods will not have AWS access")

            # Create container
            container = client.V1Container(
                name="workflow-runner",
                image=runner_image,
                image_pull_policy=image_pull_policy,
                command=["/usr/local/bin/python"],
                args=["/app/run-workflow.py", "/workflow-data/workflow.json"],
                env=env_vars,
                volume_mounts=[
                    client.V1VolumeMount(
                        name="workflow-data",
                        mount_path="/workflow-data"
                    )
                ]
            )
            
            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "workflow-runner",
                        "workflow-id": workflow_data['workflow_id']
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="workflow-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="workflow.json",
                                        path="workflow.json"
                                    )
                                ]
                            )
                        )
                    ]
                )
            )
            
            # Create job spec
            spec = client.V1JobSpec(
                template=template,
                ttl_seconds_after_finished=job_ttl
            )
            
            # Create job
            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=metadata,
                spec=spec
            )
            
            # Create the job in Kubernetes
            created_job = self.batch_v1.create_namespaced_job(
                namespace=namespace,
                body=job
            )

            job_name_resolved = getattr(
                getattr(created_job, "metadata", None), "name", metadata.name
            )
            job_uid = getattr(getattr(created_job, "metadata", None), "uid", None)
            self._patch_workflow_configmap_owner_to_job(
                namespace, configmap_name, job_name_resolved, job_uid
            )
            
            job_name = getattr(getattr(created_job, 'metadata', None), 'name', 'unknown')
            logger.debug(f"Created Kubernetes job: {job_name}")
            return created_job
            
        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def get_job_status(self, type: str, id: str):
        """Get status of a Kubernetes job"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            job_name = f"{type}-{id}"
            return self.batch_v1.read_namespaced_job(name=job_name, namespace=namespace)
        except Exception as e:
            logger.error(f"Error getting job status: {str(e)}")
            raise

    def get_pod_logs(self, type: str, id: str) -> str:
        """Get logs from a Kubernetes pod"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            pod_name = f"{type}-{id}"
            return self.v1.read_namespaced_pod_log(name=pod_name, namespace=namespace)
        except Exception as e:
            logger.error(f"Error getting pod logs: {str(e)}")
            return ""

    def get_workflow_tasks(self, workflow_id: str):
        """Get all tasks for a workflow"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            return self.batch_v1.list_namespaced_job(
                namespace=namespace,
                label_selector=f"execution-id={workflow_id}"
            )
        except Exception as e:
            logger.error(f"Error getting workflow tasks: {str(e)}")
            raise

    def delete_job(self, workflow_id: str):
        """Delete a Kubernetes job"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            job_name = f"workflow-{workflow_id}"
            return self.batch_v1.delete_namespaced_job(name=job_name, namespace=namespace)
        except Exception as e:
            logger.error(f"Error deleting job: {str(e)}")
            raise

    def stop_workflow(self, workflow_id: str):
        """Stop a running workflow by deleting all associated resources"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            results = []
            
            # Delete jobs with the execution-id label
            logger.debug(f"Stopping workflow {workflow_id}: Deleting jobs...")
            try:
                jobs = self.batch_v1.list_namespaced_job(
                    namespace=namespace,
                    label_selector=f"execution-id={workflow_id}"
                )
                for job in jobs.items:
                    logger.debug(f"Deleting job: {job.metadata.name}")
                    self.batch_v1.delete_namespaced_job(
                        name=job.metadata.name,
                        namespace=namespace,
                        propagation_policy='Background'
                    )
                    results.append(f"Deleted job: {job.metadata.name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Error deleting jobs: {e}")
                    results.append(f"Warning: {e}")
            
            # Delete pods with the execution-id label
            logger.debug(f"Stopping workflow {workflow_id}: Deleting pods...")
            try:
                pods = self.v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"execution-id={workflow_id}"
                )
                for pod in pods.items:
                    logger.debug(f"Deleting pod: {pod.metadata.name}")
                    self.v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=namespace,
                        grace_period_seconds=0
                    )
                    results.append(f"Deleted pod: {pod.metadata.name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Error deleting pods: {e}")
                    results.append(f"Warning: {e}")
            
            # Delete kueue workloads
            logger.debug(f"Stopping workflow {workflow_id}: Deleting kueue workloads...")
            try:
                workloads = self.custom_objects_v1.list_namespaced_custom_object(
                    group="kueue.x-k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="workloads",
                    label_selector=f"execution-id={workflow_id}"
                )
                for workload in workloads.get('items', []):
                    if isinstance(workload, dict) and 'metadata' in workload and 'name' in workload['metadata']:
                        workload_name = workload['metadata']['name']
                        logger.debug(f"Deleting kueue workload: {workload_name}")
                        self.custom_objects_v1.delete_namespaced_custom_object(
                            group="kueue.x-k8s.io",
                            version="v1beta1",
                            namespace=namespace,
                            plural="workloads",
                            name=workload_name
                        )
                        results.append(f"Deleted kueue workload: {workload_name}")
            except ApiException as e:
                if e.status != 404:  # Ignore if not found
                    logger.warning(f"Error deleting kueue workloads: {e}")
                    results.append(f"Warning: {e}")
            except Exception as e:
                logger.warning(f"Error accessing kueue workloads (may not be installed): {e}")
                results.append(f"Warning: Could not access kueue workloads: {e}")
            
            # Clean up worker jobs with workflow-id label
            logger.debug(f"Stopping workflow {workflow_id}: Cleaning up worker jobs...")
            try:
                worker_jobs = self.batch_v1.list_namespaced_job(
                    namespace=namespace,
                    label_selector=f"workflow-id={workflow_id}"
                )
                for job in worker_jobs.items:
                    logger.debug(f"Cleaning up worker job: {job.metadata.name}")
                    self.batch_v1.delete_namespaced_job(
                        name=job.metadata.name,
                        namespace=namespace,
                        propagation_policy='Background'
                    )
                    results.append(f"Cleaned up worker job: {job.metadata.name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error cleaning up worker jobs: {e}")
                    results.append(f"Warning: {e}")
            
            # Clean up any remaining worker/runner jobs that match common patterns (fallback)
            logger.debug(f"Stopping workflow {workflow_id}: Cleaning up remaining worker/runner jobs...")
            try:
                all_jobs = self.batch_v1.list_namespaced_job(namespace=namespace)
                for job in all_jobs.items:
                    job_name = job.metadata.name
                    # Check if this is a worker or runner job that might be related
                    if (job_name.startswith('worker-') or job_name.startswith('runner-')) and workflow_id in job_name:
                        logger.debug(f"Cleaning up related job: {job_name}")
                        self.batch_v1.delete_namespaced_job(
                            name=job_name,
                            namespace=namespace,
                            propagation_policy='Background'
                        )
                        results.append(f"Cleaned up job: {job_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error cleaning up worker/runner jobs: {e}")
                    results.append(f"Warning: {e}")
            
            # Clean up worker pods with workflow-id label
            logger.debug(f"Stopping workflow {workflow_id}: Cleaning up worker pods...")
            try:
                worker_pods = self.v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"workflow-id={workflow_id}"
                )
                for pod in worker_pods.items:
                    logger.debug(f"Cleaning up worker pod: {pod.metadata.name}")
                    self.v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=namespace,
                        grace_period_seconds=0
                    )
                    results.append(f"Cleaned up worker pod: {pod.metadata.name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error cleaning up worker pods: {e}")
                    results.append(f"Warning: {e}")
            
            # Clean up any remaining worker/runner pods that match common patterns (fallback)
            logger.debug(f"Stopping workflow {workflow_id}: Cleaning up remaining worker/runner pods...")
            try:
                all_pods = self.v1.list_namespaced_pod(namespace=namespace)
                for pod in all_pods.items:
                    pod_name = pod.metadata.name
                    # Check if this is a worker or runner pod that might be related
                    if (pod_name.startswith('worker-') or pod_name.startswith('runner-')) and workflow_id in pod_name:
                        logger.debug(f"Cleaning up related pod: {pod_name}")
                        self.v1.delete_namespaced_pod(
                            name=pod_name,
                            namespace=namespace,
                            grace_period_seconds=0
                        )
                        results.append(f"Cleaned up pod: {pod_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error cleaning up worker/runner pods: {e}")
                    results.append(f"Warning: {e}")
            
            # Delete the ConfigMap for the workflow data
            logger.debug(f"Stopping workflow {workflow_id}: Deleting ConfigMap...")
            try:
                configmap_name = f"workflow-data-{workflow_id}"
                self.v1.delete_namespaced_config_map(
                    name=configmap_name,
                    namespace=namespace
                )
                results.append(f"Deleted ConfigMap: {configmap_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error deleting ConfigMap: {e}")
                    results.append(f"Warning: {e}")
            
            logger.debug(f"Workflow {workflow_id} stopping completed")
            return results
            
        except Exception as e:
            logger.error(f"Error stopping workflow {workflow_id}: {str(e)}")
            raise

    def list_deployments(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all Deployments in the namespace with image, replica, and status info."""
        namespace = namespace or os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
        except ApiException as e:
            logger.error(f"Failed to list deployments in {namespace}: {e}")
            return []

        results: List[Dict[str, Any]] = []
        for dep in deployments.items:
            containers = dep.spec.template.spec.containers or []
            container = containers[0] if containers else None
            image = container.image if container else "unknown"

            app_version = self._read_pod_env(
                dep.spec.selector.match_labels,
                container.name if container else None,
                namespace,
            )

            desired = dep.spec.replicas or 0
            ready = dep.status.ready_replicas or 0

            status = "available"
            for cond in (dep.status.conditions or []):
                if cond.type == "Available" and cond.status != "True":
                    status = "degraded"
                    break
                if cond.type == "Progressing" and cond.reason == "ReplicaSetUpdated":
                    status = "progressing"

            results.append({
                "name": dep.metadata.name,
                "image": image,
                "app_version": app_version,
                "ready_replicas": ready,
                "desired_replicas": desired,
                "status": status,
            })
        return results

    def _read_pod_env(
        self,
        match_labels: Dict[str, str],
        container_name: Optional[str],
        namespace: str,
    ) -> Optional[str]:
        """Exec into a running pod to read the APP_VERSION env var baked into its image."""
        label_selector = ",".join(f"{k}={v}" for k, v in (match_labels or {}).items())
        try:
            pods = self.v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
                field_selector="status.phase=Running",
                limit=1,
            )
            if not pods.items:
                return None

            pod_name = pods.items[0].metadata.name
            kwargs: Dict[str, Any] = {
                "command": ["sh", "-c", "echo $APP_VERSION"],
                "stderr": False,
                "stdin": False,
                "stdout": True,
                "tty": False,
            }
            if container_name:
                kwargs["container"] = container_name

            resp = stream(
                self.v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                **kwargs,
            )
            value = resp.strip() if resp else None
            return value or None
        except Exception as e:
            logger.debug(f"Could not read APP_VERSION from pod ({label_selector}): {e}")
            return None

    # --- Kueue maintenance (ClusterQueue stopPolicy) & database restore Job ---

    KUEUE_CLUSTER_QUEUE_NAMES = (
        "runner-cluster-queue",
        "worker-cluster-queue",
        "ai-analysis-cluster-queue",
    )

    _TERMINAL_WORKLOAD_CONDITIONS = frozenset({"Finished", "Failed", "Rejected"})

    def patch_cluster_queue_stop_policy(self, name: str, stop_policy: Optional[str]) -> None:
        """Patch a ClusterQueue spec.stopPolicy (Hold, HoldAndDrain, or clear with None)."""
        body: Dict[str, Any] = {"spec": {"stopPolicy": stop_policy}}
        try:
            # Merge-patch is the client default; _content_type is not supported (kubernetes client v35+).
            self.custom_objects_v1.patch_cluster_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                plural="clusterqueues",
                name=name,
                body=body,
            )
            logger.info("patched ClusterQueue %s stopPolicy=%s", name, stop_policy)
        except ApiException as e:
            logger.error("patch ClusterQueue %s failed: %s", name, e)
            raise

    def set_all_cluster_queues_hold(self) -> List[str]:
        """Set stopPolicy Hold on all ClusterQueues (no new admissions; admitted workloads run to completion).

        Prefer this for DB maintenance. HoldAndDrain evicts admitted workloads and causes restarts when
        the policy is cleared — see Kueue ClusterQueue stopPolicy docs.
        """
        updated: List[str] = []
        for name in self.KUEUE_CLUSTER_QUEUE_NAMES:
            self.patch_cluster_queue_stop_policy(name, "Hold")
            updated.append(name)
        return updated

    def clear_all_cluster_queues_stop_policy(self) -> List[str]:
        cleared: List[str] = []
        for name in self.KUEUE_CLUSTER_QUEUE_NAMES:
            self.patch_cluster_queue_stop_policy(name, None)
            cleared.append(name)
        return cleared

    def get_cluster_queue_stop_policies(self) -> Dict[str, Optional[str]]:
        policies: Dict[str, Optional[str]] = {}
        for name in self.KUEUE_CLUSTER_QUEUE_NAMES:
            try:
                obj = self.custom_objects_v1.get_cluster_custom_object(
                    group="kueue.x-k8s.io",
                    version="v1beta1",
                    plural="clusterqueues",
                    name=name,
                )
                policies[name] = (obj.get("spec") or {}).get("stopPolicy")
            except ApiException as e:
                logger.warning("get ClusterQueue %s: %s", name, e)
                policies[name] = None
        return policies

    def count_active_kueue_workloads(self) -> tuple[int, List[str]]:
        """Workloads whose last condition type is not terminal (Finished/Failed/Rejected)."""
        namespace = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
        try:
            workloads = self.custom_objects_v1.list_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
            )
        except ApiException as e:
            logger.error("list workloads: %s", e)
            raise

        active_names: List[str] = []
        for item in workloads.get("items", []):
            meta = item.get("metadata") or {}
            name = str(meta.get("name", ""))
            conditions = (item.get("status") or {}).get("conditions") or []
            if not conditions:
                active_names.append(name)
                continue
            last_type = str((conditions[-1] or {}).get("type", ""))
            if last_type not in self._TERMINAL_WORKLOAD_CONDITIONS:
                active_names.append(name)
        return len(active_names), active_names

    def count_running_batch_jobs_exclude_restore(self, name_prefix_exclude: str = "db-restore-") -> tuple[int, List[str]]:
        """Batch Jobs with status.active > 0, excluding database restore Jobs by name prefix."""
        namespace = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
        running: List[str] = []
        try:
            jobs = self.batch_v1.list_namespaced_job(namespace=namespace)
        except ApiException as e:
            logger.error("list jobs: %s", e)
            raise
        for job in jobs.items or []:
            jn = job.metadata.name or ""
            if jn.startswith(name_prefix_exclude):
                continue
            active = (job.status.active or 0) if job.status else 0
            if active > 0:
                running.append(jn)
        return len(running), running

    def create_database_restore_job(
        self,
        job_name: str,
        pull_token: str,
        staging_id: str,
        *,
        api_internal_base: str,
        curl_image: str = "curlimages/curl:8.6.0",
        postgres_image: str = "postgres:15",
    ) -> client.V1Job:
        """
        Job with curl initContainer to pull the dump from the API, then pg_restore in postgres image.
        """
        namespace = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
        pull_url = f"{api_internal_base.rstrip('/')}/internal/database-restore/pull"

        work_vol = client.V1Volume(name="dump-work", empty_dir=client.V1EmptyDirVolumeSource())

        init_env = [
            client.V1EnvVar(name="PULL_TOKEN", value=pull_token),
            client.V1EnvVar(name="API_PULL_URL", value=pull_url),
            client.V1EnvVar(
                name="INTERNAL_SERVICE_API_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="internal-service-secret",
                        key="token",
                        optional=True,
                    )
                ),
            ),
        ]
        init_container = client.V1Container(
            name="fetch-dump",
            image=curl_image,
            command=[
                "sh",
                "-c",
                'exec curl -fsS -G -H "Authorization: Bearer ${INTERNAL_SERVICE_API_KEY}" '
                '--data-urlencode "token=${PULL_TOKEN}" "${API_PULL_URL}" -o /work/dump',
            ],
            env=init_env,
            volume_mounts=[client.V1VolumeMount(name="dump-work", mount_path="/work")],
        )

        main_env = [
            client.V1EnvVar(name="POSTGRES_HOST", value="postgresql"),
            client.V1EnvVar(
                name="DATABASE_NAME",
                value_from=client.V1EnvVarSource(
                    config_map_key_ref=client.V1ConfigMapKeySelector(
                        name="service-config",
                        key="database.name",
                    )
                ),
            ),
            client.V1EnvVar(
                name="POSTGRES_USER",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="postgres-secret",
                        key="postgres-root-username",
                    )
                ),
            ),
            client.V1EnvVar(
                name="POSTGRES_PASSWORD",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="postgres-secret",
                        key="postgres-root-password",
                    )
                ),
            ),
            client.V1EnvVar(
                name="PGPASSWORD",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="postgres-secret",
                        key="postgres-root-password",
                    )
                ),
            ),
        ]
        restore_cmd = (
            "set -euo pipefail; "
            "trap 'rm -f /work/dump' EXIT; "
            "pg_restore -h \"${POSTGRES_HOST}\" -p 5432 "
            "-U \"${POSTGRES_USER}\" -d \"${DATABASE_NAME}\" "
            "--no-owner --no-acl --clean --if-exists --exit-on-error /work/dump"
        )
        main_container = client.V1Container(
            name="pg-restore",
            image=postgres_image,
            command=["bash", "-lc", restore_cmd],
            env=main_env,
            volume_mounts=[client.V1VolumeMount(name="dump-work", mount_path="/work")],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "256Mi"},
                limits={"cpu": "2", "memory": "2Gi"},
            ),
        )

        ttl = int(os.getenv("DATABASE_RESTORE_JOB_TTL_SECONDS", "3600"))
        deadline = int(os.getenv("DATABASE_RESTORE_JOB_ACTIVE_DEADLINE_SEC", "86400"))

        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            volumes=[work_vol],
            init_containers=[init_container],
            containers=[main_container],
        )
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={"app": "database-restore"},
                annotations={"reconhawx.io/db-restore-staging-id": staging_id},
            ),
            spec=pod_spec,
        )

        job_spec = client.V1JobSpec(
            template=template,
            backoff_limit=0,
            ttl_seconds_after_finished=ttl,
            active_deadline_seconds=deadline,
        )

        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={"app": "database-restore"},
                annotations={"reconhawx.io/db-restore-staging-id": staging_id},
            ),
            spec=job_spec,
        )

        try:
            created = self.batch_v1.create_namespaced_job(namespace=namespace, body=job)
            logger.warning(
                "created database restore Job %s namespace=%s staging_id=%s",
                job_name,
                namespace,
                staging_id,
            )
            return created
        except ApiException as e:
            logger.error("create restore Job failed: %s", e)
            raise

    def read_namespaced_job_status(self, job_name: str) -> Dict[str, Any]:
        namespace = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
        try:
            job = self.batch_v1.read_namespaced_job_status(name=job_name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                return {"found": False}
            raise
        status_obj = job.status
        st: Dict[str, Any] = {
            "found": True,
            "active": status_obj.active if status_obj else 0,
            "succeeded": status_obj.succeeded if status_obj else 0,
            "failed": status_obj.failed if status_obj else 0,
            "start_time": status_obj.start_time.isoformat() if status_obj and status_obj.start_time else None,
            "completion_time": status_obj.completion_time.isoformat()
            if status_obj and status_obj.completion_time
            else None,
            "conditions": [],
        }
        if status_obj and status_obj.conditions:
            for c in status_obj.conditions:
                st["conditions"].append(
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason,
                        "message": c.message,
                    }
                )
        # terminal heuristic for callers
        if st.get("succeeded"):
            st["phase"] = "succeeded"
        elif st.get("failed"):
            st["phase"] = "failed"
        elif (st.get("active") or 0) > 0:
            st["phase"] = "active"
        else:
            st["phase"] = "unknown"
        return st