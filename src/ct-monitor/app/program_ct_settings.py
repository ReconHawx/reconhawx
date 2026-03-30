"""Per-program CT monitor settings from Recon API (ct_monitor_program_settings JSONB)."""

from __future__ import annotations

from typing import Dict, Set, Tuple

# Match ct-monitor config.py default CT_TLD_FILTER
DEFAULT_TLD_FILTER_STR = "com,net,org,io,co,app,xyz,online,site,info,biz"
DEFAULT_SIMILARITY_THRESHOLD = 0.75


def default_tld_set() -> Set[str]:
    return {x.strip().lower() for x in DEFAULT_TLD_FILTER_STR.split(",") if x.strip()}


def program_tlds_and_similarity(program_data: Dict) -> Tuple[Set[str], float]:
    raw = program_data.get("ct_monitor_program_settings") or {}
    if not isinstance(raw, dict):
        raw = {}
    tld_str = (raw.get("tld_filter") or "").strip()
    if tld_str:
        tlds = {x.strip().lower() for x in tld_str.split(",") if x.strip()}
    else:
        tlds = default_tld_set()
    sim = raw.get("similarity_threshold")
    try:
        thr = float(sim) if sim is not None else DEFAULT_SIMILARITY_THRESHOLD
    except (TypeError, ValueError):
        thr = DEFAULT_SIMILARITY_THRESHOLD
    thr = max(0.0, min(1.0, thr))
    return tlds, thr
