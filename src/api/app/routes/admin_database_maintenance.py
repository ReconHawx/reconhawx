"""Superuser maintenance: system_settings toggle, Kueue ClusterQueue Hold, Job-based pg_restore."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

from auth.dependencies import require_superuser
from models.user_postgres import UserResponse
from repository import AdminRepository
from repository.action_log_repo import ActionLogRepository
from services import database_backup_service as dbs
from services import maintenance_settings as maint_cfg
from services import restore_staging
from services.kubernetes import KubernetesService

logger = logging.getLogger(__name__)

router = APIRouter()


class MaintenanceSettingsUpdate(BaseModel):
    enabled: bool = False
    message: Optional[str] = Field(default="")


@router.get("/database/maintenance/settings")
async def get_maintenance_settings(
    current_user: UserResponse = Depends(require_superuser),
):
    repo = AdminRepository()
    row = await repo.get_system_setting(maint_cfg.SYSTEM_SETTINGS_KEY)
    raw = (row or {}).get("value") if isinstance((row or {}).get("value"), dict) else {}
    db_enabled = bool(raw.get("enabled", False))
    db_message = str(raw.get("message") or "").strip()

    env_on = maint_cfg.env_maintenance_active()
    env_msg = maint_cfg.env_message_override()

    enabled_effective = env_on or db_enabled
    if env_msg:
        message_effective = env_msg
    elif db_message:
        message_effective = db_message
    else:
        message_effective = maint_cfg.DEFAULT_DETAIL_MESSAGE

    return {
        "status": "success",
        "settings": {
            "enabled": db_enabled,
            "message": db_message,
        },
        "effective": {
            "enabled": enabled_effective,
            "message": message_effective,
            "env_override_active": env_on,
        },
    }


@router.put("/database/maintenance/settings")
async def put_maintenance_settings(
    body: MaintenanceSettingsUpdate,
    current_user: UserResponse = Depends(require_superuser),
):
    repo = AdminRepository()
    value: Dict[str, Any] = {
        "enabled": body.enabled,
        "message": (body.message or "").strip(),
    }
    await repo.set_system_setting(maint_cfg.SYSTEM_SETTINGS_KEY, value)
    maint_cfg.bump_cache_generation()

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="maintenance",
        action_type="maintenance_settings_update",
        user_id=str(current_user.id),
        metadata={"enabled": body.enabled},
    )

    return {"status": "success", "settings": value}


@router.post("/database/maintenance/kueue/hold")
@router.post("/database/maintenance/kueue/hold-drain")
async def kueue_hold_cluster_queues(
    current_user: UserResponse = Depends(require_superuser),
):
    """Apply Kueue stopPolicy **Hold** on all ClusterQueues (legacy path: hold-drain).

    **Hold** stops new admissions; admitted workloads run to completion. **Do not** use HoldAndDrain
    for graceful drain — it evicts running workloads (they restart when the policy is cleared).
    """
    k8s = KubernetesService()
    try:
        names = k8s.set_all_cluster_queues_hold()
    except ApiException as e:
        logger.error("Kueue hold: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="kueue",
        action_type="kueue_hold",
        user_id=str(current_user.id),
        metadata={"cluster_queues": names, "stop_policy": "Hold"},
    )
    return {"status": "success", "patched_cluster_queues": names, "stop_policy": "Hold"}


@router.post("/database/maintenance/kueue/clear-stop-policy")
async def kueue_clear_stop_policy(
    current_user: UserResponse = Depends(require_superuser),
):
    k8s = KubernetesService()
    try:
        names = k8s.clear_all_cluster_queues_stop_policy()
    except ApiException as e:
        logger.error("Kueue clear stopPolicy: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="kueue",
        action_type="kueue_clear_stop_policy",
        user_id=str(current_user.id),
        metadata={"cluster_queues": names},
    )
    return {"status": "success", "cleared_cluster_queues": names}


@router.get("/database/maintenance/kueue/drain-status")
async def kueue_drain_status(
    current_user: UserResponse = Depends(require_superuser),
):
    k8s = KubernetesService()
    try:
        policies = k8s.get_cluster_queue_stop_policies()
        w_count, w_names = k8s.count_active_kueue_workloads()
        j_count, j_names = k8s.count_running_batch_jobs_exclude_restore()
    except ApiException as e:
        logger.error("drain status: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    return {
        "status": "success",
        "cluster_queue_stop_policies": policies,
        "active_kueue_workloads_count": w_count,
        "active_kueue_workloads": w_names[:100],
        "running_batch_jobs_count": j_count,
        "running_batch_jobs": j_names[:100],
    }


def _all_cluster_queues_on_hold(k8s: KubernetesService, policies: Dict[str, Any]) -> bool:
    for name in k8s.KUEUE_CLUSTER_QUEUE_NAMES:
        if policies.get(name) != "Hold":
            return False
    return True


@router.post("/database/maintenance/kueue/flush-batch-jobs")
async def kueue_flush_batch_jobs(
    current_user: UserResponse = Depends(require_superuser),
):
    """Delete all Batch Jobs in the app namespace (except db-restore-*), only when all ClusterQueues are on Hold."""
    k8s = KubernetesService()
    try:
        policies = k8s.get_cluster_queue_stop_policies()
    except ApiException as e:
        logger.error("flush batch jobs (policies): %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    if not _all_cluster_queues_on_hold(k8s, policies):
        raise HTTPException(
            status_code=409,
            detail="All ClusterQueues must be on Kueue Hold before flushing workloads.",
        )

    try:
        result = k8s.delete_all_batch_jobs_flush_kueue()
    except ApiException as e:
        logger.error("flush batch jobs: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="kueue",
        action_type="kueue_flush_batch_jobs",
        user_id=str(current_user.id),
        metadata={
            "namespace": result.get("namespace"),
            "deleted_count": result.get("deleted_count"),
            "skipped_restore_count": result.get("skipped_restore_count"),
            "deleted_job_names_sample": result.get("deleted_job_names"),
            "delete_errors": result.get("errors"),
        },
    )

    return {
        "status": "success",
        **result,
    }


@router.post("/database/maintenance/restore/stage")
async def maintenance_restore_stage(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_superuser),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a dump file")

    base = os.getenv("RESTORE_STAGING_DIR", "/tmp/reconhawx-restore-staging")
    os.makedirs(base, mode=0o700, exist_ok=True)

    max_bytes = dbs.max_restore_upload_bytes()
    total = 0
    fd, path = tempfile.mkstemp(prefix="reconhawx-restore-", suffix=".dump", dir=base)
    os.close(fd)
    try:
        with open(path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum restore size ({max_bytes} bytes)",
                    )
                out.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        staging_id, _pull = restore_staging.register_file(path)
        logger.warning(
            "restore stage user_id=%s staging_id=%s bytes=%s",
            current_user.id,
            staging_id,
            total,
        )
        return {"status": "success", "staging_id": staging_id, "bytes": total}
    except HTTPException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


class RestoreJobBody(BaseModel):
    staging_id: str = Field(..., min_length=8)
    confirm: str


@router.post("/database/maintenance/restore/job")
async def maintenance_restore_create_job(
    body: RestoreJobBody,
    current_user: UserResponse = Depends(require_superuser),
):
    if body.confirm != "RESTORE_DATABASE":
        raise HTTPException(
            status_code=400,
            detail='confirm must be exactly "RESTORE_DATABASE"',
        )

    rec = restore_staging.get_staging(body.staging_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Unknown or expired staging_id")

    api_base = (
        os.getenv("API_INTERNAL_URL")
        or os.getenv("API_URL")
        or "http://api:8000"
    ).rstrip("/")

    job_name = f"db-restore-{int(time.time())}-{uuid4().hex[:6]}"
    k8s = KubernetesService()
    try:
        k8s.create_database_restore_job(
            job_name,
            rec.pull_token,
            body.staging_id,
            api_internal_base=api_base,
        )
    except ApiException as e:
        logger.error("create restore job: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="database",
        action_type="database_restore_job_created",
        user_id=str(current_user.id),
        metadata={"job_name": job_name, "staging_id": body.staging_id},
    )

    return {"status": "success", "job_name": job_name}


@router.get("/database/maintenance/restore/job/{job_name}")
async def maintenance_restore_job_status(
    job_name: str,
    current_user: UserResponse = Depends(require_superuser),
):
    k8s = KubernetesService()
    ns = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
    staging_id: Optional[str] = None
    try:
        job = k8s.batch_v1.read_namespaced_job(name=job_name, namespace=ns)
        staging_id = (job.metadata.annotations or {}).get("reconhawx.io/db-restore-staging-id")
    except ApiException as e:
        if e.status != 404:
            logger.error("read job: %s", e)
            raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    st = k8s.read_namespaced_job_status(job_name)
    if not st.get("found"):
        raise HTTPException(status_code=404, detail="Job not found")

    if staging_id and st.get("phase") in ("succeeded", "failed"):
        restore_staging.finalize_staging_id(staging_id)

    return {"status": "success", "job_name": job_name, **st}
