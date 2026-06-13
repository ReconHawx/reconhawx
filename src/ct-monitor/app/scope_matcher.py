"""
Program scope matching for CT asset monitoring.

Ports the matching subset of the API's ``utils/scope_patterns.py``
(structured ``scope_domains`` / ``out_of_scope_domains`` entries plus legacy
``domain_regex`` / ``out_of_scope_regex`` arrays). Keep the matching semantics
in sync with the API module — the API re-checks scope on ingest, so the only
cost of drift here is extra or missing candidate submissions, but the two
should agree.

Unlike the API version (which compiles regexes per call), this module compiles
every pattern once per config refresh: certificate SAN volume makes the hot
path latency-sensitive.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set, Tuple

from domain_labels import extract_apex_domain

logger = logging.getLogger(__name__)

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$|^[a-z0-9]$")


def _norm_host(hostname: str) -> str:
    return (hostname or "").strip().lower().strip(".")


def _valid_literal_label(lab: str) -> bool:
    if not lab or len(lab) > 63:
        return False
    if lab == "*":
        return True
    return bool(_LABEL_RE.match(lab))


def validate_scope_domain_entry(entry: Dict[str, Any]) -> Tuple[str, bool]:
    """Validate and normalize a structured scope entry. Returns (pattern, wildcard)."""
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


def structured_pattern_to_regex(pattern: str) -> str:
    """Build anchored regex source for a validated structured pattern (lowercase)."""
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


def _compile_structured(pattern: str, wildcard: bool) -> Optional[Pattern[str]]:
    try:
        if "*" in pattern:
            return re.compile(structured_pattern_to_regex(pattern))
        if wildcard:
            return re.compile(_exact_with_optional_subdomains_regex(pattern))
        return re.compile(
            r"^" + r"\.".join(re.escape(x) for x in pattern.split(".")) + r"$"
        )
    except re.error as e:
        logger.warning("Bad structured scope regex for pattern %r: %s", pattern, e)
        return None


def _scope_root_from_pattern(pattern: str) -> str:
    """
    Hostname suffix a pattern can match under (for apex prefiltering).

    Wildcard-label patterns use the suffix after the *last* ``*`` so internal
    wildcards resolve to the correct zone (``api.*.dev.example.com`` →
    ``dev.example.com``); other patterns use the pattern itself.
    """
    if "*" not in pattern:
        return pattern
    suffix = pattern.rsplit("*", 1)[-1].strip(".")
    return _norm_host(suffix)


_LEGACY_TWO_LEVEL_TLDS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


def _legacy_regex_to_apex_guess(regex_pattern: str) -> str:
    """Mirror API ``_legacy_regex_to_apex_guess`` heuristic."""
    domain = regex_pattern
    domain = re.sub(r"\^|\$", "", domain)
    domain = re.sub(r"\.\*", "", domain)
    domain = domain.replace("\\.", ".").replace("\\", "")
    domain = re.sub(r"\(\?:", "", domain).replace(")", "")
    domain = re.sub(r"\[.*?\]", "", domain).strip()
    domain = re.sub(r"^\.+|\.+$", "", domain)
    parts = [p for p in domain.split(".") if p]
    if len(parts) >= 2 and "." in domain:
        if len(parts) >= 3 and parts[-2] in _LEGACY_TWO_LEVEL_TLDS:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return ""


class CompiledScopeMatcher:
    """
    Precompiled in-scope / out-of-scope matcher for one program.

    Semantics mirror the API's ``is_domain_in_scope_structured_and_legacy``:
    a hostname is in scope when it matches at least one in-scope rule
    (structured or legacy regex) and no out-of-scope rule.
    """

    def __init__(
        self,
        scope_domains: Optional[Sequence[Dict[str, Any]]] = None,
        out_of_scope_domains: Optional[Sequence[Dict[str, Any]]] = None,
        domain_regex: Optional[Sequence[str]] = None,
        out_of_scope_regex: Optional[Sequence[str]] = None,
    ) -> None:
        self._in_scope: List[Pattern[str]] = []
        self._out_of_scope: List[Pattern[str]] = []
        self._apex_roots: Set[str] = set()

        for entry in scope_domains or []:
            try:
                pattern, wildcard = validate_scope_domain_entry(entry)
            except ValueError as e:
                logger.warning("Skipping invalid scope_domains entry: %s", e)
                continue
            compiled = _compile_structured(pattern, wildcard)
            if compiled is None:
                continue
            self._in_scope.append(compiled)
            root = _scope_root_from_pattern(pattern)
            apex = extract_apex_domain(root) if root else ""
            if apex and "." in apex:
                self._apex_roots.add(apex)

        for raw in domain_regex or []:
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                self._in_scope.append(re.compile(raw))
            except re.error:
                logger.warning("Invalid legacy regex pattern: %s", raw)
                continue
            guess = _legacy_regex_to_apex_guess(raw)
            apex = extract_apex_domain(guess) if guess else ""
            if apex and "." in apex:
                self._apex_roots.add(apex)

        for entry in out_of_scope_domains or []:
            try:
                pattern, wildcard = validate_scope_domain_entry(entry)
            except ValueError as e:
                logger.warning("Skipping invalid out_of_scope_domains entry: %s", e)
                continue
            compiled = _compile_structured(pattern, wildcard)
            if compiled is not None:
                self._out_of_scope.append(compiled)

        for raw in out_of_scope_regex or []:
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                self._out_of_scope.append(re.compile(raw))
            except re.error:
                logger.warning("Invalid out-of-scope regex pattern: %s", raw)

    @property
    def has_in_scope_rules(self) -> bool:
        return bool(self._in_scope)

    @property
    def apex_roots(self) -> Set[str]:
        """Registrable apex domains the in-scope rules can match under (prefilter)."""
        return self._apex_roots

    def matches(self, hostname: str) -> bool:
        """True if hostname is in scope for this program."""
        host = _norm_host(hostname)
        if not host:
            return False
        if not any(cre.match(host) for cre in self._in_scope):
            return False
        return not any(cre.match(host) for cre in self._out_of_scope)
