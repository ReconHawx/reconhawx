"""End-to-end certificate matcher tests for TLD-agnostic variations and keywords."""

from unittest.mock import patch

from domain_config_builder import MatchingSnapshot, ProgramCTMatchState
from models import CertificateInfo
from variation_generator import DnstwistVariationGenerator


@patch("dnstwist.Fuzzer")
def test_match_certificate_cross_tld_variation(mock_fuzzer_class):
    from certificate_matcher import match_certificate_sync
    from unittest.mock import MagicMock

    inner = MagicMock()
    inner.generate = MagicMock()
    inner.permutations = MagicMock(
        return_value=[
            {"fuzzer": "*original", "domain": "domain.com"},
            {"fuzzer": "replacement", "domain": "d0main.com"},
        ]
    )
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = False
    mock_fuzzer_class.return_value = mock_cm

    vg = DnstwistVariationGenerator(fuzzers=["replacement"])
    vg.add_protected_domain("domain.com", "prog1")

    snap = MatchingSnapshot(
        variation_generator=vg,
        program_match_states={},
    )
    cert = CertificateInfo(
        domains=["d0main.live"],
        issuer="O",
        issuer_cn="CN",
    )
    pending, count = match_certificate_sync(cert, snap)
    assert count == 1
    assert len(pending) == 1
    match, program = pending[0]
    assert program == "prog1"
    assert match.match_type == "dnstwist:replacement"
    assert match.cert_domain == "d0main.live"
    assert match.protected_domain == "domain.com"


@patch("dnstwist.Fuzzer")
def test_match_certificate_prefix_does_not_match_variation(mock_fuzzer_class):
    from certificate_matcher import match_certificate_sync
    from unittest.mock import MagicMock

    inner = MagicMock()
    inner.generate = MagicMock()
    inner.permutations = MagicMock(
        return_value=[
            {"fuzzer": "replacement", "domain": "d0main.com"},
        ]
    )
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = False
    mock_fuzzer_class.return_value = mock_cm

    vg = DnstwistVariationGenerator(fuzzers=["replacement"])
    vg.add_protected_domain("domain.com", "prog1")

    snap = MatchingSnapshot(
        variation_generator=vg,
        program_match_states={},
    )
    cert = CertificateInfo(domains=["my-d0main.net"], issuer="O", issuer_cn="CN")
    pending, count = match_certificate_sync(cert, snap)
    assert count == 0
    assert pending == []


def test_match_certificate_keyword_with_typo_label():
    from certificate_matcher import match_certificate_sync

    vg = DnstwistVariationGenerator()
    state = ProgramCTMatchState(
        keywords=["production"],
        similarity_threshold=0.99,
        protected_list=["domain.com"],
    )
    snap = MatchingSnapshot(
        variation_generator=vg,
        program_match_states={"prog1": state},
    )
    cert = CertificateInfo(
        domains=["production-d0main.live"],
        issuer="O",
        issuer_cn="CN",
    )
    pending, count = match_certificate_sync(cert, snap)
    assert count == 1
    match, program = pending[0]
    assert program == "prog1"
    assert match.match_type == "keyword"
    assert match.protected_domain == "production"
