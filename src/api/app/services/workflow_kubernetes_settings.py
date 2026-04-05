"""
Workflow runner/worker images and pull policy in system_settings (key workflow_kubernetes).

Built-in defaults use APP_VERSION for image tags (aligned with API deployment).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

WORKFLOW_KUBERNETES_KEY = "workflow_kubernetes"

_VALID_PULL_POLICIES = frozenset({"Always", "Never", "IfNotPresent"})

_SETTING_KEYS = ("runner_image", "worker_image", "image_pull_policy")


def _app_version_tag() -> str:
    return (os.getenv("APP_VERSION") or "dev").strip() or "dev"


def builtin_workflow_kubernetes_defaults() -> Dict[str, str]:
    tag = _app_version_tag()
    return {
        "runner_image": f"ghcr.io/reconhawx/reconhawx/runner:{tag}",
        "worker_image": f"ghcr.io/reconhawx/reconhawx/worker:{tag}",
        "image_pull_policy": "IfNotPresent",
    }


def merge_workflow_kubernetes(
    db_value: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Apply optional DB overrides on top of version-based built-in defaults."""
    out = builtin_workflow_kubernetes_defaults()
    if not isinstance(db_value, dict):
        return out
    for k in _SETTING_KEYS:
        if k not in db_value or db_value[k] is None:
            continue
        raw = db_value[k]
        if k == "image_pull_policy":
            s = str(raw).strip()
            if s in _VALID_PULL_POLICIES:
                out[k] = s
            else:
                logger.warning("Invalid workflow_kubernetes image_pull_policy: %r", raw)
            continue
        s = str(raw).strip()
        if s:
            out[k] = s
        else:
            logger.warning("Ignoring empty workflow_kubernetes value for %s", k)
    return out


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


def validate_workflow_kubernetes_updates(
    updates: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Validate PUT payload fields. Returns (normalized dict of non-None updates, error message).
    """
    out: Dict[str, Any] = {}
    for k in _SETTING_KEYS:
        if k not in updates:
            continue
        v = updates[k]
        if v is None:
            out[k] = None
            continue
        if k == "image_pull_policy":
            s = str(v).strip()
            if s not in _VALID_PULL_POLICIES:
                return {}, f"image_pull_policy must be one of: {', '.join(sorted(_VALID_PULL_POLICIES))}"
            out[k] = s
            continue
        s = str(v).strip()
        if not s:
            return {}, f"{k} must be a non-empty string"
        out[k] = s
    return out, None


async def update_workflow_kubernetes_partial(updates: Dict[str, Any]) -> Dict[str, str]:
    """Merge validated updates into stored JSON (None removes override). Return effective merged config."""
    from repository.admin_repo import AdminRepository

    normalized, err = validate_workflow_kubernetes_updates(updates)
    if err:
        raise ValueError(err)
    if not normalized:
        raise ValueError("No fields to update")

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_KUBERNETES_KEY)
    current = (row or {}).get("value") if isinstance(row, dict) else None
    if not isinstance(current, dict):
        current = {}
    merged_stored = {**current}
    for k, v in normalized.items():
        if v is None:
            merged_stored.pop(k, None)
        else:
            merged_stored[k] = v
    await admin_repo.set_system_setting(WORKFLOW_KUBERNETES_KEY, merged_stored)
    return merge_workflow_kubernetes(merged_stored)
