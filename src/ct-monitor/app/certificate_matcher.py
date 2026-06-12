"""
Synchronous certificate matching (runs in asyncio.to_thread).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_config_builder import MatchingSnapshot, ProgramCTMatchState
from models import CertificateInfo, MatchResult
from protected_domain_similarity import (
    PreparedTypo,
    best_match_among_prepared,
    prepare_typo,
    similarity_impossible_by_length_prepared,
)

logger = logging.getLogger(__name__)


def _cert_metadata_details(cert_info: CertificateInfo) -> Dict[str, Any]:
    return {
        "cert_issuer": cert_info.issuer,
        "cert_fingerprint": cert_info.fingerprint,
        "cert_not_before": cert_info.not_before,
        "cert_seen_at": cert_info.seen_at,
        "cert_all_domains": cert_info.domains,
    }


def _first_matching_keyword(
    domain_lower: str,
    keywords: List[str],
    matched_keywords: Optional[Set[str]],
) -> Optional[str]:
    """First keyword (in program order) present in the domain.

    ``matched_keywords`` is the automaton scan result for this domain across all
    programs; when None, fall back to per-keyword substring checks.
    """
    if matched_keywords is not None:
        for keyword in keywords:
            if keyword in matched_keywords:
                return keyword
        return None
    for keyword in keywords:
        if keyword in domain_lower:
            return keyword
    return None


def _match_keyword_or_similarity(
    domain_lower: str,
    state: ProgramCTMatchState,
    cert_info: CertificateInfo,
    matched_keywords: Optional[Set[str]] = None,
    prepared: Optional[PreparedTypo] = None,
) -> Tuple[Optional[MatchResult], bool]:
    """
    Keyword or protected similarity match.

    Returns (match_or_none, similarity_skipped_by_length_gate).
    """
    keyword = _first_matching_keyword(domain_lower, state.keywords, matched_keywords)
    if keyword is not None:
        d = dict(_cert_metadata_details(cert_info))
        d["match_source"] = "keyword_or_similarity"
        d["matched_keyword"] = keyword
        return (
            MatchResult(
                matched=True,
                protected_domain=keyword,
                cert_domain=domain_lower,
                similarity_score=0.90,
                match_type="keyword",
                details=d,
            ),
            False,
        )

    if state.protected_prepared:
        if prepared is None:
            prepared = prepare_typo(domain_lower)
        if similarity_impossible_by_length_prepared(
            prepared,
            state.protected_collapsed_lengths,
            state.similarity_threshold,
        ):
            return None, True

        best_s, best_p = best_match_among_prepared(
            prepared, state.protected_prepared, score_cutoff=state.similarity_threshold
        )
        if best_s >= state.similarity_threshold and best_p is not None:
            d = dict(_cert_metadata_details(cert_info))
            d["match_source"] = "keyword_or_similarity"
            d["similarity_threshold"] = state.similarity_threshold
            return (
                MatchResult(
                    matched=True,
                    protected_domain=best_p,
                    cert_domain=domain_lower,
                    similarity_score=best_s,
                    match_type="protected_similarity",
                    details=d,
                ),
                False,
            )

    return None, False


def match_certificate_sync(
    cert_info: CertificateInfo,
    snap: MatchingSnapshot,
) -> Tuple[List[Tuple[MatchResult, str]], int, int]:
    """
    Match one certificate against a snapshot.

    Returns (pending alerts, match count, similarity_skipped count).
    """
    pending: List[Tuple[MatchResult, str]] = []
    matches_found = 0
    similarity_skipped = 0
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
            logger.info(
                "CT ALERT: %s matches variation of %s (program=%s, fuzzer=%s)",
                match.cert_domain,
                match.protected_domain,
                variation_info.program_name,
                variation_info.fuzzer,
            )
            pending.append((match, variation_info.program_name))
            continue

        if not snap.program_match_states:
            continue

        # Shared per-domain work: one automaton scan for all programs' keywords,
        # and one PreparedTypo (suffix fragments + collapsed + apex) reused by
        # every program's similarity check.
        matched_keywords = snap.find_keywords(domain_lower)
        prepared: Optional[PreparedTypo] = None

        for program_name, state in snap.program_match_states.items():
            try:
                if prepared is None and state.protected_prepared:
                    prepared = prepare_typo(domain_lower)
                match, skipped = _match_keyword_or_similarity(
                    domain_lower,
                    state,
                    cert_info,
                    matched_keywords=matched_keywords,
                    prepared=prepared,
                )
                if skipped:
                    similarity_skipped += 1
                if match:
                    alerted_domains.add(domain_lower)
                    matches_found += 1
                    logger.info(
                        "CT ALERT: %s looks like %s (program=%s, type=%s, score=%.2f)",
                        match.cert_domain,
                        match.protected_domain,
                        program_name,
                        match.match_type,
                        match.similarity_score,
                    )
                    pending.append((match, program_name))
                    break
            except Exception as e:
                logger.error(
                    "Error processing certificate for program %s: %s", program_name, e
                )

    return pending, matches_found, similarity_skipped
