"""Structured program scope: discovery targets (kept in sync with api/app/utils/scope_patterns.py)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$|^[a-z0-9]$")


def _norm_host(hostname: str) -> str:
    h = (hostname or "").strip().lower().strip(".")
    return h


def _valid_literal_label(lab: str) -> bool:
    if not lab or len(lab) > 63:
        return False
    if lab == "*":
        return True
    return bool(_LABEL_RE.match(lab))


def validate_scope_domain_entry(entry: Dict[str, Any]) -> Tuple[str, bool]:
    if not isinstance(entry, dict):
        raise ValueError("scope entry must be an object")
    pattern = entry.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("scope entry requires non-empty pattern string")
    pattern = _norm_host(pattern)
    if not pattern:
        raise ValueError("invalid pattern")
    labels = pattern.split(".")
    if any(lab == "" for lab in labels):
        raise ValueError("invalid pattern: empty label")
    for lab in labels:
        if lab != "*" and not _valid_literal_label(lab):
            raise ValueError(f"invalid label in pattern: {lab!r}")
    wildcard = bool(entry.get("wildcard", False))
    if any(l == "*" for l in labels):
        wildcard = True
    return pattern, wildcard


_TWO_LEVEL_TLDS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


def apex_from_pattern(pattern: str) -> str:
    pat = _norm_host(pattern)
    if not pat:
        return ""
    labels = [x for x in pat.split(".") if x]
    if labels and labels[0] == "*":
        labels = labels[1:]
    if not labels:
        return ""
    if len(labels) >= 2:
        if len(labels) >= 3 and labels[-2] in _TWO_LEVEL_TLDS:
            return ".".join(labels[-3:])
        return ".".join(labels[-2:])
    return labels[0]


def discovery_target_from_scope_pattern(pattern: str) -> str:
    """
    Root hostname string for workflow program_scope_domains discovery.

    If the pattern contains a wildcard label (*), use the suffix after the *last*
    ``*`` so internal wildcards resolve to the correct zone (e.g.
    ``api.*.dev.example.com`` → ``dev.example.com``). Patterns without ``*`` use
    :func:`apex_from_pattern`.
    """
    pat = _norm_host(pattern)
    if not pat:
        return ""
    if "*" not in pat:
        return apex_from_pattern(pat)
    suffix = pat.rsplit("*", 1)[-1].strip(".")
    return _norm_host(suffix) if suffix else ""


def discovery_targets_from_scope(
    scope_domains: Optional[Sequence[Dict[str, Any]]],
    domain_regex: Optional[Sequence[str]],
    filter_mode: str = "all",
) -> List[str]:
    scope_domains = scope_domains or []
    domain_regex = domain_regex or []
    targets: List[str] = []

    for entry in scope_domains:
        try:
            pat, wc = validate_scope_domain_entry(entry)
        except ValueError:
            continue
        if filter_mode == "wildcard_only" and not wc:
            continue
        if filter_mode == "non_wildcard_only" and wc:
            continue
        root = discovery_target_from_scope_pattern(pat)
        if root and "." in root:
            targets.append(root)

    if filter_mode == "all":
        for rx in domain_regex:
            g = _legacy_regex_to_apex_guess(rx)
            if g:
                targets.append(g)

    return sorted(set(targets))


def _legacy_regex_to_apex_guess(regex_pattern: str) -> str:
    domain = regex_pattern
    domain = re.sub(r"\^|\$", "", domain)
    domain = re.sub(r"\.\*", "", domain)
    domain = domain.replace("\\.", ".").replace("\\", "")
    domain = re.sub(r"\(\?:", "", domain).replace(")", "")
    domain = re.sub(r"\[.*?\]", "", domain).strip()
    domain = re.sub(r"^\.+|\.+$", "", domain)
    parts = [p for p in domain.split(".") if p]
    if len(parts) >= 2 and "." in domain:
        apex = ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in _TWO_LEVEL_TLDS else ".".join(parts[-2:])
        return apex
    return ""
