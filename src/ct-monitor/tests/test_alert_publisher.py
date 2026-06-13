"""Tests for CTAlertPublisher priority and disconnected publish."""

import pytest


@pytest.mark.parametrize(
    "match_type,score,expected",
    [
        ("homoglyph", 0.1, "critical"),
        ("tld_swap", 0.1, "high"),
        ("keyword", 0.96, "high"),
        ("protected_similarity", 0.95, "high"),
        ("protected_similarity", 0.9, "medium"),
        ("protected_similarity", 0.84, "low"),
    ],
)
def test_calculate_priority(match_type, score, expected):
    from alert_publisher import CTAlertPublisher
    from models import MatchResult

    pub = CTAlertPublisher()
    mr = MatchResult(
        matched=True,
        protected_domain="example.com",
        cert_domain="x.com",
        similarity_score=score,
        match_type=match_type,
        details={},
    )
    assert pub._calculate_priority(mr) == expected


@pytest.mark.asyncio
async def test_publish_alert_not_connected():
    from alert_publisher import CTAlertPublisher
    from models import CertificateInfo, MatchResult

    pub = CTAlertPublisher()
    mr = MatchResult(
        matched=True,
        protected_domain="example.com",
        cert_domain="bad.com",
        similarity_score=0.9,
        match_type="keyword",
        details={},
    )
    cert = CertificateInfo(domains=["bad.com"], issuer="O", issuer_cn="CN")
    ok = await pub.publish_alert(mr, cert, "prog")
    assert ok is False


@pytest.mark.asyncio
async def test_publish_asset_discovered_not_connected():
    from alert_publisher import CTAlertPublisher

    pub = CTAlertPublisher()
    ok = await pub.publish_asset_discovered("prog", "uuid", "api.example.com")
    assert ok is False


@pytest.mark.asyncio
async def test_publish_asset_discovered_payload(monkeypatch):
    import json

    from alert_publisher import CTAlertPublisher

    published = []

    class _FakeAck:
        seq = 42

    class _FakeJS:
        async def publish(self, subject, data, headers=None, timeout=None):
            published.append(
                {
                    "subject": subject,
                    "payload": json.loads(data.decode()),
                    "headers": headers,
                }
            )
            return _FakeAck()

    pub = CTAlertPublisher()
    pub._js = _FakeJS()
    pub._connected = True

    ok = await pub.publish_asset_discovered(
        "my-program",
        "11111111-1111-1111-1111-111111111111",
        "api.example.com",
    )
    assert ok is True
    assert len(published) == 1
    assert published[0]["subject"] == "events.assets.ct_subdomain.discovered"
    payload = published[0]["payload"]
    assert payload["program_name"] == "my-program"
    assert payload["program_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["name"] == "api.example.com"
    assert payload["source"] == "ct_monitoring"
    assert payload["domain_list_array"] == ["api.example.com"]
