"""
CT monitor global runtime settings stored in system_settings (key ct_monitor_runtime).

Merged with the same defaults as src/ct-monitor/app/config.py CTMonitorConfig env fallbacks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CT_MONITOR_RUNTIME_KEY = "ct_monitor_runtime"

# Defaults aligned with ct-monitor CTMonitorConfig (same literals as env fallbacks there)
_DEFAULTS: Dict[str, Any] = {
    "domain_refresh_interval": 300,
    "stats_interval": 60,
    "ct_poll_interval": 10,
    "ct_batch_size": 100,
    "ct_max_entries_per_poll": 1000,
    "ct_start_offset": 0,
}


def default_ct_monitor_runtime() -> Dict[str, Any]:
    return dict(_DEFAULTS)


def merge_ct_monitor_runtime(db_value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge DB JSONB into defaults; coerce types; ignore unknown keys."""
    out = default_ct_monitor_runtime()
    if not isinstance(db_value, dict):
        return out
    for k in list(_DEFAULTS.keys()):
        if k not in db_value or db_value[k] is None:
            continue
        try:
            if k == "ct_start_offset":
                out[k] = int(db_value[k])
            else:
                out[k] = int(db_value[k])
        except (TypeError, ValueError):
            logger.warning("Invalid ct_monitor_runtime value for %s: %r", k, db_value.get(k))
    return out


async def get_ct_monitor_runtime_merged() -> Dict[str, Any]:
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(CT_MONITOR_RUNTIME_KEY)
    raw = (row or {}).get("value") if isinstance(row, dict) else None
    return merge_ct_monitor_runtime(raw if isinstance(raw, dict) else None)


async def update_ct_monitor_runtime_partial(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validated updates into stored setting and return merged effective config."""
    from repository.admin_repo import AdminRepository

    admin_repo = AdminRepository()
    row = await admin_repo.get_system_setting(CT_MONITOR_RUNTIME_KEY)
    current = (row or {}).get("value") if isinstance(row, dict) else None
    if not isinstance(current, dict):
        current = {}
    merged_stored = {**current}
    for k, v in updates.items():
        if k in _DEFAULTS and v is not None:
            merged_stored[k] = int(v)
    await admin_repo.set_system_setting(CT_MONITOR_RUNTIME_KEY, merged_stored)
    return merge_ct_monitor_runtime(merged_stored)
