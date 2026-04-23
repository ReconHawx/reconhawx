"""Superuser: in-cluster ReconHawx upgrade (Kubernetes Job + status)."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

from auth.dependencies import require_superuser
from models.user_postgres import UserResponse
from repository.action_log_repo import ActionLogRepository
from services import upgrade_staging
from services.kubernetes import KubernetesService, UPGRADE_JOB_NAME_PREFIX

logger = logging.getLogger(__name__)

router = APIRouter()

_VERSION_RE = re.compile(r"^(latest|\d+\.\d+\.\d+)$")

_github_latest_cache: Dict[str, Any] = {"at": 0.0, "tag": None, "reachable": False}


def _github_repo() -> str:
    return (os.getenv("RECONHAWX_GITHUB_REPO") or "ReconHawx/reconhawx").strip()


def _upgrader_image() -> str:
    return (os.getenv("UPGRADER_IMAGE") or "ghcr.io/reconhawx/reconhawx/upgrader:latest").strip()


def _max_upgrade_staging_bytes() -> int:
    return int(os.getenv("UPGRADE_STAGING_MAX_BYTES", str(200 * 1024 * 1024)))


async def _fetch_github_latest_tag() -> Tuple[Optional[str], bool]:
    """Returns (semver without leading v, github_reachable)."""
    now = time.time()
    if now - float(_github_latest_cache.get("at") or 0) < 60.0 and _github_latest_cache.get("tag") is not None:
        return _github_latest_cache.get("tag"), bool(_github_latest_cache.get("reachable"))

    repo = _github_repo()
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "reconhawx-api-upgrade-status",
    }
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    tag: Optional[str] = None
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
            raw = (data.get("tag_name") or "").strip()
            if raw.startswith("v"):
                raw = raw[1:]
            tag = raw or None
            reachable = True
    except Exception as e:
        logger.warning("GitHub releases/latest failed: %s", e)

    _github_latest_cache["at"] = now
    _github_latest_cache["tag"] = tag
    _github_latest_cache["reachable"] = reachable
    return tag, reachable


class UpgradeJobBody(BaseModel):
    version: str = Field(..., min_length=1)
    staging_id: Optional[str] = None
    kueue_resync_quotas: bool = False
    upgrade_observability: bool = False
    confirm: str = Field(..., min_length=1)


@router.get("/system/upgrade/status")
async def upgrade_status(current_user: UserResponse = Depends(require_superuser)):
    k8s = KubernetesService()
    ns = os.getenv("KUBERNETES_NAMESPACE", "reconhawx")
    cluster_version: Optional[str] = None
    try:
        cm = k8s.v1.read_namespaced_config_map(name="reconhawx-version", namespace=ns)
        cluster_version = (cm.data or {}).get("APP_VERSION")
    except ApiException as e:
        if e.status != 404:
            logger.error("read reconhawx-version: %s", e)
            raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    bundle_version = (os.getenv("APP_VERSION") or "").strip() or None
    latest_release, github_reachable = await _fetch_github_latest_tag()

    try:
        recent = k8s.list_upgrade_jobs(limit=10)
    except ApiException as e:
        logger.error("list upgrade jobs: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    return {
        "status": "success",
        "cluster_version": cluster_version,
        "bundle_version": bundle_version,
        "latest_release": latest_release,
        "github_repo": _github_repo(),
        "github_reachable": github_reachable,
        "recent_upgrade_jobs": recent,
    }


@router.post("/system/upgrade/stage")
async def upgrade_stage(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_superuser),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a tarball file")

    base = os.getenv("UPGRADE_STAGING_DIR", "/tmp/reconhawx-upgrade-staging")
    os.makedirs(base, mode=0o700, exist_ok=True)

    max_bytes = _max_upgrade_staging_bytes()
    total = 0
    fd, path = tempfile.mkstemp(prefix="reconhawx-upgrade-", suffix=".tar.gz", dir=base)
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
                        detail=f"File exceeds maximum upgrade staging size ({max_bytes} bytes)",
                    )
                out.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        staging_id, _pull = upgrade_staging.register_file(path)
        logger.warning(
            "upgrade stage user_id=%s staging_id=%s bytes=%s",
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


@router.post("/system/upgrade/job")
async def upgrade_create_job(
    body: UpgradeJobBody,
    current_user: UserResponse = Depends(require_superuser),
):
    if body.confirm != "UPGRADE_RECONHAWX":
        raise HTTPException(
            status_code=400,
            detail='confirm must be exactly "UPGRADE_RECONHAWX"',
        )
    staging_raw = (body.staging_id or "").strip()
    if staging_raw and len(staging_raw) < 8:
        raise HTTPException(status_code=400, detail="staging_id is too short")
    ver = body.version.strip()
    if not _VERSION_RE.match(ver):
        raise HTTPException(
            status_code=400,
            detail='version must be "latest" or a semver x.y.z',
        )

    k8s = KubernetesService()
    try:
        if k8s.has_non_terminal_upgrade_job():
            raise HTTPException(
                status_code=409,
                detail="An upgrade Job is already running or pending completion.",
            )
    except ApiException as e:
        logger.error("upgrade concurrency check: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    pull_token: Optional[str] = None
    staging_id = staging_raw or None
    if staging_id:
        rec = upgrade_staging.get_staging(staging_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Unknown or expired staging_id")
        pull_token = rec.pull_token

    api_base = (
        os.getenv("API_INTERNAL_URL")
        or os.getenv("API_URL")
        or "http://api:8000"
    ).rstrip("/")

    job_name = f"{UPGRADE_JOB_NAME_PREFIX}{int(time.time())}-{uuid4().hex[:6]}"
    try:
        k8s.create_upgrade_job(
            job_name,
            upgrader_image=_upgrader_image(),
            target_version=ver,
            github_repo=_github_repo(),
            pull_token=pull_token,
            staging_id=staging_id,
            api_internal_base=api_base if pull_token else None,
            kueue_resync_quotas=body.kueue_resync_quotas,
            upgrade_observability=body.upgrade_observability,
            triggered_by_user_id=str(current_user.id),
        )
    except ApiException as e:
        logger.error("create upgrade job: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    await ActionLogRepository.log_action(
        entity_type="system",
        entity_id="upgrader",
        action_type="upgrade_job_created",
        user_id=str(current_user.id),
        metadata={
            "job_name": job_name,
            "version": ver,
            "staging_id": staging_id,
            "kueue_resync_quotas": body.kueue_resync_quotas,
        },
    )

    return {"status": "success", "job_name": job_name}


@router.get("/system/upgrade/jobs")
async def upgrade_list_jobs(
    limit: int = 20,
    current_user: UserResponse = Depends(require_superuser),
):
    k8s = KubernetesService()
    try:
        jobs = k8s.list_upgrade_jobs(limit=min(max(limit, 1), 50))
    except ApiException as e:
        logger.error("list upgrade jobs: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e
    return {"status": "success", "jobs": jobs}


@router.get("/system/upgrade/job/{job_name}")
async def upgrade_job_status(
    job_name: str,
    current_user: UserResponse = Depends(require_superuser),
):
    if not job_name.startswith(UPGRADE_JOB_NAME_PREFIX):
        raise HTTPException(status_code=400, detail="Invalid job name")

    k8s = KubernetesService()
    try:
        st = k8s.read_upgrade_job_status(job_name)
    except ApiException as e:
        logger.error("read upgrade job: %s", e)
        raise HTTPException(status_code=502, detail=f"Kubernetes: {e.reason or e}") from e

    if not st.get("found"):
        raise HTTPException(status_code=404, detail="Job not found")

    staging_id = None
    try:
        job = k8s.batch_v1.read_namespaced_job(name=job_name, namespace=os.getenv("KUBERNETES_NAMESPACE", "reconhawx"))
        staging_id = (job.metadata.annotations or {}).get("reconhawx.io/upgrade-staging-id")
    except ApiException:
        staging_id = None

    if staging_id and st.get("phase") in ("succeeded", "failed"):
        upgrade_staging.finalize_staging_id(staging_id)

    return {"status": "success", "job_name": job_name, **st}


@router.get("/system/upgrade/job/{job_name}/logs")
async def upgrade_job_logs(
    job_name: str,
    tail_lines: int = 500,
    since_seconds: Optional[int] = None,
    current_user: UserResponse = Depends(require_superuser),
):
    if not job_name.startswith(UPGRADE_JOB_NAME_PREFIX):
        raise HTTPException(status_code=400, detail="Invalid job name")

    k8s = KubernetesService()
    tl = min(max(tail_lines, 10), 5000)
    ss = since_seconds if since_seconds is None or since_seconds > 0 else None
    pod, log = k8s.tail_upgrade_job_logs(job_name, tail_lines=tl, since_seconds=ss)
    if not pod:
        raise HTTPException(status_code=404, detail="No pod for this Job yet")
    return {"status": "success", "job_name": job_name, "pod_name": pod, "log": log}
