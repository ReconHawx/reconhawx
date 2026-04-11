"""Synchronous in-scope checks (mirrors ProgramRepository.is_domain_in_scope logic)."""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


def domain_in_scope(
    hostname: str,
    domain_regex: Optional[List[str]],
    out_of_scope_regex: Optional[List[str]],
) -> bool:
    """
    Return True if hostname matches at least one in-scope pattern and no exclusion pattern.

    Matches async ProgramRepository.is_domain_in_scope behavior without a DB round-trip.
    """
    if not hostname:
        return False
    domain_regex = domain_regex or []
    out_of_scope_regex = out_of_scope_regex or []

    matches_in_scope = False
    for regex_pattern in domain_regex:
        try:
            if re.match(regex_pattern, hostname):
                matches_in_scope = True
                break
        except re.error:
            logger.warning("Invalid in-scope regex pattern: %s", regex_pattern)
            continue

    if not matches_in_scope:
        return False

    for regex_pattern in out_of_scope_regex:
        try:
            if re.match(regex_pattern, hostname):
                logger.info(
                    "Domain %r matched out-of-scope pattern %r", hostname, regex_pattern
                )
                return False
        except re.error:
            logger.warning("Invalid out-of-scope regex pattern: %s", regex_pattern)
            continue

    return True
