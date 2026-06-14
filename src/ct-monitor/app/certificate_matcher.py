"""
Synchronous certificate matching (runs in asyncio.to_thread).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from domain_config_builder import MatchingSnapshot, ProgramCTMatchState
from domain_labels import extract_apex_domain
from models import CertificateInfo, MatchResult
from protected_domain_similarity import (
    PreparedTypo,
    best_match_among_prepared,
    prepare_typo,
    similarity_impossible_by_length_prepared,
)

logger = logging.getLogger(__name__)

# (hostname, program_name, program_id) for an in-scope SAN (CT asset monitoring)
AssetMatch = Tuple[str, str, str]
CtLogEvent = Dict[str, Any]


def _match_assets_for_domain(
    domain_lower: str,
    snap: MatchingSnapshot,
    seen: Set[Tuple[str, str]],
    out: List[AssetMatch],
) -> None:
    """
    Scope-based asset matching for one SAN.

    Runs before the typosquat skip rules: legitimate subdomains of protected
    domains are exactly what asset monitoring wants to discover. Wildcard SANs
    are matched and submitted as the hostname after the leading ``*.``.
    """
    host = domain_lower
    if host.startswith("*."):
        host = host[2:]
    if not host or "." not in host:
        return
    apex = extract_apex_domain(host)
    if not apex:
        return
    for program_name in snap.asset_candidate_programs(apex):
        key = (host, program_name)
        if key in seen:
            continue
        state = snap.asset_match_states.get(program_name)
        if state is None:
            continue
        if state.matcher.matches(host):
            seen.add(key)
            out.append((host, program_name, state.program_id))


def _cert_metadata_details(cert_info: CertificateInfo) -> Dict[str, Any]:
    return {
        "cert_issuer": cert_info.issuer,
        "cert_fingerprint": cert_info.fingerprint,
        "cert_not_before": cert_info.not_before,
        "cert_seen_at": cert_info.seen_at,
        "cert_all_domains": cert_info.domains,
    }


def _program_id(snap: MatchingSnapshot, program_name: str) -> Optional[str]:
    return (snap.program_ids or {}).get(program_name)


def _append_skip_log(
    out: List[CtLogEvent],
    *,
    snap: MatchingSnapshot,
    cert_info: CertificateInfo,
    program_name: str,
    domain: str,
    outcome: str,
    protected_domain: Optional[str] = None,
    match_type: Optional[str] = None,
    similarity_score: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    program_id = _program_id(snap, program_name)
    if not program_id:
        return
    event_details = {
        "certificate": cert_info.to_dict(),
        **(details or {}),
    }
    out.append(
        {
            "program_id": program_id,
            "program_name": program_name,
            "event_type": "typosquat_skip",
            "outcome": outcome,
            "domain": domain,
            "protected_domain": protected_domain,
            "match_type": match_type,
            "similarity_score": similarity_score,
            "cert_fingerprint": cert_info.fingerprint,
            "cert_issuer": cert_info.issuer,
            "cert_source": cert_info.source,
            "details": event_details,
        }
    )


def _protected_domain_programs(
    snap: MatchingSnapshot,
    domain_lower: str,
) -> List[Tuple[str, str]]:
    matches: List[Tuple[str, str]] = []
    for program_name, domains in (snap.protected_domains or {}).items():
        if domain_lower in domains:
            matches.append((program_name, domain_lower))
    return matches


def _legitimate_subdomain_programs(
    snap: MatchingSnapshot,
    domain_lower: str,
) -> List[Tuple[str, str]]:
    matches: List[Tuple[str, str]] = []
    for program_name, domains in (snap.protected_domains or {}).items():
        for protected in domains:
            if domain_lower.endswith(f".{protected}"):
                matches.append((program_name, protected))
                break
    return matches


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
        result = (
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
        return result

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
            result = (
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
            return result

    return None, False


def match_certificate_sync(
    cert_info: CertificateInfo,
    snap: MatchingSnapshot,
    collect_logs: bool = False,
) -> Union[
    Tuple[List[Tuple[MatchResult, str]], int, int, List[AssetMatch]],
    Tuple[List[Tuple[MatchResult, str]], int, int, List[AssetMatch], List[CtLogEvent]],
]:
    """
    Match one certificate against a snapshot.

    Returns (pending alerts, match count, similarity_skipped count, asset matches).
    """
    pending: List[Tuple[MatchResult, str]] = []
    matches_found = 0
    similarity_skipped = 0
    vg = snap.variation_generator
    alerted_domains: set[str] = set()
    asset_matches: List[AssetMatch] = []
    asset_seen: Set[Tuple[str, str]] = set()
    log_events: List[CtLogEvent] = []

    for domain in cert_info.domains:
        domain_lower = domain.lower().strip()

        # Asset scope matching runs before the typosquat skip rules below:
        # is_legitimate_subdomain skips exactly the in-scope hostnames asset
        # monitoring is meant to discover.
        if snap.asset_match_states:
            _match_assets_for_domain(domain_lower, snap, asset_seen, asset_matches)

        if domain_lower in alerted_domains:
            continue
        if vg.is_legitimate_subdomain(domain_lower):
            if collect_logs:
                for program_name, protected in _legitimate_subdomain_programs(snap, domain_lower):
                    _append_skip_log(
                        log_events,
                        snap=snap,
                        cert_info=cert_info,
                        program_name=program_name,
                        domain=domain_lower,
                        outcome="skipped_legitimate_subdomain",
                        protected_domain=protected,
                        match_type="legitimate_subdomain",
                    )
            continue
        if vg.is_protected_domain(domain_lower):
            if collect_logs:
                for program_name, protected in _protected_domain_programs(snap, domain_lower):
                    _append_skip_log(
                        log_events,
                        snap=snap,
                        cert_info=cert_info,
                        program_name=program_name,
                        domain=domain_lower,
                        outcome="skipped_protected_domain",
                        protected_domain=protected,
                        match_type="protected_domain",
                    )
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

    if collect_logs:
        return pending, matches_found, similarity_skipped, asset_matches, log_events
    return pending, matches_found, similarity_skipped, asset_matches
