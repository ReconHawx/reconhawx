"""
WAF verdict classification for nuclei-based prechecks and secondary heavy-task hints.

Kill switch ``WAF_DETECTION=off`` (also ``false`` / ``0`` / ``no``) mirrors ``RUNNER_INPUT_VALIDATION``.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tasks that probe HTTP and participate in quarantine precheck + scheduling.
HEAVY_HTTP_TASK_NAMES = frozenset(
    {
        "test_http",
        "crawl_website",
        "fuzz_website",
        "nuclei_scan",
        "screenshot_website",
        "wpscan",
    }
)

# Single-file precheck template (one request); see waf-precheck-unified.yaml. Per-vendor
# YAMLs in the same directory are reference-only for the runner precheck.
_PREC_CHECK_TEMPLATE_ID = "waf-precheck-unified"
WAF_PRECHECK_TEMPLATE_PATH = f"/workspace/files/waf-block/{_PREC_CHECK_TEMPLATE_ID}.yaml"


def _is_disabled() -> bool:
    raw = os.environ.get("WAF_DETECTION", "on")
    return raw.strip().lower() in {"off", "false", "0", "no"}


def is_waf_detection_enabled() -> bool:
    return not _is_disabled()


@dataclass
class WafVerdict:
    verdict: str  # "blocked_waf" | "accessible" | "unknown"
    vendor: Optional[str]
    evidence: List[str]
    confidence: float


def build_waf_precheck_command(target: str) -> str:
    """Single-target nuclei run: one bundled template ⇒ one HTTP request per precheck."""
    t = (target or "").strip()
    if not t:
        raise ValueError("waf precheck requires a non-empty target")
    return (
        f"cat << 'EOF' | nuclei -or -silent -j -t {WAF_PRECHECK_TEMPLATE_PATH}\n{t}\nEOF"
    )


def classify_precheck_output(nuclei_jsonl: str) -> WafVerdict:
    """Precheck nuclei JSONL: unified template match ⇒ blocked_waf (vendor omitted)."""
    if _is_disabled():
        return WafVerdict("unknown", None, [], 0.0)

    if not (nuclei_jsonl or "").strip():
        return WafVerdict("accessible", None, [], 1.0)

    evidence: List[str] = []
    saw_line = False
    json_ok = False
    for raw in nuclei_jsonl.splitlines():
        line = raw.strip()
        if not line or line.startswith("stderr:"):
            continue
        saw_line = True
        try:
            row: Dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        json_ok = True
        tid = str(row.get("template-id") or row.get("template_id") or "")
        path = str(row.get("template") or row.get("path") or "").lower()
        if tid == _PREC_CHECK_TEMPLATE_ID or "waf-precheck-unified" in path:
            matched = str(row.get("matched-at") or row.get("matched_at") or row.get("url") or "")
            evidence.append(f"{tid}:{matched}")

    if evidence:
        # Operators do not need vendor granularity for precheck; Redis / logs use verdict only.
        return WafVerdict("blocked_waf", None, evidence, 1.0)

    if saw_line and not json_ok:
        logger.warning("waf precheck output had lines but no parsable JSON; treating as unknown/accessible")
        return WafVerdict("unknown", None, [], 0.3)

    return WafVerdict("accessible", None, [], 1.0)


def _httpx_403_ratio(output: str) -> tuple[int, int, Optional[str]]:
    """Return (count_403, total_json_lines, server_guess)."""
    n403 = 0
    total = 0
    server_guess: Optional[str] = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        code = row.get("status_code") or row.get("status-code")
        try:
            if int(code) == 403:
                n403 += 1
        except (TypeError, ValueError):
            pass
        if not server_guess:
            tech = row.get("tech") or row.get("server") or row.get("header")
            if isinstance(tech, list) and tech:
                server_guess = str(tech[0])
            elif isinstance(tech, str):
                server_guess = tech
    return n403, total, server_guess


def classify_heavy_output(task_name: str, output: str, *, success: bool) -> WafVerdict:
    """Weak secondary signals; reputation layer promotes only after repeated hits."""
    if _is_disabled():
        return WafVerdict("unknown", None, [], 0.0)

    out = output or ""
    if task_name == "screenshot_website":
        return WafVerdict("unknown", None, [], 0.0)

    if task_name == "test_http":
        n403, total, server = _httpx_403_ratio(out)
        if total >= 5 and n403 / total >= 0.8:
            vendor = None
            if server and "cloudflare" in server.lower():
                vendor = "cloudflare"
            return WafVerdict("blocked_waf", vendor, [f"httpx_403_ratio={n403}/{total}"], 0.5)
        return WafVerdict("unknown", None, [], 0.0)

    if task_name in {"crawl_website", "fuzz_website"}:
        n403, total, _ = _httpx_403_ratio(out)
        if total >= 5 and n403 / total >= 0.8:
            return WafVerdict("blocked_waf", None, [f"http_tool_403_ratio={n403}/{total}"], 0.5)
        return WafVerdict("unknown", None, [], 0.0)

    if task_name == "nuclei_scan":
        lines = [ln for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("stderr:")]
        valid = 0
        for line in lines:
            try:
                json.loads(line)
                valid += 1
            except json.JSONDecodeError:
                pass
        if valid == 0 and success and len(lines) >= 10:
            return WafVerdict("blocked_waf", None, ["nuclei_zero_findings_many_lines"], 0.3)
        return WafVerdict("unknown", None, [], 0.0)

    if task_name == "wpscan":
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return WafVerdict("unknown", None, [], 0.0)
        findings = data.get("interesting_findings") or []
        for f in findings:
            if isinstance(f, dict) and str(f.get("type", "")).lower() == "block_page":
                return WafVerdict("blocked_waf", "cloudflare", ["wpscan_block_page"], 0.5)
        return WafVerdict("unknown", None, [], 0.0)

    return WafVerdict("unknown", None, [], 0.0)


def secondary_signal_eligible_output(output: str) -> bool:
    """Single-target jobs: enough signal for 403-ratio heuristics."""
    return len([ln for ln in (output or "").splitlines() if ln.strip()]) >= 5
