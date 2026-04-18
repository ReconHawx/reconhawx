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
