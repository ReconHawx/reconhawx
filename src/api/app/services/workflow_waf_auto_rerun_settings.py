"""
WAF workflow settings stored in ``system_settings`` (key ``workflow_waf_auto_rerun``).

Includes auto-rerun (enabled, max_attempts, delay_seconds) and runner quarantine
(timing injected into workflow-runner pods as ``WAF_QUARANTINE_TTL``,
``WAF_SECONDARY_PROMOTE``, ``WAF_SECONDARY_WINDOW``).
``secondary_promote`` / ``secondary_window`` bound weak heavy-task WAF signals in Redis
(a sliding time window and a count threshold) before they promote to the same block
as a nuclei precheck hit (see ``waf_reputation.record_secondary_signal``).

Seeded via Alembic. Admin UI may change values; reset restores canonical defaults.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, Optional, TypedDict

logger = logging.getLogger(__name__)

WORKFLOW_WAF_AUTO_RERUN_KEY = "workflow_waf_auto_rerun"

MAX_AUTO_RERUN_ATTEMPTS_ADMIN = 50

DELAY_SECONDS_MIN = 60
DELAY_SECONDS_MAX = 86_400

QUARANTINE_TTL_MIN = 60
QUARANTINE_TTL_MAX = 86_400

SECONDARY_PROMOTE_MIN = 1
SECONDARY_PROMOTE_MAX = 100

SECONDARY_WINDOW_MIN = 60
SECONDARY_WINDOW_MAX = 86_400


class WorkflowWafAutoRerunEffective(TypedDict):
    enabled: bool
    max_attempts: int
    delay_seconds: int
    quarantine_ttl: int
    secondary_promote: int
    secondary_window: int


# Single source with migration seed JSON — keep aligned with Alembic insert.
CANONICAL_DEFAULTS: WorkflowWafAutoRerunEffective = {
    "enabled": True,
    "max_attempts": 3,
    "delay_seconds": 2100,
    "quarantine_ttl": 1800,
    "secondary_promote": 2,
    "secondary_window": 900,
}


def admin_bounds_payload() -> Dict[str, Any]:
    """Bounds for admin UI and API validation."""
    return {
        "max_attempts": {"min": 1, "max": MAX_AUTO_RERUN_ATTEMPTS_ADMIN},
        "delay_seconds": {"min": DELAY_SECONDS_MIN, "max": DELAY_SECONDS_MAX},
        "quarantine_ttl": {"min": QUARANTINE_TTL_MIN, "max": QUARANTINE_TTL_MAX},
        "secondary_promote": {"min": SECONDARY_PROMOTE_MIN, "max": SECONDARY_PROMOTE_MAX},
        "secondary_window": {"min": SECONDARY_WINDOW_MIN, "max": SECONDARY_WINDOW_MAX},
    }


def _clamp_int_in_range(n: Any, lo: int, hi: int) -> Optional[int]:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return None
    if v < lo or v > hi:
        return None
    return v


def _clamp_max_attempts(n: Any) -> Optional[int]:
    return _clamp_int_in_range(n, 1, MAX_AUTO_RERUN_ATTEMPTS_ADMIN)


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
    d = _clamp_int_in_range(raw.get("delay_seconds"), DELAY_SECONDS_MIN, DELAY_SECONDS_MAX)
    if d is not None:
        out["delay_seconds"] = d
    q = _clamp_int_in_range(raw.get("quarantine_ttl"), QUARANTINE_TTL_MIN, QUARANTINE_TTL_MAX)
    if q is not None:
        out["quarantine_ttl"] = q
    sp = _clamp_int_in_range(
        raw.get("secondary_promote"), SECONDARY_PROMOTE_MIN, SECONDARY_PROMOTE_MAX
    )
    if sp is not None:
        out["secondary_promote"] = sp
    sw = _clamp_int_in_range(
        raw.get("secondary_window"), SECONDARY_WINDOW_MIN, SECONDARY_WINDOW_MAX
    )
    if sw is not None:
        out["secondary_window"] = sw
    return out


async def get_workflow_waf_auto_rerun_effective() -> WorkflowWafAutoRerunEffective:
    """Effective policy for WAF auto-rerun and runner quarantine (DB-backed where seeded)."""
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
        "bounds": admin_bounds_payload(),
    }


def _any_update_kw(
    *,
    enabled: Optional[bool],
    max_attempts: Optional[int],
    delay_seconds: Optional[int],
    quarantine_ttl: Optional[int],
    secondary_promote: Optional[int],
    secondary_window: Optional[int],
) -> bool:
    return any(
        x is not None
        for x in (
            enabled,
            max_attempts,
            delay_seconds,
            quarantine_ttl,
            secondary_promote,
            secondary_window,
        )
    )


async def update_workflow_waf_auto_rerun_partial(
    *,
    enabled: Optional[bool] = None,
    max_attempts: Optional[int] = None,
    delay_seconds: Optional[int] = None,
    quarantine_ttl: Optional[int] = None,
    secondary_promote: Optional[int] = None,
    secondary_window: Optional[int] = None,
) -> WorkflowWafAutoRerunEffective:
    """Upsert merged settings from partial admin update."""
    if not _any_update_kw(
        enabled=enabled,
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
        quarantine_ttl=quarantine_ttl,
        secondary_promote=secondary_promote,
        secondary_window=secondary_window,
    ):
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
    if delay_seconds is not None:
        clipped = _clamp_int_in_range(delay_seconds, DELAY_SECONDS_MIN, DELAY_SECONDS_MAX)
        if clipped is None:
            raise ValueError(
                f"delay_seconds must be an integer between {DELAY_SECONDS_MIN} and {DELAY_SECONDS_MAX}"
            )
        merged["delay_seconds"] = clipped
    if quarantine_ttl is not None:
        clipped = _clamp_int_in_range(quarantine_ttl, QUARANTINE_TTL_MIN, QUARANTINE_TTL_MAX)
        if clipped is None:
            raise ValueError(
                f"quarantine_ttl must be an integer between {QUARANTINE_TTL_MIN} and {QUARANTINE_TTL_MAX}"
            )
        merged["quarantine_ttl"] = clipped
    if secondary_promote is not None:
        clipped = _clamp_int_in_range(
            secondary_promote, SECONDARY_PROMOTE_MIN, SECONDARY_PROMOTE_MAX
        )
        if clipped is None:
            raise ValueError(
                f"secondary_promote must be an integer between "
                f"{SECONDARY_PROMOTE_MIN} and {SECONDARY_PROMOTE_MAX}"
            )
        merged["secondary_promote"] = clipped
    if secondary_window is not None:
        clipped = _clamp_int_in_range(
            secondary_window, SECONDARY_WINDOW_MIN, SECONDARY_WINDOW_MAX
        )
        if clipped is None:
            raise ValueError(
                f"secondary_window must be an integer between "
                f"{SECONDARY_WINDOW_MIN} and {SECONDARY_WINDOW_MAX}"
            )
        merged["secondary_window"] = clipped

    await admin_repo.set_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY, dict(merged))
    return merged


async def reset_workflow_waf_auto_rerun_to_defaults() -> WorkflowWafAutoRerunEffective:
    """Upsert canonical defaults."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    val = dict(CANONICAL_DEFAULTS)
    await admin_repo.set_system_setting(WORKFLOW_WAF_AUTO_RERUN_KEY, val)
    return deepcopy(dict(CANONICAL_DEFAULTS))
