from kubernetes import client, config
from kubernetes.client.rest import ApiException
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
        self.batch_v1 = client.BatchV1Api()
        self.custom_objects_v1 = client.CustomObjectsApi()

        # Kueue configuration
        self.kueue_enabled = os.getenv('KUEUE_ENABLED', 'true').lower() == 'true'
        self.kueue_workflow_queue = os.getenv('KUEUE_WORKFLOW_QUEUE', 'recon-runner-queue')
        self.kueue_cluster_queue = os.getenv('KUEUE_CLUSTER_QUEUE', 'cluster-queue')
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
        namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
        runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
        worker_image = os.getenv('WORKER_IMAGE', 'worker:latest')
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
            {"name": "IMAGE_PULL_POLICY", "value": os.getenv('IMAGE_PULL_POLICY', 'Always')},

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
            "imagePullPolicy": os.getenv('IMAGE_PULL_POLICY', 'Always'),
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
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            worker_image = os.getenv('WORKER_IMAGE', 'worker:latest')
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
                client.V1EnvVar(name="IMAGE_PULL_POLICY", value=os.getenv('IMAGE_PULL_POLICY', 'Always')),

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
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY'),
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