"""Params fingerprint for last-execution matching (excludes operational params)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, FrozenSet, Mapping, Optional

# Operational / scheduling keys — never affect whether two runs are the "same scan".
GLOBAL_EXCLUDE_KEYS: FrozenSet[str] = frozenset(
    {
        "last_execution_threshold",
        "timeout",
        "chunk_size",
        "batch_size",
        "max_workers",
        "domains_per_worker",
        "ips_per_worker",
        "ip_limit",
        "max_cidr_size",
        "port_scan_timeout",
        "force_ip",
        "httpx_urls_per_job",
        "katana_timeout",
        "rate_limit",
        "retries",
        "http_timeout",
    }
)

# Per-task keys that define scan semantics (after global exclude). Empty = task_type only.
TASK_PARAM_ALLOWLIST: Dict[str, FrozenSet[str]] = {
    "fuzz_website": frozenset({"wordlist"}),
    "dns_bruteforce": frozenset({"wordlist"}),
    "nuclei_scan": frozenset(
        {
            "template",
            "automatic_scan",
            "tags",
            "severity",
            "interactsh_server",
            "interactsh_token",
            "headless",
            "cmd_args",
        }
    ),
    "wpscan": frozenset({"enumerate"}),
    "typosquat_detection": frozenset(
        {
            "analyze_input_as_variations",
            "source",
            "max_variations",
            "fuzzers",
            "active_checks",
            "geoip_checks",
            "exclude_tested",
            "include_subdomains",
            "recalculate_risk",
            "enable_fuzzing",
            "fuzzer_wordlist",
        }
    ),
    "crawl_website": frozenset({"depth"}),
    "subdomain_permutations": frozenset({"permutation_list", "permutation_limit"}),
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_payload(task_type: str, params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the dict that is hashed for a task + params pair."""
    raw = dict(params) if params else {}
    filtered = {k: v for k, v in raw.items() if k not in GLOBAL_EXCLUDE_KEYS}

    allowlist = TASK_PARAM_ALLOWLIST.get(task_type)
    if allowlist is not None:
        filtered = {k: filtered[k] for k in sorted(allowlist) if k in filtered}
    else:
        filtered = {}

    return {"task_type": task_type, "params": filtered}


def params_fingerprint(task_type: str, params: Optional[Mapping[str, Any]] = None) -> str:
    """Stable SHA-256 hex fingerprint for last-execution matching."""
    payload = fingerprint_payload(task_type, params)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return digest
