"""Unit tests for nuclei precheck / heavy-output WAF classification."""

from __future__ import annotations

import json

from services import waf_detection


def test_classify_precheck_blocked_line() -> None:
    line = json.dumps(
        {
            "template-id": "waf-precheck-unified",
            "host": "x",
            "matched-at": "https://x/",
        }
    )
    v = waf_detection.classify_precheck_output(line + "\n")
    assert v.verdict == "blocked_waf"
    assert v.vendor is None


def test_classify_precheck_unified_via_path_fallback() -> None:
    """Path-based match when nuclei emits template path instead of template-id."""
    line = json.dumps(
        {
            "template-id": "",
            "template": "/something/waf-precheck-unified.yaml",
            "matched-at": "https://x/",
        }
    )
    v = waf_detection.classify_precheck_output(line + "\n")
    assert v.verdict == "blocked_waf"
    assert v.vendor is None


def test_classify_precheck_empty_accessible(monkeypatch) -> None:
    monkeypatch.delenv("WAF_DETECTION", raising=False)
    v = waf_detection.classify_precheck_output("")
    assert v.verdict == "accessible"


def test_waf_detection_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("WAF_DETECTION", "off")
    line = json.dumps({"template-id": "waf-precheck-unified"})
    assert waf_detection.classify_precheck_output(line).verdict == "unknown"
    assert waf_detection.classify_heavy_output("test_http", "{}", success=True).confidence == 0.0


def test_build_precheck_command() -> None:
    cmd = waf_detection.build_waf_precheck_command("https://a.example")
    assert "nuclei" in cmd and "waf-precheck-unified.yaml" in cmd


def test_httpx_403_ratio_blocked() -> None:
    rows = [{"status_code": 403}] * 8 + [{"status_code": 200}] * 2
    blob = "\n".join(json.dumps(r) for r in rows)
    v = waf_detection.classify_heavy_output("test_http", blob, success=True)
    assert v.verdict == "blocked_waf"
