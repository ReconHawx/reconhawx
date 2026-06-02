"""Tests for pure helpers in ``recon_tasks.typosquat_components``."""

from __future__ import annotations

import pytest

from recon_tasks.typosquat_components import (
    TyposquatAnalyzer,
    _calculate_domain_similarity,
    _decode_gowitness_filename_to_url,
    _extract_apex_domain,
    _levenshtein_distance,
    _levenshtein_similarity,
    is_protected_domain_seed,
)


def test_levenshtein_distance_basic() -> None:
    assert _levenshtein_distance("kitten", "sitting") == 3
    assert _levenshtein_distance("", "abc") == 3
    assert _levenshtein_distance("abc", "abc") == 0


def test_levenshtein_similarity_bounds() -> None:
    assert _levenshtein_similarity("abc", "abc") == 1.0
    assert _levenshtein_similarity("", "") == 1.0
    sim = _levenshtein_similarity("example", "exampel")
    assert 0 < sim < 1


def test_extract_apex_domain() -> None:
    assert _extract_apex_domain("WWW.Example.com") == "example.com"
    assert _extract_apex_domain("deep.sub.example.com") == "example.com"
    assert _extract_apex_domain("example") == "example"


def test_is_protected_domain_seed_apex_match() -> None:
    protected = ["brand.com", "other.org"]
    assert is_protected_domain_seed("brand.com", protected) is True
    assert is_protected_domain_seed("www.brand.com", protected) is True
    assert is_protected_domain_seed("other.org", protected) is True
    assert is_protected_domain_seed("unrelated.net", protected) is False
    assert is_protected_domain_seed("", protected) is False
    assert is_protected_domain_seed("brand.com", []) is False


def test_calculate_domain_similarity_no_protected_domains() -> None:
    sim, matched, pct = _calculate_domain_similarity("example.com", [])
    assert sim == 0.0 and matched is None and pct == 0.0


def test_calculate_domain_similarity_picks_best_match() -> None:
    sim, matched, pct = _calculate_domain_similarity(
        "exampel.com",
        ["example.com", "other.org"],
    )
    assert matched == "example.com"
    assert 0.8 < sim <= 1.0
    assert 0 < pct <= 100


def test_decode_gowitness_filename_rejects_non_png() -> None:
    assert _decode_gowitness_filename_to_url("foo.jpg") is None
    assert _decode_gowitness_filename_to_url("") is None


def test_decode_gowitness_filename_roundtrip() -> None:
    # screenshotter.sh writes :// -> --- and / -> ---
    url = _decode_gowitness_filename_to_url("https---example.com-443.png")
    assert url is not None
    assert url.startswith("https://example.com")
    assert "443" in url


@pytest.fixture
def analyzer(monkeypatch) -> TyposquatAnalyzer:
    monkeypatch.setenv("PROGRAM_NAME", "unit")
    return TyposquatAnalyzer()


def test_detect_parked_domain_clean(analyzer: TyposquatAnalyzer) -> None:
    is_parked, reasons, score = analyzer.detect_parked_domain(
        nameservers=["ns1.cloudflare.com"],
        mx_servers=["10 mail.example.com."],
        a_records=["8.8.8.8"],
        http_title="Welcome",
        http_body="<html>normal content</html>" * 50,
        domain="example.com",
    )
    assert is_parked is False
    assert score == 0


def test_detect_parked_domain_nameserver_match(analyzer: TyposquatAnalyzer) -> None:
    is_parked, reasons, score = analyzer.detect_parked_domain(
        nameservers=["ns1.sedoparking.com"],
        mx_servers=[],
        a_records=[],
        http_title=None,
        http_body=None,
        domain="sketchy.com",
    )
    assert is_parked is True
    assert reasons["nameserver_matches"] == ["ns1.sedoparking.com"]
    assert score >= 25


def test_detect_parked_domain_a_record_match(analyzer: TyposquatAnalyzer) -> None:
    # 185.53.176.x is in ParkingCrew 185.53.176.0/22.
    is_parked, reasons, score = analyzer.detect_parked_domain(
        nameservers=[],
        mx_servers=[],
        a_records=["185.53.176.7"],
        http_title=None,
        http_body=None,
        domain="sketchy.com",
    )
    assert is_parked is True
    assert reasons["a_matches"]
    assert score >= 40


def test_detect_parked_domain_title_and_body_keywords(analyzer: TyposquatAnalyzer) -> None:
    is_parked, reasons, score = analyzer.detect_parked_domain(
        nameservers=[],
        mx_servers=[],
        a_records=[],
        http_title="Domain Parking",
        http_body="this domain is parked",
        domain="sketchy.com",
    )
    assert is_parked is True
    # minimal_content also triggers because body is short.
    assert reasons.get("title_keywords")
    assert reasons.get("body_keywords")


def test_parse_worker_output_sets_bypass_for_protected_seed(analyzer: TyposquatAnalyzer, monkeypatch) -> None:
    import json

    from recon_tasks.base import FindingType

    monkeypatch.setattr(
        analyzer,
        "_get_program_protected_domains",
        lambda program_name: ["brand.com"],
    )

    worker_line = json.dumps(
        {
            "typo_domain": "br4nd.com",
            "original_domain": "brand.com",
            "fuzzers": ["replacement"],
            "info": {
                "registered": True,
                "dns_a": ["1.2.3.4"],
            },
            "typosquat_urls": [{"url": "http://br4nd.com/"}],
        }
    )

    result, _, _, _ = analyzer.parse_worker_output(
        worker_line, {"analyze_input_as_variations": False}
    )

    findings = result[FindingType.TYPOSQUAT_DOMAIN]
    assert len(findings) == 1
    assert findings[0]["ignore_typosquat_filtering"] is True

    urls = result[FindingType.TYPOSQUAT_URL]
    assert len(urls) == 1
    assert urls[0]["ignore_typosquat_filtering"] is True
