"""
Typosquat Filtering Service - gates typosquat domain insertion based on
similarity to protected domains and protected keyword matching.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from services.protected_domain_similarity_service import (
    _extract_apex_domain,
    best_similarity_typo_to_protected,
)

logger = logging.getLogger(__name__)


class TyposquatFilteringService:

    @staticmethod
    def should_insert_domain(
        typo_domain: str,
        protected_domains: List[str],
        protected_subdomain_prefixes: List[str],
        filtering_settings: Dict[str, Any],
        asset_apex_domains: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Determine whether a typosquat domain passes filtering and should be
        inserted into the database.

        Returns:
            (passes, reason) – ``passes`` is True when the domain qualifies;
            ``reason`` is a human-readable explanation.
        """
        if not filtering_settings.get("enabled", False):
            return True, "filtering_disabled"

        min_similarity = filtering_settings.get("min_similarity_percent", 0.0)
        max_sim = 0.0  # Used in final return when similarity check ran

        # --- Check 0: exact apex match with protected domain or asset apex → filter out ---
        if typo_domain:
            typo_apex = _extract_apex_domain(typo_domain).lower()
            protected_apexes = {_extract_apex_domain(p).lower() for p in (protected_domains or [])}
            asset_apexes = {a.lower() for a in (asset_apex_domains or [])}
            blocked_apexes = protected_apexes | asset_apexes
            if typo_apex in blocked_apexes:
                if typo_apex in protected_apexes:
                    logger.info(
                        f"Domain {typo_domain} filtered out: exact apex match with protected domain"
                    )
                    return False, "exact_apex_match:protected"
                else:
                    logger.info(
                        f"Domain {typo_domain} filtered out: exact apex match with asset apex domain"
                    )
                    return False, "exact_apex_match:asset"

        # --- Check 1: keyword matching (protected_subdomain_prefixes acts as keyword list) ---
        if protected_subdomain_prefixes and typo_domain:
            domain_lower = typo_domain.lower()
            for keyword in protected_subdomain_prefixes:
                keyword_lower = keyword.lower().strip()
                if keyword_lower and keyword_lower in domain_lower:
                    logger.info(
                        f"Domain {typo_domain} matched protected keyword '{keyword}'"
                    )
                    return True, f"keyword_match:{keyword}"

        # --- Check 2: similarity with protected domains ---
        if protected_domains and typo_domain and min_similarity > 0:
            max_sim = 0.0
            best_match: Optional[str] = None

            for protected in protected_domains:
                sim = best_similarity_typo_to_protected(typo_domain, protected) * 100
                if sim > max_sim:
                    max_sim = sim
                    best_match = protected

            if max_sim >= min_similarity:
                logger.info(
                    f"Domain {typo_domain} passed similarity filter "
                    f"({max_sim:.1f}% >= {min_similarity}% with {best_match})"
                )
                return True, f"similarity:{max_sim:.1f}%:{best_match}"

            logger.info(
                f"Domain {typo_domain} FAILED similarity filter "
                f"(best {max_sim:.1f}% < {min_similarity}% with {best_match})"
            )
        elif not protected_domains:
            # No protected domains: allow all only if we also have no keywords
            # (no filter criteria at all). If we have keywords, we already checked
            # them above – no match means fail.
            if not protected_subdomain_prefixes:
                return True, "no_protected_domains"
            # Have keywords but no protected domains; no keyword match → fail
            return False, "no_match:no_keyword_match"

        return False, f"no_match:best_similarity={max_sim:.1f}%"
