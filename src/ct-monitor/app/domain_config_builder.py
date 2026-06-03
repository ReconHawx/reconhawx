"""
Build CT monitor domain/match configuration off the asyncio event loop.

Used during API refresh so dnstwist variation generation does not block HTTP probes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple, Union

import program_ct_settings
from variation_generator import DnstwistVariationGenerator

logger = logging.getLogger(__name__)


@dataclass
class ProgramCTMatchState:
    """Per-program keywords and similarity inputs (mirrors main.ProgramCTMatchState)."""

    keywords: List[str]
    similarity_threshold: float
    protected_list: List[str]


@dataclass
class MatchingSnapshot:
    """Immutable-ish view for certificate matching in a worker thread."""

    variation_generator: DnstwistVariationGenerator
    program_match_states: Dict[str, ProgramCTMatchState]


@dataclass
class DomainConfigBundle:
    """Full domain config produced by refresh; swapped under a short lock in main."""

    any_ct_enabled: bool
    ingestion_tld_union: Set[str]
    protected_domains: Dict[str, Set[str]]
    program_match_states: Dict[str, ProgramCTMatchState]
    variation_generator: DnstwistVariationGenerator
    programs_ct_enabled_detail: List[Dict[str, Any]]
    total_domains: int
    total_variations: int

    def matching_snapshot(self) -> MatchingSnapshot:
        return MatchingSnapshot(
            variation_generator=self.variation_generator,
            program_match_states=dict(self.program_match_states),
        )


def build_domain_config_from_loaded(
    loaded: List[Tuple[str, Any]],
) -> DomainConfigBundle:
    """Sync builder — run via asyncio.to_thread from main."""
    any_ct_enabled = any(bool(pd.get("ct_monitoring_enabled")) for _, pd in loaded)

    if program_ct_settings.ingestion_tld_filter_enabled():
        union_tlds: Set[str] = set()
        for _, program_data in loaded:
            if not program_data.get("ct_monitoring_enabled"):
                continue
            ptlds, _ = program_ct_settings.program_tlds_and_similarity(program_data)
            union_tlds |= ptlds
        if any_ct_enabled:
            ingestion_tld_union = (
                union_tlds if union_tlds else program_ct_settings.default_tld_set()
            )
        else:
            ingestion_tld_union = program_ct_settings.default_tld_set()
    else:
        ingestion_tld_union = set()

    variation_generator = DnstwistVariationGenerator()
    protected_domains: Dict[str, Set[str]] = {}
    program_match_states: Dict[str, ProgramCTMatchState] = {}
    total_domains = 0
    total_variations = 0

    for program_name, program_data in loaded:
        if not program_data.get("ct_monitoring_enabled"):
            continue

        domains: Set[str] = set()
        protected = program_data.get("protected_domains", [])
        if protected:
            domains.update(d.lower().strip() for d in protected if d)
        seeds = program_data.get("seed_domains", [])
        if seeds:
            domains.update(d.lower().strip() for d in seeds if d)
        settings = program_data.get("settings", {})
        if isinstance(settings, dict):
            root_domains = settings.get("root_domains", [])
            if root_domains:
                domains.update(d.lower().strip() for d in root_domains if d)

        raw_keywords = program_data.get("protected_subdomain_prefixes") or []
        keywords_norm: List[str] = []
        seen_kw: Set[str] = set()
        for k in raw_keywords:
            if not k:
                continue
            k2 = str(k).lower().strip()
            if k2 and k2 not in seen_kw:
                seen_kw.add(k2)
                keywords_norm.append(k2)

        if not domains and not keywords_norm:
            continue

        protected_domains[program_name] = domains
        variations_added = 0
        if domains:
            variations_added = variation_generator.add_protected_domains(
                list(domains),
                program_name,
            )
            total_variations += variations_added

        sim_thr = program_ct_settings.program_similarity_threshold(program_data)
        program_match_states[program_name] = ProgramCTMatchState(
            keywords=keywords_norm,
            similarity_threshold=sim_thr,
            protected_list=sorted(domains),
        )
        total_domains += len(domains)
        kw_info = f", {len(keywords_norm)} keywords" if keywords_norm else ""
        logger.info(
            "  ✓ Program '%s': %s protected domains%s, %s variations (CT similarity=%.2f)",
            program_name,
            len(domains),
            kw_info,
            f"{variations_added:,}",
            sim_thr,
        )

    prog_ct_rows: List[Dict[str, Any]] = []
    for program_name, program_data in loaded:
        if not program_data.get("ct_monitoring_enabled"):
            continue
        sim_thr = program_ct_settings.program_similarity_threshold(program_data)
        if program_ct_settings.ingestion_tld_filter_enabled():
            ptlds, _ = program_ct_settings.program_tlds_and_similarity(program_data)
            tld_display: Union[List[str], str] = sorted(ptlds)
        else:
            tld_display = "all"
        prog_ct_rows.append(
            {
                "program_name": program_name,
                "similarity_threshold": round(float(sim_thr), 4),
                "tld_allowlist": tld_display,
                "matcher_active": program_name in program_match_states,
            }
        )
    prog_ct_rows.sort(key=lambda r: r["program_name"])

    return DomainConfigBundle(
        any_ct_enabled=any_ct_enabled,
        ingestion_tld_union=ingestion_tld_union,
        protected_domains=protected_domains,
        program_match_states=program_match_states,
        variation_generator=variation_generator,
        programs_ct_enabled_detail=prog_ct_rows,
        total_domains=total_domains,
        total_variations=total_variations,
    )
