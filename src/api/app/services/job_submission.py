from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
import logging
import json
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _internal_service_api_key_env_var() -> client.V1EnvVar:
    """Env var resolved from the same Secret the API bootstraps (see main.initialize_internal_service_token)."""
    return client.V1EnvVar(
        name="INTERNAL_SERVICE_API_KEY",
        value_from=client.V1EnvVarSource(
            secret_key_ref=client.V1SecretKeySelector(
                name=os.getenv("INTERNAL_SERVICE_SECRET_NAME", "internal-service-secret"),
                key="token",
            )
        ),
    )


class JobSubmissionService:
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

    def _patch_configmap_owner_to_batch_job(
        self,
        namespace: str,
        configmap_name: str,
        job_name: str,
        job_uid: Optional[str],
    ) -> None:
        """Link ConfigMap lifecycle to the Batch Job so GC deletes it with the Job (e.g. ttlSecondsAfterFinished)."""
        if not job_uid:
            logger.error(
                "Cannot set ConfigMap owner: Job %s has no uid; %s may be orphaned",
                job_name,
                configmap_name,
            )
            return
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
                "Set ownerReferences on ConfigMap %s -> Job %s (%s)",
                configmap_name,
                job_name,
                job_uid,
            )
        except ApiException as e:
            logger.error(
                "Failed to patch ConfigMap %s with Job ownerReference: %s",
                configmap_name,
                e,
            )
            raise
        
    def create_phishlabs_batch_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for PhishLabs batch processing"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')
            int(os.getenv('JOB_TTL_SECONDS', '300'))
            
            # Create ConfigMap with job data
            configmap_name = f"job-data-{job_id}"
            
            job_json = json.dumps(job_data)
            logger.debug(f"Creating PhishLabs batch job {job_id} with data: {job_data}")
            
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "phishlabs_batch"
                    }
                ),
                data={
                    "job_data.json": job_json
                }
            )
            
            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise
            
            # Create job metadata with Kueue annotations
            metadata = client.V1ObjectMeta(
                name=f"job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "phishlabs_batch",
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                },
                annotations={
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                }
            )

            # Create container with resource requests/limits
            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    # PostgreSQL connection
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),
                    _internal_service_api_key_env_var(),

                    # Logging
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    limits={
                        "cpu": "500m",
                        "memory": "512Mi"
                    }
                ),
                volume_mounts=[
                    client.V1VolumeMount(
                        name="job-data",
                        mount_path="/app/job-data"
                    )
                ]
            )
            
            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "phishlabs_batch"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="job_data.json",
                                        path="job_data.json"
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
                backoff_limit=0,  # Prevent retries
                ttl_seconds_after_finished=300  # 5 minutes TTL
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
            
            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job
            
        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def create_ai_analysis_batch_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for AI analysis batch processing."""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')
            int(os.getenv('JOB_TTL_SECONDS', '300'))

            configmap_name = f"ai-analysis-job-data-{job_id}"
            job_json = json.dumps(job_data)
            logger.debug(f"Creating AI analysis batch job {job_id} with data: {job_data}")

            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "ai_analysis_batch"
                    }
                ),
                data={"job_data.json": job_json}
            )

            try:
                self.v1.create_namespaced_config_map(namespace=namespace, body=configmap)
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise

            ai_analysis_queue = os.getenv("KUEUE_AI_ANALYSIS_QUEUE", "recon-ai-analysis-queue")
            metadata = client.V1ObjectMeta(
                name=f"ai-analysis-job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "ai_analysis_batch",
                    "kueue.x-k8s.io/queue-name": ai_analysis_queue
                },
                annotations={"kueue.x-k8s.io/queue-name": ai_analysis_queue}
            )

            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),
                    _internal_service_api_key_env_var(),
                    client.V1EnvVar(name="API_BASE_URL", value=os.getenv('API_BASE_URL', 'http://api:8000')),
                    client.V1EnvVar(name="OLLAMA_URL", value=os.getenv('OLLAMA_URL', 'http://ollama:11434')),
                    client.V1EnvVar(name="OLLAMA_MODEL", value=os.getenv('OLLAMA_MODEL', 'llama3:latest')),
                    client.V1EnvVar(name="OLLAMA_TIMEOUT", value=os.getenv('OLLAMA_TIMEOUT', '900')),
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={"cpu": "500m", "memory": "512Mi"},
                    limits={"cpu": "2000m", "memory": "2Gi"}
                ),
                volume_mounts=[
                    client.V1VolumeMount(name="job-data", mount_path="/app/job-data")
                ]
            )

            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "ai_analysis_batch"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[client.V1KeyToPath(key="job_data.json", path="job_data.json")]
                            )
                        )
                    ]
                )
            )

            spec = client.V1JobSpec(
                template=template,
                backoff_limit=0,
                ttl_seconds_after_finished=300
            )

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=metadata,
                spec=spec
            )

            created_job = self.batch_v1.create_namespaced_job(namespace=namespace, body=job)
            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"ai-analysis-job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job

        except Exception as e:
            logger.error(f"Error creating AI analysis batch job: {str(e)}")
            raise

    def create_dummy_batch_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for dummy batch processing (testing purposes)"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')
            int(os.getenv('JOB_TTL_SECONDS', '300'))
            
            # Create ConfigMap with job data
            configmap_name = f"job-data-{job_id}"
            
            job_json = json.dumps(job_data)
            logger.debug(f"Creating dummy batch job {job_id} with data: {job_data}")
            
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "dummy_batch"
                    }
                ),
                data={
                    "job_data.json": job_json
                }
            )
            
            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise
            
            # Create job metadata with Kueue annotations
            metadata = client.V1ObjectMeta(
                name=f"job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "dummy_batch",
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                },
                annotations={
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                }
            )
            
            # Create container with resource requests/limits
            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    # Service URLs
                    client.V1EnvVar(name="MONGO_URI", value=os.getenv('MONGO_URI')),
                    client.V1EnvVar(name="MONGO_DATABASE_NAME", value="recon_db"),

                    # PostgreSQL connection
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),

                    # Logging
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    limits={
                        "cpu": "500m",
                        "memory": "512Mi"
                    }
                ),
                volume_mounts=[
                    client.V1VolumeMount(
                        name="job-data",
                        mount_path="/app/job-data"
                    )
                ]
            )
            
            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "dummy_batch"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="job_data.json",
                                        path="job_data.json"
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
                backoff_limit=0,  # Prevent retries
                ttl_seconds_after_finished=300  # 5 minutes TTL
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
            
            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job
            
        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def create_typosquat_batch_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for typosquat batch processing"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')
            int(os.getenv('JOB_TTL_SECONDS', '300'))

            # Create ConfigMap with job data
            configmap_name = f"job-data-{job_id}"

            job_json = json.dumps(job_data)
            logger.debug(f"Creating typosquat batch job {job_id} with data: {job_data}")

            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "typosquat_batch"
                    }
                ),
                data={
                    "job_data.json": job_json
                }
            )

            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise

            # Create job metadata with Kueue annotations
            metadata = client.V1ObjectMeta(
                name=f"job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "typosquat_batch",
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                },
                annotations={
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                }
            )

            # Create container with resource requests/limits
            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    # PostgreSQL connection
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),
                    _internal_service_api_key_env_var(),

                    # Logging
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    limits={
                        "cpu": "500m",
                        "memory": "512Mi"
                    }
                ),
                volume_mounts=[
                    client.V1VolumeMount(
                        name="job-data",
                        mount_path="/app/job-data"
                    )
                ]
            )

            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "typosquat_batch"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="job_data.json",
                                        path="job_data.json"
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
                backoff_limit=0,  # Prevent retries
                ttl_seconds_after_finished=300  # 5 minutes TTL
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

            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job

        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def create_gather_api_findings_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for gathering API findings"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')

            # Create ConfigMap with job data
            configmap_name = f"job-data-{job_id}"

            job_json = json.dumps(job_data)
            logger.debug(f"Creating gather API findings job {job_id} with data: {job_data}")

            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "gather_api_findings"
                    }
                ),
                data={
                    "job_data.json": job_json
                }
            )

            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise

            # Create job metadata with Kueue annotations
            metadata = client.V1ObjectMeta(
                name=f"job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "gather_api_findings",
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                },
                annotations={
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                }
            )

            # Create container with resource requests/limits
            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    # PostgreSQL connection
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),

                    # API configuration
                    client.V1EnvVar(name="API_BASE_URL", value=os.getenv('API_BASE_URL', 'http://api:8000')),
                    _internal_service_api_key_env_var(),

                    # Logging
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    limits={
                        "cpu": "500m",
                        "memory": "512Mi"
                    }
                ),
                volume_mounts=[
                    client.V1VolumeMount(
                        name="job-data",
                        mount_path="/app/job-data"
                    )
                ]
            )

            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "gather_api_findings"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="job_data.json",
                                        path="job_data.json"
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
                backoff_limit=0,  # Prevent retries
                ttl_seconds_after_finished=300  # 5 minutes TTL
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

            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job

        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def create_sync_recordedfuture_data_job(self, job_id: str, job_data: Dict[str, Any]):
        """Create a Kubernetes job for syncing RecordedFuture data"""
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            runner_image = os.getenv('RUNNER_IMAGE', 'runner:latest')
            service_account = os.getenv('RUNNER_SERVICE_ACCOUNT', 'runner-service-account')

            # Create ConfigMap with job data
            configmap_name = f"job-data-{job_id}"

            job_json = json.dumps(job_data)
            logger.debug(f"Creating sync RecordedFuture data job {job_id} with data: {job_data}")

            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace,
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "sync_recordedfuture_data"
                    }
                ),
                data={
                    "job_data.json": job_json
                }
            )

            try:
                self.v1.create_namespaced_config_map(
                    namespace=namespace,
                    body=configmap
                )
                logger.debug(f"Created ConfigMap {configmap_name} for job data")
            except ApiException as e:
                logger.error(f"Failed to create ConfigMap: {e}")
                raise

            # Create job metadata with Kueue annotations
            metadata = client.V1ObjectMeta(
                name=f"job-{job_id}",
                namespace=namespace,
                labels={
                    "app": "background-job",
                    "job-id": job_id,
                    "job-type": "sync_recordedfuture_data",
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                },
                annotations={
                    "kueue.x-k8s.io/queue-name": "recon-runner-queue"
                }
            )

            # Create container with resource requests/limits
            container = client.V1Container(
                name="job-runner",
                image=runner_image,
                image_pull_policy=os.getenv('IMAGE_PULL_POLICY', 'Always'),
                command=["/usr/local/bin/python"],
                args=["/app/run-job.py"],
                env=[
                    # PostgreSQL connection
                    client.V1EnvVar(name="POSTGRES_HOST", value=os.getenv('POSTGRES_HOST', 'postgresql')),
                    client.V1EnvVar(name="POSTGRES_PORT", value=os.getenv('POSTGRES_PORT', '5432')),
                    client.V1EnvVar(name="DATABASE_NAME", value=os.getenv('DATABASE_NAME', 'recon_db')),
                    client.V1EnvVar(name="POSTGRES_USER", value=os.getenv('POSTGRES_USER', 'admin')),
                    client.V1EnvVar(name="POSTGRES_PASSWORD", value=os.getenv('POSTGRES_PASSWORD', 'password')),

                    # API configuration
                    client.V1EnvVar(name="API_BASE_URL", value=os.getenv('API_BASE_URL', 'http://api:8000')),
                    _internal_service_api_key_env_var(),

                    # Logging
                    client.V1EnvVar(name="LOG_LEVEL", value=os.getenv('LOG_LEVEL', 'INFO')),
                ],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    limits={
                        "cpu": "500m",
                        "memory": "512Mi"
                    }
                ),
                volume_mounts=[
                    client.V1VolumeMount(
                        name="job-data",
                        mount_path="/app/job-data"
                    )
                ]
            )

            # Create pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "background-job",
                        "job-id": job_id,
                        "job-type": "sync_recordedfuture_data"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    service_account_name=service_account,
                    restart_policy="Never",
                    node_selector={"reconhawx.runner": "true"},
                    volumes=[
                        client.V1Volume(
                            name="job-data",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name,
                                items=[
                                    client.V1KeyToPath(
                                        key="job_data.json",
                                        path="job_data.json"
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
                backoff_limit=0,  # Prevent retries
                ttl_seconds_after_finished=300  # 5 minutes TTL
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

            job_name = getattr(getattr(created_job, 'metadata', None), 'name', None) or f"job-{job_id}"
            job_uid = getattr(getattr(created_job, 'metadata', None), 'uid', None)
            logger.debug(f"Created Kubernetes job: {job_name}")
            self._patch_configmap_owner_to_batch_job(
                namespace, configmap_name, job_name, job_uid
            )
            return created_job

        except Exception as e:
            logger.error(f"Error creating Kubernetes job: {str(e)}")
            raise

    def get_job_status(self, job_id: str, job_type: Optional[str] = None):
        """Get the status of a Kubernetes job.
        
        job_type: When 'ai_analysis_batch', looks up ai-analysis-job-{job_id}.
                  Otherwise looks up job-{job_id}.
        """
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            job_name = f"ai-analysis-job-{job_id}" if job_type == "ai_analysis_batch" else f"job-{job_id}"
            
            job = self.batch_v1.read_namespaced_job(
                name=job_name,
                namespace=namespace
            )
            
            # Return the actual Kubernetes job object
            return job
            
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error(f"Error getting job status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting job status: {str(e)}")
            raise
    
    def delete_job(self, job_id: str, job_type: Optional[str] = None):
        """Delete a Kubernetes job and its ConfigMap.
        
        job_type: When 'ai_analysis_batch', deletes ai-analysis-job-{job_id} and
                  ai-analysis-job-data-{job_id}. Otherwise job-{job_id} and job-data-{job_id}.
        """
        try:
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'recon')
            if job_type == "ai_analysis_batch":
                job_name = f"ai-analysis-job-{job_id}"
                configmap_name = f"ai-analysis-job-data-{job_id}"
            else:
                job_name = f"job-{job_id}"
                configmap_name = f"job-data-{job_id}"
            
            # Delete the job
            try:
                self.batch_v1.delete_namespaced_job(
                    name=job_name,
                    namespace=namespace
                )
                logger.debug(f"Deleted Kubernetes job: {job_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.error(f"Error deleting job: {e}")
                    raise
            
            # Delete the ConfigMap
            try:
                self.v1.delete_namespaced_config_map(
                    name=configmap_name,
                    namespace=namespace
                )
                logger.debug(f"Deleted ConfigMap: {configmap_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.error(f"Error deleting ConfigMap: {e}")
                    raise
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting job: {str(e)}")
            raise 