"""Tests for ct-monitor dataclasses and serialization."""

from datetime import datetime, timezone
from unittest.mock import patch


def test_certificate_info_to_dict_roundtrip_keys():
    from models import CertificateInfo

    c = CertificateInfo(
        domains=["a.example.com", "b.example.com"],
        issuer="O",
        issuer_cn="CN",
        not_before="nb",
        not_after="na",
        fingerprint="fp",
        serial_number="sn",
        source="src",
        cert_index=1,
        seen_at="seen",
        update_type="upd",
    )
    d = c.to_dict()
    assert d["domains"] == ["a.example.com", "b.example.com"]
    assert d["issuer"] == "O"
    assert d["issuer_cn"] == "CN"
    assert d["not_before"] == "nb"
    assert d["not_after"] == "na"
    assert d["fingerprint"] == "fp"
    assert d["serial_number"] == "sn"
    assert d["source"] == "src"
    assert d["cert_index"] == 1
    assert d["seen_at"] == "seen"
    assert d["update_type"] == "upd"


def test_match_result_to_dict():
    from models import MatchResult

    m = MatchResult(
        matched=True,
        protected_domain="example.com",
        cert_domain="examp1e.com",
        similarity_score=0.91,
        match_type="protected_similarity",
        details={"k": "v"},
    )
    d = m.to_dict()
    assert d["matched"] is True
    assert d["protected_domain"] == "example.com"
    assert d["cert_domain"] == "examp1e.com"
    assert d["similarity_score"] == 0.91
    assert d["match_type"] == "protected_similarity"
    assert d["details"] == {"k": "v"}


def test_ct_alert_to_dict_defaults():
    from models import CTAlert

    a = CTAlert(program_name="p1", protected_domain="ex.com", detected_domain="ex.co")
    d = a.to_dict()
    assert d["event_type"] == "ct_typosquat_detected"
    assert d["program_name"] == "p1"
    assert d["protected_domain"] == "ex.com"
    assert d["detected_domain"] == "ex.co"
    assert d["source"] == "ct_monitor"
    assert d["priority"] == "medium"
    assert d["auto_analyze"] is True
    assert "timestamp" in d


def test_processing_stats_to_dict_zero_runtime_rate():
    from models import ProcessingStats

    base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    with patch("models._utcnow", return_value=base):
        s = ProcessingStats(start_time=base, total_received=99)
        d = s.to_dict()
    assert d["total_received"] == 99
    assert d["runtime_seconds"] == 0
    assert d["certs_per_second"] == 0


def test_processing_stats_to_dict_nonzero_rate():
    from models import ProcessingStats

    start = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    end = datetime(2024, 6, 1, 12, 0, 10, tzinfo=timezone.utc).replace(tzinfo=None)
    with patch("models._utcnow", return_value=end):
        s = ProcessingStats(start_time=start, total_received=100)
        d = s.to_dict()
    assert d["runtime_seconds"] == 10
    assert d["certs_per_second"] == 10.0


def test_processing_stats_offered_processed_drop_rates():
    from models import ProcessingStats

    start = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    end = datetime(2024, 6, 1, 12, 0, 10, tzinfo=timezone.utc).replace(tzinfo=None)
    with patch("models._utcnow", return_value=end):
        s = ProcessingStats(
            start_time=start,
            total_received=80,
            processed=50,
            queue_drops=20,
        )
        d = s.to_dict(match_in_flight=2, match_concurrency=4, service_similarity_skipped=99)
    assert d["offered_per_second"] == 10.0
    assert d["processed_per_second"] == 5.0
    assert d["drop_rate"] == 0.2
    assert d["match_in_flight"] == 2
    assert d["match_concurrency"] == 4
    assert d["similarity_skipped"] == 99
