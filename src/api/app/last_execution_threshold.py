"""
Parse and normalize last_execution_threshold for recon tasks.

Plain numbers mean hours (default). Optional suffixes: h, d (days), w (weeks).
No months/years. Values are resolved to whole hours for scheduling comparisons.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Union

_LAST_EXEC_THRESHOLD_RE = re.compile(
    r"^\s*(\d+)\s*(h|d|w)?\s*$",
    re.IGNORECASE,
)


class LastExecutionThresholdError(ValueError):
    """Invalid last_execution_threshold value."""


def last_execution_threshold_to_hours(value: Any) -> int:
    """
    Convert a stored threshold to positive integer hours.

    Accepts int (hours), or string: digits, optional suffix h/d/w (case-insensitive).
    """
    if value is None:
        raise LastExecutionThresholdError("last_execution_threshold is required")
    if isinstance(value, bool):
        raise LastExecutionThresholdError("invalid type")

    if isinstance(value, (int, float)):
        if isinstance(value, float) and int(value) != value:
            raise LastExecutionThresholdError("fractional hours are not supported")
        hours = int(value)
        if hours < 1:
            raise LastExecutionThresholdError("must be at least 1 hour")
        return hours

    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise LastExecutionThresholdError("empty value")
        m = _LAST_EXEC_THRESHOLD_RE.match(s)
        if not m:
            raise LastExecutionThresholdError(
                "use a positive number (hours) or add suffix h, d, or w "
                "(e.g. 24, 24h, 1d, 2w); months/years are not supported)"
            )
        n = int(m.group(1))
        if n < 1:
            raise LastExecutionThresholdError("value must be at least 1")
        suffix = (m.group(2) or "h").lower()
        if suffix == "h":
            return n
        if suffix == "d":
            return n * 24
        if suffix == "w":
            return n * 24 * 7
        raise LastExecutionThresholdError("unsupported suffix")

    raise LastExecutionThresholdError(f"unsupported type {type(value).__name__}")


def coerce_stored_last_execution_threshold(value: Any) -> Union[int, str]:
    """
    Validate and return a JSON-storable form: int for plain hours, or compact string for d/w (and explicit h).
    """
    last_execution_threshold_to_hours(value)

    if isinstance(value, (int, float)):
        iv = int(value)
        if isinstance(value, float) and iv != value:
            raise LastExecutionThresholdError("fractional hours are not supported")
        return iv

    if not isinstance(value, str):
        raise LastExecutionThresholdError(f"unsupported type {type(value).__name__}")
    s = value.strip()
    m = _LAST_EXEC_THRESHOLD_RE.match(s)
    if not m:
        raise LastExecutionThresholdError("invalid threshold string")
    n_str, suf = m.group(1), m.group(2)
    suf_l = (suf or "h").lower()
    if not suf or suf_l == "h":
        return int(n_str)
    return f"{int(n_str)}{suf_l}"


def normalize_recon_parameters_dict(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Copy parameters and coerce last_execution_threshold when present."""
    out = dict(parameters)
    if "last_execution_threshold" in out and out["last_execution_threshold"] is not None:
        out["last_execution_threshold"] = coerce_stored_last_execution_threshold(
            out["last_execution_threshold"]
        )
    return out
