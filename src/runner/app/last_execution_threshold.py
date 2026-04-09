"""
Parse last_execution_threshold for recon tasks (keep in sync with src/api/app/last_execution_threshold.py).

Plain numbers mean hours. Suffixes: h, d (days), w (weeks). No months/years.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LAST_EXEC_THRESHOLD_RE = re.compile(
    r"^\s*(\d+)\s*(h|d|w)?\s*$",
    re.IGNORECASE,
)


def last_execution_threshold_to_hours(value: Any, *, default_hours: int = 24) -> int:
    """
    Convert a threshold value to positive integer hours, or return default if invalid/missing.
    """
    if value is None:
        return default_hours
    if isinstance(value, bool):
        logger.warning("Invalid last_execution_threshold type bool; using default %sh", default_hours)
        return default_hours

    if isinstance(value, (int, float)):
        if isinstance(value, float) and int(value) != value:
            logger.warning("Invalid fractional last_execution_threshold %r; using default %sh", value, default_hours)
            return default_hours
        hours = int(value)
        if hours < 1:
            logger.warning("Invalid last_execution_threshold %r; using default %sh", value, default_hours)
            return default_hours
        return hours

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default_hours
        m = _LAST_EXEC_THRESHOLD_RE.match(s)
        if not m:
            logger.warning(
                "Invalid last_execution_threshold %r (expected e.g. 24, 1d, 2w); using default %sh",
                value,
                default_hours,
            )
            return default_hours
        n = int(m.group(1))
        if n < 1:
            logger.warning("Invalid last_execution_threshold %r; using default %sh", value, default_hours)
            return default_hours
        suffix = (m.group(2) or "h").lower()
        if suffix == "h":
            return n
        if suffix == "d":
            return n * 24
        if suffix == "w":
            return n * 24 * 7
        return default_hours

    logger.warning(
        "Unsupported last_execution_threshold type %s; using default %sh",
        type(value).__name__,
        default_hours,
    )
    return default_hours


def try_last_execution_threshold_to_hours(value: Any) -> Optional[int]:
    """If value is a valid threshold (per same rules as the API), return hours; otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and int(value) != value:
            return None
        hours = int(value)
        return hours if hours >= 1 else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = _LAST_EXEC_THRESHOLD_RE.match(s)
        if not m:
            return None
        n = int(m.group(1))
        if n < 1:
            return None
        suffix = (m.group(2) or "h").lower()
        if suffix == "h":
            return n
        if suffix == "d":
            return n * 24
        if suffix == "w":
            return n * 24 * 7
        return None
    return None
