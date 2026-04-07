"""
Workflow runner/worker images and pull policy in system_settings (key workflow_kubernetes).

Built-in defaults use APP_VERSION for image tags (aligned with API deployment).

Stored shape (per service):
- Structured: runner_repository, runner_tag_source (app_version | custom), runner_custom_tag
- Legacy: runner_image (full reference); used when no structured keys and value set
- Digest or other references that cannot split as repo:tag remain legacy (runner_image only).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

WORKFLOW_KUBERNETES_KEY = "workflow_kubernetes"

_VALID_PULL_POLICIES = frozenset({"Always", "Never", "IfNotPresent"})

TAG_SOURCE_APP = "app_version"
TAG_SOURCE_CUSTOM = "custom"
_VALID_TAG_SOURCES = frozenset({TAG_SOURCE_APP, TAG_SOURCE_CUSTOM})

DEFAULT_RUNNER_REPOSITORY = "ghcr.io/reconhawx/reconhawx/runner"
DEFAULT_WORKER_REPOSITORY = "ghcr.io/reconhawx/reconhawx/worker"

_RUNNER_STRUCTURED_KEYS = frozenset({"runner_repository", "runner_tag_source", "runner_custom_tag"})
_WORKER_STRUCTURED_KEYS = frozenset({"worker_repository", "worker_tag_source", "worker_custom_tag"})


def _app_version_tag() -> str:
    return (os.getenv("APP_VERSION") or "dev").strip() or "dev"


def get_workflow_kubernetes_app_version() -> str:
    """APP_VERSION used for default image tags (same as API deployment)."""
    return _app_version_tag()


def split_repo_and_tag(image_ref: str) -> Optional[Tuple[str, str]]:
    """
    Split image ref into (repository, tag) using the last ':' when no '@' digest.
    Returns None if a digest is present or there is no tag segment.
    """
    s = (image_ref or "").strip()
    if not s or "@" in s:
        return None
    if ":" not in s:
        return None
    repo, tag = s.rsplit(":", 1)
    if not repo or not tag:
        return None
    return repo, tag


def _normalize_tag_source(raw: Any) -> str:
    s = str(raw or TAG_SOURCE_APP).strip()
    return s if s in _VALID_TAG_SOURCES else TAG_SOURCE_APP


def _has_structured_runner(db: Dict[str, Any]) -> bool:
    return any(k in db for k in _RUNNER_STRUCTURED_KEYS)


def _has_structured_worker(db: Dict[str, Any]) -> bool:
    return any(k in db for k in _WORKER_STRUCTURED_KEYS)


def _effective_runner_image(db: Dict[str, Any]) -> str:
    tag = _app_version_tag()
    if _has_structured_runner(db):
        repo = str(db.get("runner_repository") or "").strip() or DEFAULT_RUNNER_REPOSITORY
        mode = _normalize_tag_source(db.get("runner_tag_source"))
        if mode == TAG_SOURCE_CUSTOM:
            ct = str(db.get("runner_custom_tag") or "").strip()
            if not ct:
                return f"{repo}:{tag}"
            return f"{repo}:{ct}"
        return f"{repo}:{tag}"
    legacy = db.get("runner_image")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return f"{DEFAULT_RUNNER_REPOSITORY}:{tag}"


def _effective_worker_image(db: Dict[str, Any]) -> str:
    tag = _app_version_tag()
    if _has_structured_worker(db):
        repo = str(db.get("worker_repository") or "").strip() or DEFAULT_WORKER_REPOSITORY
        mode = _normalize_tag_source(db.get("worker_tag_source"))
        if mode == TAG_SOURCE_CUSTOM:
            ct = str(db.get("worker_custom_tag") or "").strip()
            if not ct:
                return f"{repo}:{tag}"
            return f"{repo}:{ct}"
        return f"{repo}:{tag}"
    legacy = db.get("worker_image")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return f"{DEFAULT_WORKER_REPOSITORY}:{tag}"


def builtin_workflow_kubernetes_defaults() -> Dict[str, str]:
    tag = _app_version_tag()
    return {
        "runner_image": f"{DEFAULT_RUNNER_REPOSITORY}:{tag}",
        "worker_image": f"{DEFAULT_WORKER_REPOSITORY}:{tag}",
        "image_pull_policy": "IfNotPresent",
    }


def merge_workflow_kubernetes(
    db_value: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Compute effective runner_image / worker_image / image_pull_policy from DB + builtins."""
    out = builtin_workflow_kubernetes_defaults()
    db: Dict[str, Any] = dict(db_value) if isinstance(db_value, dict) else {}
    out["runner_image"] = _effective_runner_image(db)
    out["worker_image"] = _effective_worker_image(db)
    ipp = db.get("image_pull_policy")
    if ipp is not None:
        s = str(ipp).strip()
        if s in _VALID_PULL_POLICIES:
            out["image_pull_policy"] = s
        else:
            logger.warning("Invalid workflow_kubernetes image_pull_policy: %r", ipp)
    return out


def runner_editor_from_stored(db: Dict[str, Any]) -> Dict[str, Any]:
    if _has_structured_runner(db):
        return {
            "kind": "structured",
            "repository": str(db.get("runner_repository") or "").strip() or DEFAULT_RUNNER_REPOSITORY,
            "tag_source": _normalize_tag_source(db.get("runner_tag_source")),
            "custom_tag": str(db.get("runner_custom_tag") or "").strip(),
        }
    legacy = (db.get("runner_image") or "").strip() if isinstance(db.get("runner_image"), str) else ""
    if not legacy:
        return {
            "kind": "structured",
            "repository": DEFAULT_RUNNER_REPOSITORY,
            "tag_source": TAG_SOURCE_APP,
            "custom_tag": "",
        }
    if "@" in legacy:
        return {"kind": "legacy", "full_image": legacy}
    parsed = split_repo_and_tag(legacy)
    if parsed:
        repo, t = parsed
        return {
            "kind": "structured",
            "repository": repo,
            "tag_source": TAG_SOURCE_CUSTOM,
            "custom_tag": t,
        }
    return {"kind": "legacy", "full_image": legacy}


def worker_editor_from_stored(db: Dict[str, Any]) -> Dict[str, Any]:
    if _has_structured_worker(db):
        return {
            "kind": "structured",
            "repository": str(db.get("worker_repository") or "").strip() or DEFAULT_WORKER_REPOSITORY,
            "tag_source": _normalize_tag_source(db.get("worker_tag_source")),
            "custom_tag": str(db.get("worker_custom_tag") or "").strip(),
        }
    legacy = (db.get("worker_image") or "").strip() if isinstance(db.get("worker_image"), str) else ""
    if not legacy:
        return {
            "kind": "structured",
            "repository": DEFAULT_WORKER_REPOSITORY,
            "tag_source": TAG_SOURCE_APP,
            "custom_tag": "",
        }
    if "@" in legacy:
        return {"kind": "legacy", "full_image": legacy}
    parsed = split_repo_and_tag(legacy)
    if parsed:
        repo, t = parsed
        return {
            "kind": "structured",
            "repository": repo,
            "tag_source": TAG_SOURCE_CUSTOM,
            "custom_tag": t,
        }
    return {"kind": "legacy", "full_image": legacy}


async def get_workflow_kubernetes_admin_bundle() -> Dict[str, Any]:
    """Merged settings plus editor-friendly runner/worker blocks and APP_VERSION."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_KUBERNETES_KEY)
    raw = (row or {}).get("value") if isinstance(row, dict) else None
    db = dict(raw) if isinstance(raw, dict) else {}
    return {
        "app_version": get_workflow_kubernetes_app_version(),
        "settings": merge_workflow_kubernetes(db),
        "runner": runner_editor_from_stored(db),
        "worker": worker_editor_from_stored(db),
    }


async def workflow_kubernetes_admin_success_payload() -> Dict[str, Any]:
    """Response body for GET/PUT/DELETE admin workflow-kubernetes endpoints."""
    bundle = await get_workflow_kubernetes_admin_bundle()
    return {
        "status": "success",
        "app_version": bundle["app_version"],
        "settings": bundle["settings"],
        "runner": bundle["runner"],
        "worker": bundle["worker"],
    }


def _fetch_raw_stored_sync() -> Optional[Dict[str, Any]]:
    from db import SessionLocal
    from models.postgres import SystemSetting

    db = SessionLocal()
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == WORKFLOW_KUBERNETES_KEY).first()
        if not row or not isinstance(row.value, dict):
            return None
        return dict(row.value)
    finally:
        db.close()


def get_workflow_kubernetes_merged_sync() -> Dict[str, str]:
    raw = _fetch_raw_stored_sync()
    return merge_workflow_kubernetes(raw)


async def get_workflow_kubernetes_merged() -> Dict[str, str]:
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_KUBERNETES_KEY)
    raw = (row or {}).get("value") if isinstance(row, dict) else None
    return merge_workflow_kubernetes(raw if isinstance(raw, dict) else None)


def _strip_runner_structured(stored: Dict[str, Any]) -> None:
    for k in _RUNNER_STRUCTURED_KEYS:
        stored.pop(k, None)


def _strip_worker_structured(stored: Dict[str, Any]) -> None:
    for k in _WORKER_STRUCTURED_KEYS:
        stored.pop(k, None)


def _strip_runner_legacy(stored: Dict[str, Any]) -> None:
    stored.pop("runner_image", None)


def _strip_worker_legacy(stored: Dict[str, Any]) -> None:
    stored.pop("worker_image", None)


def validate_workflow_kubernetes_updates(
    updates: Dict[str, Any],
    current: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Validate PUT payload. Returns (normalized dict of updates to apply, error message).
    None values remove keys from stored JSON.
    """
    cur: Dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    out: Dict[str, Any] = {}

    # --- image_pull_policy ---
    if "image_pull_policy" in updates:
        v = updates["image_pull_policy"]
        if v is None:
            out["image_pull_policy"] = None
        else:
            s = str(v).strip()
            if s not in _VALID_PULL_POLICIES:
                return {}, f"image_pull_policy must be one of: {', '.join(sorted(_VALID_PULL_POLICIES))}"
            out["image_pull_policy"] = s

    # Detect intent: structured vs legacy per service
    structured_runner_keys = [k for k in _RUNNER_STRUCTURED_KEYS if k in updates]
    legacy_runner_in_updates = "runner_image" in updates
    structured_worker_keys = [k for k in _WORKER_STRUCTURED_KEYS if k in updates]
    legacy_worker_in_updates = "worker_image" in updates

    if structured_runner_keys and legacy_runner_in_updates:
        return {}, "Cannot set runner_image together with structured runner fields in one request"

    if structured_worker_keys and legacy_worker_in_updates:
        return {}, "Cannot set worker_image together with structured worker fields in one request"

    # --- runner structured ---
    if structured_runner_keys:
        if "runner_repository" in updates:
            rv = updates["runner_repository"]
            if rv is None:
                out["runner_repository"] = None
            else:
                rs = str(rv).strip()
                if not rs:
                    return {}, "runner_repository must be non-empty when provided"
                out["runner_repository"] = rs
        if "runner_tag_source" in updates:
            tv = updates["runner_tag_source"]
            if tv is None:
                out["runner_tag_source"] = None
            else:
                ts = str(tv).strip()
                if ts not in _VALID_TAG_SOURCES:
                    return {}, f"runner_tag_source must be one of: {', '.join(sorted(_VALID_TAG_SOURCES))}"
                out["runner_tag_source"] = ts
        if "runner_custom_tag" in updates:
            cv = updates["runner_custom_tag"]
            if cv is None:
                out["runner_custom_tag"] = None
            else:
                out["runner_custom_tag"] = str(cv).strip()

    if legacy_runner_in_updates:
        v = updates["runner_image"]
        if v is None:
            out["runner_image"] = None
        else:
            s = str(v).strip()
            if not s:
                return {}, "runner_image must be a non-empty string when provided"
            out["runner_image"] = s

    # --- worker structured ---
    if structured_worker_keys:
        if "worker_repository" in updates:
            rv = updates["worker_repository"]
            if rv is None:
                out["worker_repository"] = None
            else:
                rs = str(rv).strip()
                if not rs:
                    return {}, "worker_repository must be non-empty when provided"
                out["worker_repository"] = rs
        if "worker_tag_source" in updates:
            tv = updates["worker_tag_source"]
            if tv is None:
                out["worker_tag_source"] = None
            else:
                ts = str(tv).strip()
                if ts not in _VALID_TAG_SOURCES:
                    return {}, f"worker_tag_source must be one of: {', '.join(sorted(_VALID_TAG_SOURCES))}"
                out["worker_tag_source"] = ts
        if "worker_custom_tag" in updates:
            cv = updates["worker_custom_tag"]
            if cv is None:
                out["worker_custom_tag"] = None
            else:
                out["worker_custom_tag"] = str(cv).strip()

    if legacy_worker_in_updates:
        v = updates["worker_image"]
        if v is None:
            out["worker_image"] = None
        else:
            s = str(v).strip()
            if not s:
                return {}, "worker_image must be a non-empty string when provided"
            out["worker_image"] = s

    if not out:
        return {}, None

    preview = _apply_updates_to_stored(cur, out)
    if _has_structured_runner(preview):
        if _normalize_tag_source(preview.get("runner_tag_source")) == TAG_SOURCE_CUSTOM:
            if not str(preview.get("runner_custom_tag") or "").strip():
                return {}, "runner_custom_tag must be non-empty when runner_tag_source is custom"
    if _has_structured_worker(preview):
        if _normalize_tag_source(preview.get("worker_tag_source")) == TAG_SOURCE_CUSTOM:
            if not str(preview.get("worker_custom_tag") or "").strip():
                return {}, "worker_custom_tag must be non-empty when worker_tag_source is custom"

    return out, None


def _apply_updates_to_stored(
    current: Dict[str, Any],
    normalized: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge normalized updates and reconcile legacy vs structured keys."""
    merged = {**current}
    for k, v in normalized.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v

    # After apply: strip conflicts
    if any(k in normalized for k in _RUNNER_STRUCTURED_KEYS):
        _strip_runner_legacy(merged)
    if any(k in normalized for k in _WORKER_STRUCTURED_KEYS):
        _strip_worker_legacy(merged)
    if "runner_image" in normalized and normalized["runner_image"] is not None:
        _strip_runner_structured(merged)
    elif "runner_image" in normalized and normalized["runner_image"] is None:
        _strip_runner_legacy(merged)

    if "worker_image" in normalized and normalized["worker_image"] is not None:
        _strip_worker_structured(merged)
    elif "worker_image" in normalized and normalized["worker_image"] is None:
        _strip_worker_legacy(merged)

    return merged


async def update_workflow_kubernetes_partial(updates: Dict[str, Any]) -> Dict[str, str]:
    """Merge validated updates into stored JSON (None removes key). Return effective merged config."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_KUBERNETES_KEY)
    cur = (row or {}).get("value") if isinstance(row, dict) else None
    if not isinstance(cur, dict):
        cur = {}

    normalized, err = validate_workflow_kubernetes_updates(updates, cur)
    if err:
        raise ValueError(err)
    if not normalized:
        raise ValueError("No fields to update")

    merged_stored = _apply_updates_to_stored(cur, normalized)
    await admin_repo.set_system_setting(WORKFLOW_KUBERNETES_KEY, merged_stored)
    return merge_workflow_kubernetes(merged_stored)

