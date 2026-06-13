"""Structured program scope patterns: hostname matching and apex extraction.

Patterns use dot-separated labels; a label may be ``*`` (wildcard label).
Legacy regex arrays are matched separately with re.match.

Keep matching semantics in sync with ct-monitor's precompiled port in
``src/ct-monitor/app/scope_matcher.py`` (CT asset monitoring).
"""

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
    """Validate and normalize a scope entry. Returns (pattern, wildcard)."""
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


def sanitize_scope_entries(
    entries: Optional[Sequence[Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Split a structured scope list into (valid, dropped).

    Each valid entry is returned in normalized form as
    ``{"pattern": <lowercased>, "wildcard": <bool>}``. Invalid or non-dict
    rows are collected in ``dropped`` as ``{"pattern": <raw>, "reason": <str>}``
    so callers can log them and/or surface them to the UI.

    The helper is intentionally permissive: it never raises. It is meant for
    write paths that want to drop bad rows silently rather than reject the
    whole request.
    """
    valid: List[Dict[str, Any]] = []
    dropped: List[Dict[str, str]] = []
    if not entries:
        return valid, dropped
    for raw in entries:
        if not isinstance(raw, dict):
            dropped.append({"pattern": str(raw), "reason": "not an object"})
            continue
        try:
            pat, wc = validate_scope_domain_entry(raw)
        except ValueError as e:
            raw_pat = raw.get("pattern")
            dropped.append(
                {
                    "pattern": raw_pat if isinstance(raw_pat, str) else str(raw_pat),
                    "reason": str(e),
                }
            )
            continue
        valid.append({"pattern": pat, "wildcard": wc})
    return valid, dropped


def structured_pattern_to_regex(pattern: str) -> str:
    """Build anchored regex for a validated structured pattern (lowercase)."""
    labels = pattern.split(".")
    if not labels:
        raise ValueError("empty pattern")
    if labels[0] == "*":
        if len(labels) < 2:
            raise ValueError("pattern * alone is invalid")
        rest = r"\.".join(re.escape(x) for x in labels[1:])
        return r"^(?:[a-z0-9-]+\.)+" + rest + r"$"
    parts: List[str] = []
    for lab in labels:
        if lab == "*":
            parts.append(r"[a-z0-9-]+")
        else:
            parts.append(re.escape(lab))
    return r"^" + r"\.".join(parts) + r"$"


def _exact_with_optional_subdomains_regex(pattern: str) -> str:
    """pattern has no *; wildcard=True → apex and any subdomain."""
    escaped = r"\.".join(re.escape(x) for x in pattern.split("."))
    return r"^(?:[a-z0-9-]+\.)*" + escaped + r"$"


def hostname_matches_structured(pattern: str, wildcard: bool, hostname: str) -> bool:
    """Return True if hostname matches this structured scope row."""
    host = _norm_host(hostname)
    if not host:
        return False
    pat = _norm_host(pattern)
    if not pat:
        return False
    try:
        if "*" in pat:
            cre = re.compile(structured_pattern_to_regex(pat))
            return cre.match(host) is not None
        if wildcard:
            cre = re.compile(_exact_with_optional_subdomains_regex(pat))
            return cre.match(host) is not None
        cre = re.compile(r"^" + r"\.".join(re.escape(x) for x in pat.split(".")) + r"$")
        return cre.match(host) is not None
    except re.error as e:
        logger.warning("Bad structured scope regex for pattern %r: %s", pat, e)
        return False


def hostname_matches_legacy_regex(regex_pattern: str, hostname: str) -> bool:
    host = _norm_host(hostname)
    if not host:
        return False
    try:
        return re.match(regex_pattern, host) is not None
    except re.error:
        logger.warning("Invalid legacy regex pattern: %s", regex_pattern)
        return False


def is_domain_in_scope_structured_and_legacy(
    hostname: str,
    scope_domains: Optional[Sequence[Dict[str, Any]]],
    out_of_scope_domains: Optional[Sequence[Dict[str, Any]]],
    domain_regex: Optional[Sequence[str]],
    out_of_scope_regex: Optional[Sequence[str]],
) -> bool:
    """
    True if hostname matches at least one in-scope rule (structured or legacy)
    and does not match any out-of-scope rule.
    """
    host = _norm_host(hostname)
    if not host:
        return False

    scope_domains = scope_domains or []
    domain_regex = domain_regex or []

    matches_in_scope = False
    for entry in scope_domains:
        try:
            pat, wc = validate_scope_domain_entry(entry)
        except ValueError as e:
            logger.warning("Skipping invalid scope_domains entry: %s", e)
            continue
        if hostname_matches_structured(pat, wc, host):
            matches_in_scope = True
            break

    if not matches_in_scope:
        for regex_pattern in domain_regex:
            if hostname_matches_legacy_regex(regex_pattern, host):
                matches_in_scope = True
                break

    if not matches_in_scope:
        return False

    oos_struct = out_of_scope_domains or []
    oos_regex = out_of_scope_regex or []

    for entry in oos_struct:
        try:
            pat, wc = validate_scope_domain_entry(entry)
        except ValueError as e:
            logger.warning("Skipping invalid out_of_scope_domains entry: %s", e)
            continue
        if hostname_matches_structured(pat, wc, host):
            logger.info("Domain %r matched out-of-scope pattern %r", host, pat)
            return False

    for regex_pattern in oos_regex:
        try:
            if re.match(regex_pattern, host):
                logger.info("Domain %r matched out-of-scope legacy regex", host)
                return False
        except re.error:
            logger.warning("Invalid out-of-scope regex pattern: %s", regex_pattern)
            continue

    return True


_TWO_LEVEL_TLDS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


def apex_from_pattern(pattern: str) -> str:
    """
    Best-effort apex / discovery root string for a structured pattern.
    Strips leading * label; uses last 2 or 3 labels for common ccTLDs.
    """
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
    """
    Strings for workflow program_scope_domains input: per-row discovery roots, deduped.

    Wildcard patterns use the hostname suffix after the last ``*``; others use
    :func:`apex_from_pattern`. ``filter_mode``: ``all`` | ``wildcard_only`` |
    ``non_wildcard_only``. Legacy regex rows contribute via
    :func:`_legacy_regex_to_apex_guess` when ``filter_mode`` is ``all`` only.
    """
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
    """Mirror ProgramDetail extractApexDomain / task_executor heuristic."""
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
