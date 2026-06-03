"""Per-program CT monitor settings from Recon API (ct_monitor_program_settings JSONB)."""

from __future__ import annotations

import os
from typing import Dict, Set, Tuple

# Legacy default when CT_INGESTION_TLD_FILTER_ENABLED=true and program tld_filter is empty
DEFAULT_TLD_FILTER_STR = "com,net,org,io,co,app,xyz,online,site,info,biz"
DEFAULT_SIMILARITY_THRESHOLD = 0.75


def ingestion_tld_filter_enabled() -> bool:
    """When false (default), all certificate TLDs are ingested and matched."""
    raw = os.getenv("CT_INGESTION_TLD_FILTER_ENABLED", "false").strip().lower()
    return raw in ("true", "1", "yes", "on")


def default_tld_set() -> Set[str]:
    return {x.strip().lower() for x in DEFAULT_TLD_FILTER_STR.split(",") if x.strip()}


def program_similarity_threshold(program_data: Dict) -> float:
    raw = program_data.get("ct_monitor_program_settings") or {}
    if not isinstance(raw, dict):
        raw = {}
    sim = raw.get("similarity_threshold")
    try:
        thr = float(sim) if sim is not None else DEFAULT_SIMILARITY_THRESHOLD
    except (TypeError, ValueError):
        thr = DEFAULT_SIMILARITY_THRESHOLD
    return max(0.0, min(1.0, thr))


def program_tlds_and_similarity(program_data: Dict) -> Tuple[Set[str], float]:
    """
    Parse per-program CT settings.

    tld_filter is only used when ingestion_tld_filter_enabled(); otherwise returns empty TLD set.
    Empty program tld_filter no longer falls back to default_tld_set when ingestion filter is off.
    """
    sim = program_similarity_threshold(program_data)
    if not ingestion_tld_filter_enabled():
        return set(), sim

    raw = program_data.get("ct_monitor_program_settings") or {}
    if not isinstance(raw, dict):
        raw = {}
    tld_str = (raw.get("tld_filter") or "").strip()
    if tld_str:
        tlds = {x.strip().lower() for x in tld_str.split(",") if x.strip()}
    else:
        tlds = default_tld_set()
    return tlds, sim
