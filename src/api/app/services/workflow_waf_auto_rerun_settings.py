"""
WAF auto-rerun toggles stored in ``system_settings`` (key ``workflow_waf_auto_rerun``).

Seeded via Alembic to ``enabled: true``, ``max_attempts: 3``. Admin UI may change values;
Reset restores canonical defaults.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, Optional, TypedDict

logger = logging.getLogger(__name__)

WORKFLOW_WAF_AUTO_RERUN_KEY = "workflow_waf_auto_rerun"

MAX_AUTO_RERUN_ATTEMPTS_ADMIN = 50


class WorkflowWafAutoRerunEffective(TypedDict):
    enabled: bool
    max_attempts: int


# Single source with migration seed JSON — keep aligned with Alembic insert.
CANONICAL_DEFAULTS: WorkflowWafAutoRerunEffective = {
    "enabled": True,
    "max_attempts": 3,
}


def _clamp_max_attempts(n: Any) -> Optional[int]:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return None
    if v < 1 or v > MAX_AUTO_RERUN_ATTEMPTS_ADMIN:
        return None
    return v


def merge_stored_value(raw: Any) -> WorkflowWafAutoRerunEffective:
    """Interpret DB JSON blob over canonical defaults; tolerate partial/invalid."""
    out: WorkflowWafAutoRerunEffective = deepcopy(dict(CANONICAL_DEFAULTS))
    if not isinstance(raw, dict):
        return out
    if isinstance(raw.get("enabled"), bool):
        out["enabled"] = raw["enabled"]
    clipped = _clamp_max_attempts(raw.get("max_attempts"))
    if clipped is not None:
        out["max_attempts"] = clipped
    return out


async def get_workflow_waf_auto_rerun_effective() -> WorkflowWafAutoRerunEffective:
    """Effective policy for scheduling WAF reruns (DB-backed where seeded)."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY)
    if not row:
        logger.warning(
            "workflow_waf_auto_rerun: no system_settings row for %s — using canonical defaults",
            WORKFLOW_WAF_AUTO_RERUN_KEY,
        )
        return deepcopy(dict(CANONICAL_DEFAULTS))
    merged = merge_stored_value(row.get("value"))
    return merged


async def get_admin_payload() -> Dict[str, Any]:
    """Response shape for GET /admin/workflow-waf-auto-rerun-settings."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY)
    stored_display: Dict[str, Any] = {}
    if isinstance(row, dict):
        rv = row.get("value")
        if isinstance(rv, dict):
            stored_display = rv

    merged = merge_stored_value(stored_display)
    return {
        "settings": merged,
        "stored": stored_display if row is not None else {},
        "canonical_defaults": dict(CANONICAL_DEFAULTS),
        "max_attempts_cap": MAX_AUTO_RERUN_ATTEMPTS_ADMIN,
    }


async def update_workflow_waf_auto_rerun_partial(
    *,
    enabled: Optional[bool] = None,
    max_attempts: Optional[int] = None,
) -> WorkflowWafAutoRerunEffective:
    """Upsert merged settings from partial admin update."""
    if enabled is None and max_attempts is None:
        raise ValueError("No fields to update")

    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY)
    stored_display: Dict[str, Any] = {}
    if isinstance(row, dict):
        rv = row.get("value")
        if isinstance(rv, dict):
            stored_display = rv
    merged = merge_stored_value(stored_display)

    if enabled is not None:
        merged["enabled"] = bool(enabled)
    if max_attempts is not None:
        clipped = _clamp_max_attempts(max_attempts)
        if clipped is None:
            raise ValueError(
                f"max_attempts must be an integer between 1 and {MAX_AUTO_RERUN_ATTEMPTS_ADMIN}"
            )
        merged["max_attempts"] = clipped

    await admin_repo.set_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY, dict(merged))
    return merged


async def reset_workflow_waf_auto_rerun_to_defaults() -> WorkflowWafAutoRerunEffective:
    """Upsert canonical defaults."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    val = dict(CANONICAL_DEFAULTS)
    await admin_repo.set_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY, val)
    return deepcopy(dict(CANONICAL_DEFAULTS))
