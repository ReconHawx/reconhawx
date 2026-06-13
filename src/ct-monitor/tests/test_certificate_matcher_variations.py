"""End-to-end certificate matcher tests for TLD-agnostic variations and keywords."""

from unittest.mock import patch


@patch("dnstwist.Fuzzer")
def test_match_certificate_cross_tld_variation(mock_fuzzer_class):
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import MatchingSnapshot
    from models import CertificateInfo
    from unittest.mock import MagicMock
    from variation_generator import DnstwistVariationGenerator

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
    pending, count, _skipped, _assets = match_certificate_sync(cert, snap)
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
    from domain_config_builder import MatchingSnapshot
    from models import CertificateInfo
    from unittest.mock import MagicMock
    from variation_generator import DnstwistVariationGenerator

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
    pending, count, _skipped, _assets = match_certificate_sync(cert, snap)
    assert count == 0
    assert pending == []


def test_match_certificate_keyword_with_typo_label():
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import MatchingSnapshot, ProgramCTMatchState
    from models import CertificateInfo
    from variation_generator import DnstwistVariationGenerator

    vg = DnstwistVariationGenerator()
    state = ProgramCTMatchState(
        keywords=["production"],
        similarity_threshold=0.99,
        protected_list=["domain.com"],
        protected_collapsed_lengths=[len("domaincom")],
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
    pending, count, _skipped, _assets = match_certificate_sync(cert, snap)
    assert count == 1
    match, program = pending[0]
    assert program == "prog1"
    assert match.match_type == "keyword"
    assert match.protected_domain == "production"


def test_keyword_automaton_finds_all_keywords():
    from domain_config_builder import (
        MatchingSnapshot,
        ProgramCTMatchState,
        build_keyword_automaton,
    )
    from variation_generator import DnstwistVariationGenerator

    states = {
        "prog1": ProgramCTMatchState(
            keywords=["production", "vpn"],
            similarity_threshold=0.99,
            protected_list=[],
        ),
        "prog2": ProgramCTMatchState(
            keywords=["corp"],
            similarity_threshold=0.99,
            protected_list=[],
        ),
    }
    automaton = build_keyword_automaton(states)
    assert automaton is not None
    snap = MatchingSnapshot(
        variation_generator=DnstwistVariationGenerator(),
        program_match_states=states,
        keyword_automaton=automaton,
    )
    assert snap.find_keywords("production-corp-vpn.example.com") == {
        "production",
        "vpn",
        "corp",
    }
    assert snap.find_keywords("nothing.example.com") == set()
    # No automaton -> None signals substring fallback.
    no_auto = MatchingSnapshot(
        variation_generator=DnstwistVariationGenerator(),
        program_match_states=states,
    )
    assert no_auto.find_keywords("production.example.com") is None


def test_match_certificate_keyword_via_automaton_first_program_wins():
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import (
        MatchingSnapshot,
        ProgramCTMatchState,
        build_keyword_automaton,
    )
    from models import CertificateInfo
    from variation_generator import DnstwistVariationGenerator

    states = {
        "prog1": ProgramCTMatchState(
            keywords=["internal", "corp"],
            similarity_threshold=0.99,
            protected_list=[],
        ),
        "prog2": ProgramCTMatchState(
            keywords=["corp"],
            similarity_threshold=0.99,
            protected_list=[],
        ),
    }
    snap = MatchingSnapshot(
        variation_generator=DnstwistVariationGenerator(),
        program_match_states=states,
        keyword_automaton=build_keyword_automaton(states),
    )
    cert = CertificateInfo(
        domains=["corp-login.evil.net"],
        issuer="O",
        issuer_cn="CN",
    )
    pending, count, _skipped, _assets = match_certificate_sync(cert, snap)
    assert count == 1
    match, program = pending[0]
    assert program == "prog1"
    assert match.match_type == "keyword"
    assert match.protected_domain == "corp"


def test_program_match_state_derives_prepared_data():
    from domain_config_builder import ProgramCTMatchState
    from protected_domain_similarity import (
        _collapse_hostname_alphanumeric,
        prepare_protected,
    )

    state = ProgramCTMatchState(
        keywords=[],
        similarity_threshold=0.85,
        protected_list=["example.com", "dcs-entreprise.com"],
    )
    assert [p.domain for p in state.protected_prepared] == [
        "example.com",
        "dcs-entreprise.com",
    ]
    assert state.protected_prepared[0] == prepare_protected("example.com")
    assert state.protected_collapsed_lengths == [
        len(_collapse_hostname_alphanumeric("example.com")),
        len(_collapse_hostname_alphanumeric("dcs-entreprise.com")),
    ]
