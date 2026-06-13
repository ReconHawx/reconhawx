"""Tests for CTMonitorService keyword/similarity matching helpers."""


def test_cert_metadata_details():
    from main import CTMonitorService
    from models import CertificateInfo

    cert = CertificateInfo(
        domains=["d.example.com"],
        issuer="Org",
        issuer_cn="ICN",
        fingerprint="ab",
        not_before="nb",
        seen_at="seen",
    )
    d = CTMonitorService._cert_metadata_details(cert)
    assert d["cert_issuer"] == "Org"
    assert d["cert_fingerprint"] == "ab"
    assert d["cert_not_before"] == "nb"
    assert d["cert_seen_at"] == "seen"
    assert d["cert_all_domains"] == ["d.example.com"]


def test_match_keyword_or_similarity_keyword():
    from certificate_matcher import _match_keyword_or_similarity
    from domain_config_builder import ProgramCTMatchState
    from models import CertificateInfo

    state = ProgramCTMatchState(
        keywords=["corpinternal"],
        similarity_threshold=0.99,
        protected_list=["example.com"],
    )
    cert = CertificateInfo(domains=[], issuer="O", issuer_cn="CN")
    m, skipped = _match_keyword_or_similarity("portal-corpinternal.evil.com", state, cert)
    assert skipped is False
    assert m is not None
    assert m.match_type == "keyword"
    assert m.matched is True


def test_match_keyword_or_similarity_protected_similarity():
    from certificate_matcher import _match_keyword_or_similarity
    from domain_config_builder import ProgramCTMatchState
    from models import CertificateInfo

    state = ProgramCTMatchState(
        keywords=[],
        similarity_threshold=0.85,
        protected_list=["example.com"],
    )
    cert = CertificateInfo(domains=[], issuer="O", issuer_cn="CN")
    m, skipped = _match_keyword_or_similarity("examp1e.com", state, cert)
    assert skipped is False
    assert m is not None
    assert m.match_type == "protected_similarity"
    assert m.protected_domain == "example.com"


def test_match_keyword_or_similarity_below_threshold():
    from certificate_matcher import _match_keyword_or_similarity
    from domain_config_builder import ProgramCTMatchState
    from models import CertificateInfo

    state = ProgramCTMatchState(
        keywords=[],
        similarity_threshold=0.99,
        protected_list=["example.com"],
    )
    cert = CertificateInfo(domains=[], issuer="O", issuer_cn="CN")
    m, skipped = _match_keyword_or_similarity("completely-unrelated-label.net", state, cert)
    assert m is None


def test_match_certificate_sync_counts_similarity_skipped():
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import ProgramCTMatchState
    from domain_config_builder import MatchingSnapshot
    from variation_generator import DnstwistVariationGenerator
    from models import CertificateInfo

    state = ProgramCTMatchState(
        keywords=[],
        similarity_threshold=0.85,
        protected_list=["example.com"],
        protected_collapsed_lengths=[len("examplecom")],
    )
    snap = MatchingSnapshot(
        variation_generator=DnstwistVariationGenerator(),
        program_match_states={"prog1": state},
    )
    cert = CertificateInfo(
        domains=["qwertyuiopasdfghjklzxcvbnmzzzzzzzzzzzzzzzz.net"],
        issuer="O",
        issuer_cn="CN",
    )
    pending, count, skipped, _assets = match_certificate_sync(cert, snap)
    assert count == 0
    assert pending == []
    assert skipped >= 1
