"""
Runtime input validation for recon tasks.

At dispatch time, filters out values that do not match the task's declared
``Task.input_type`` (AssetType or list of AssetType). Invalid values are dropped
with a structured WARNING log in the caller; fully-invalid batches fall through
the executor's existing "no input -> skip task" branch.

Design notes:
- Single source of truth is ``Task.input_type`` (locked to the API manifest /
  ``recon_task_builtin_defaults.yaml`` by ``TaskParameterManager._assert_registry_matches_manifest``).
- ``AssetType.STRING``, ``SERVICE``, ``CERTIFICATE`` and ``SCREENSHOT`` are accept-all
  (utility / debug tasks like ``shell_command`` must not be policed).
- ``AssetType.IP`` uses stdlib ``ipaddress`` (IPv4 + IPv6); the legacy regex-only
  ``utils.utils.is_valid_ip`` is intentionally not used.
- The escape hatch ``RUNNER_INPUT_VALIDATION=off`` (default ``on``) short-circuits
  the validator to accept-all for one release; remove after a stability window.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Sequence, Set

from tasks.base import AssetType
from utils.utils import is_valid_domain, is_valid_url

logger = logging.getLogger(__name__)


_SAMPLE_CAP = 5


def _is_disabled() -> bool:
    raw = os.environ.get("RUNNER_INPUT_VALIDATION", "on")
    return raw.strip().lower() in {"off", "false", "0", "no"}


def _valid_domain(value: str) -> bool:
    return is_valid_domain(value)


def _valid_url(value: str) -> bool:
    ok, _ = is_valid_url(value)
    return ok


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def _valid_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except (ValueError, TypeError):
        return False


# Mapping: AssetType -> predicate. Accept-all types are intentionally absent here
# and handled as "always valid" in ``validate_value``.
_VALIDATORS: Dict[AssetType, Callable[[str], bool]] = {
    AssetType.SUBDOMAIN: _valid_domain,
    AssetType.APEX_DOMAIN: _valid_domain,
    AssetType.URL: _valid_url,
    AssetType.IP: _valid_ip,
    AssetType.CIDR: _valid_cidr,
}


# These types don't carry a shape we can meaningfully validate at dispatch time
# (strings are catch-all; services/certs/screenshots are opaque object references
# that arrive already-typed from upstream steps).
_ACCEPT_ALL: Set[AssetType] = {
    AssetType.STRING,
    AssetType.SERVICE,
    AssetType.CERTIFICATE,
    AssetType.SCREENSHOT,
}


@dataclass
class ValidationResult:
    """Outcome of ``validate_inputs_for_task``."""

    kept: List[str] = field(default_factory=list)
    dropped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    samples: List[str] = field(default_factory=list)


def validate_value(value: Any, asset_type: AssetType) -> bool:
    """Return True iff ``value`` is a valid instance of ``asset_type``.

    Non-string values are accepted (pre-typed model objects from upstream steps).
    Unknown or accept-all AssetTypes are treated as valid.
    """
    if asset_type in _ACCEPT_ALL:
        return True
    if not isinstance(value, str):
        return True
    validator = _VALIDATORS.get(asset_type)
    if validator is None:
        return True
    s = value.strip()
    if not s:
        return False
    return validator(s)


def _normalize_allowed(allowed_types: Iterable[AssetType]) -> List[AssetType]:
    out: List[AssetType] = []
    for t in allowed_types or ():
        if isinstance(t, AssetType):
            out.append(t)
    return out


def _bucket_for(asset_type: AssetType) -> str:
    return f"invalid_{asset_type.value}"


def validate_inputs_for_task(
    values: Sequence[Any],
    allowed_types: Iterable[AssetType],
) -> ValidationResult:
    """Split ``values`` into kept/dropped based on the task's allowed AssetTypes.

    An input is kept if it matches **any** of the declared types (multi-type tasks
    like ``nuclei_scan`` / ``test_http`` accept a mix). The ``by_type`` bucket for
    a dropped value is keyed on the task's first declared type - we don't multi-count.
    """
    result = ValidationResult()

    if not values:
        return result

    allowed = _normalize_allowed(allowed_types)

    if _is_disabled() or not allowed or all(t in _ACCEPT_ALL for t in allowed):
        result.kept = [v for v in values]
        return result

    primary = allowed[0]
    bucket_key = _bucket_for(primary)

    for value in values:
        if any(validate_value(value, t) for t in allowed):
            result.kept.append(value)
            continue
        result.dropped += 1
        result.by_type[bucket_key] = result.by_type.get(bucket_key, 0) + 1
        if len(result.samples) < _SAMPLE_CAP and isinstance(value, str):
            result.samples.append(value)

    return result


__all__ = [
    "ValidationResult",
    "validate_value",
    "validate_inputs_for_task",
]
