"""Synchronous in-scope checks (mirrors ProgramRepository.is_domain_in_scope logic)."""

import logging
from typing import Any, Dict, List, Optional

from utils.scope_patterns import is_domain_in_scope_structured_and_legacy

logger = logging.getLogger(__name__)


def domain_in_scope(
    hostname: str,
    domain_regex: Optional[List[str]],
    out_of_scope_regex: Optional[List[str]],
    scope_domains: Optional[List[Dict[str, Any]]] = None,
    out_of_scope_domains: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Return True if hostname matches at least one in-scope rule (structured or legacy)
    and no exclusion rule.

    Matches async ProgramRepository.is_domain_in_scope behavior without a DB round-trip.
    """
    return is_domain_in_scope_structured_and_legacy(
        hostname,
        scope_domains,
        out_of_scope_domains,
        domain_regex,
        out_of_scope_regex,
    )
