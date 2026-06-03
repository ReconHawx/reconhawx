"""
Synchronous certificate matching (runs in asyncio.to_thread).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from domain_config_builder import MatchingSnapshot, ProgramCTMatchState
from models import CertificateInfo, MatchResult
from protected_domain_similarity import best_match_among_protected

logger = logging.getLogger(__name__)


def _cert_metadata_details(cert_info: CertificateInfo) -> Dict[str, Any]:
    return {
        "cert_issuer": cert_info.issuer,
        "cert_fingerprint": cert_info.fingerprint,
        "cert_not_before": cert_info.not_before,
        "cert_seen_at": cert_info.seen_at,
        "cert_all_domains": cert_info.domains,
    }


def _match_keyword_or_similarity(
    domain_lower: str,
    state: ProgramCTMatchState,
    cert_info: CertificateInfo,
) -> Optional[MatchResult]:
    base_details = dict(_cert_metadata_details(cert_info))
    base_details["match_source"] = "keyword_or_similarity"

    for keyword in state.keywords:
        if keyword in domain_lower:
            d = dict(base_details)
            d["matched_keyword"] = keyword
            return MatchResult(
                matched=True,
                protected_domain=keyword,
                cert_domain=domain_lower,
                similarity_score=0.90,
                match_type="keyword",
                details=d,
            )

    if state.protected_list:
        best_s, best_p = best_match_among_protected(domain_lower, state.protected_list)
        if best_s >= state.similarity_threshold and best_p is not None:
            d = dict(base_details)
            d["similarity_threshold"] = state.similarity_threshold
            return MatchResult(
                matched=True,
                protected_domain=best_p,
                cert_domain=domain_lower,
                similarity_score=best_s,
                match_type="protected_similarity",
                details=d,
            )

    return None


def match_certificate_sync(
    cert_info: CertificateInfo,
    snap: MatchingSnapshot,
) -> Tuple[List[Tuple[MatchResult, str]], int]:
    """
    Match one certificate against a snapshot. Returns (pending alerts, match count).
    """
    pending: List[Tuple[MatchResult, str]] = []
    matches_found = 0
    vg = snap.variation_generator
    alerted_domains: set[str] = set()

    for domain in cert_info.domains:
        domain_lower = domain.lower().strip()

        if domain_lower in alerted_domains:
            continue
        if vg.is_legitimate_subdomain(domain_lower):
            continue
        if vg.is_protected_domain(domain_lower):
            continue

        variation_info = vg.match(domain_lower)
        if variation_info:
            alerted_domains.add(domain_lower)
            matches_found += 1
            match = MatchResult(
                matched=True,
                protected_domain=variation_info.protected_domain,
                cert_domain=domain_lower,
                similarity_score=0.95,
                match_type=f"dnstwist:{variation_info.fuzzer}",
                details={
                    "fuzzer": variation_info.fuzzer,
                    **_cert_metadata_details(cert_info),
                    "match_source": "variation_generator",
                },
            )
            logger.warning(
                "🚨 CT ALERT: %s matches variation of %s (program=%s, fuzzer=%s)",
                match.cert_domain,
                match.protected_domain,
                variation_info.program_name,
                variation_info.fuzzer,
            )
            pending.append((match, variation_info.program_name))

    for domain in cert_info.domains:
        domain_lower = domain.lower().strip()

        if domain_lower in alerted_domains:
            continue
        if vg.is_legitimate_subdomain(domain_lower):
            continue
        if vg.is_protected_domain(domain_lower):
            continue

        for program_name, state in snap.program_match_states.items():
            if domain_lower in alerted_domains:
                continue
            try:
                match = _match_keyword_or_similarity(domain_lower, state, cert_info)
                if match:
                    alerted_domains.add(domain_lower)
                    matches_found += 1
                    logger.warning(
                        "🚨 CT ALERT: %s looks like %s (program=%s, type=%s, score=%.2f)",
                        match.cert_domain,
                        match.protected_domain,
                        program_name,
                        match.match_type,
                        match.similarity_score,
                    )
                    pending.append((match, program_name))
            except Exception as e:
                logger.error("Error processing certificate for program %s: %s", program_name, e)

    return pending, matches_found
