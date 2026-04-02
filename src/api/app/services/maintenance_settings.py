"""DB-backed maintenance mode (system_settings) with TTL cache; env is break-glass override."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

from repository.admin_repo import AdminRepository

logger = logging.getLogger(__name__)

SYSTEM_SETTINGS_KEY = "maintenance_mode"
DEFAULT_DETAIL_MESSAGE = "Service is under maintenance."

_TTL_SEC = float(os.getenv("MAINTENANCE_SETTINGS_CACHE_TTL_SEC", "3"))

_cache_generation = 0
# (generation_when_fetched, monotonic_at_fetch, db_enabled, db_message_raw)
_cache_entry: Optional[Tuple[int, float, bool, str]] = None


def bump_cache_generation() -> None:
    global _cache_generation
    _cache_generation += 1


def env_maintenance_active() -> bool:
    return os.getenv("MAINTENANCE_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def env_message_override() -> str:
    return os.getenv("MAINTENANCE_MESSAGE", "").strip()


def _parse_db_value(raw: Any) -> Tuple[bool, str]:
    if not isinstance(raw, dict):
        return False, ""
    enabled = bool(raw.get("enabled", False))
    msg = raw.get("message")
    m = str(msg).strip() if msg is not None else ""
    return enabled, m


async def _fetch_db() -> Tuple[bool, str]:
    try:
        repo = AdminRepository()
        row = await repo.get_system_setting(SYSTEM_SETTINGS_KEY)
        if not row:
            return False, ""
        val = row.get("value")
        return _parse_db_value(val)
    except Exception as e:
        logger.warning("maintenance_mode read from DB failed (fall back to env/off): %s", e)
        return False, ""


async def get_db_maintenance_cached() -> Tuple[bool, str]:
    """Returns (db_enabled, db_message) using a short TTL cache."""
    global _cache_entry
    now = time.monotonic()
    gen = _cache_generation

    if _cache_entry is not None:
        cached_gen, cached_at, db_en, db_msg = _cache_entry
        if cached_gen == gen and (now - cached_at) < _TTL_SEC:
            return db_en, db_msg

    db_en, db_msg = await _fetch_db()
    _cache_entry = (gen, now, db_en, db_msg)
    return db_en, db_msg


async def get_effective_maintenance() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Effective (enabled, user_message, meta).
    meta includes env_override_active (env forces maintenance on).
    """
    env_on = env_maintenance_active()
    env_msg = env_message_override()

    db_on, db_msg = await get_db_maintenance_cached()

    enabled = env_on or db_on
    if env_msg:
        message = env_msg
    elif db_msg:
        message = db_msg
    else:
        message = DEFAULT_DETAIL_MESSAGE

    meta = {
        "env_override_active": env_on,
        "db_enabled": db_on,
    }
    return enabled, message, meta

