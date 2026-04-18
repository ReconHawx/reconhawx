"""Tests for pure helpers in ``batch_jobs.ai_analysis_batch``."""

from __future__ import annotations

import pytest

from batch_jobs.ai_analysis_batch import (
    _build_finding_context,
    _extract_json,
    _normalize_result,
)


def test_extract_json_direct() -> None:
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_fenced() -> None:
    text = "prefix\n```json\n{\"threat_level\": \"high\"}\n```\nsuffix"
    assert _extract_json(text) == {"threat_level": "high"}


def test_extract_json_from_brace_scan() -> None:
    text = "Some text before {\n  \"key\": \"val\"\n} trailing"
    assert _extract_json(text) == {"key": "val"}


def test_extract_json_returns_none_for_garbage() -> None:
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


def test_normalize_result_clamps_confidence_and_levels() -> None:
    out = _normalize_result({"threat_level": "xyz", "confidence": 150, "summary": "s"})
    assert out["threat_level"] == "low"
    assert out["confidence"] == 100

    out = _normalize_result({"threat_level": "high", "confidence": -5})
    assert out["confidence"] == 0


def test_normalize_result_uses_model_override() -> None:
    out = _normalize_result({"threat_level": "medium"}, model_override="llama3")
    assert out["model"] == "llama3"
    assert out["recommended_action"] == "monitoring"


def test_normalize_result_truncates_summary_and_reasoning() -> None:
    long_summary = "x" * 2000
    long_reasoning = "y" * 5000
    out = _normalize_result({"summary": long_summary, "reasoning": long_reasoning})
    assert len(out["summary"]) == 1000
    assert len(out["reasoning"]) == 2000


def test_build_finding_context_includes_core_sections() -> None:
    finding = {
        "typo_domain": "exarnple.com",
        "source": "bruteforce",
        "timestamp": "2024-01-01",
        "dns_a_records": ["1.1.1.1"],
        "whois_registrar": "Test Registrar",
        "protected_domain_similarities": [
            {"protected_domain": "example.com", "similarity_percent": 92}
        ],
    }
    urls = [{"url": "https://exarnple.com", "http_status_code": 200, "title": "Login"}]
    shots = [{"url": "https://exarnple.com", "extracted_text": "Please log in"}]

    ctx = _build_finding_context(finding, urls, shots)
    assert "exarnple.com" in ctx
    assert "Test Registrar" in ctx
    assert "example.com" in ctx
    assert "Login" in ctx
    assert "Please log in" in ctx
