"""CT asset monitoring: config builder asset states + certificate matcher integration."""

from unittest.mock import MagicMock, patch


def _program(name, program_id="11111111-1111-1111-1111-111111111111", **overrides):
    data = {
        "id": program_id,
        "name": name,
        "ct_monitoring_enabled": False,
        "ct_asset_monitoring_enabled": True,
        "scope_domains": [{"pattern": "*.example.com", "wildcard": True}],
        "out_of_scope_domains": [],
        "domain_regex": [],
        "out_of_scope_regex": [],
        "protected_domains": [],
        "protected_subdomain_prefixes": [],
    }
    data.update(overrides)
    return data


def test_build_asset_match_states_basic():
    from domain_config_builder import build_asset_match_states

    states = build_asset_match_states([("prog1", _program("prog1"))])
    assert "prog1" in states
    state = states["prog1"]
    assert state.program_id == "11111111-1111-1111-1111-111111111111"
    assert state.matcher.matches("api.example.com")
    assert not state.matcher.matches("api.other.com")


def test_build_asset_match_states_skips_without_id_or_rules():
    from domain_config_builder import build_asset_match_states

    no_id = _program("no-id", program_id="")
    no_rules = _program("no-rules", scope_domains=[])
    disabled = _program("disabled", ct_asset_monitoring_enabled=False)
    states = build_asset_match_states(
        [("no-id", no_id), ("no-rules", no_rules), ("disabled", disabled)]
    )
    assert states == {}


def test_asset_apex_index():
    from domain_config_builder import build_asset_apex_index, build_asset_match_states

    p1 = _program("prog1")
    p2 = _program(
        "prog2",
        program_id="22222222-2222-2222-2222-222222222222",
        scope_domains=[
            {"pattern": "*.example.com", "wildcard": True},
            {"pattern": "*.other.io", "wildcard": True},
        ],
    )
    states = build_asset_match_states([("prog1", p1), ("prog2", p2)])
    index = build_asset_apex_index(states)
    assert sorted(index["example.com"]) == ["prog1", "prog2"]
    assert index["other.io"] == ["prog2"]


def test_build_domain_config_asset_only_program_enables_ingestion():
    from domain_config_builder import build_domain_config_from_loaded

    bundle = build_domain_config_from_loaded([("prog1", _program("prog1"))])
    assert bundle.any_ct_enabled is True
    assert bundle.any_typosquat_enabled is False
    assert bundle.any_asset_enabled is True
    assert bundle.program_match_states == {}
    assert "prog1" in bundle.asset_match_states
    assert bundle.programs_asset_enabled_detail == [
        {"program_name": "prog1", "apex_roots": ["example.com"]}
    ]
    snap = bundle.matching_snapshot()
    assert snap.asset_candidate_programs("example.com") == ["prog1"]
    assert snap.asset_candidate_programs("unknown.com") == []
    assert snap.program_ids["prog1"] == "11111111-1111-1111-1111-111111111111"


def test_build_domain_config_no_programs_disables_ingestion():
    from domain_config_builder import build_domain_config_from_loaded

    disabled = _program("prog1", ct_asset_monitoring_enabled=False)
    bundle = build_domain_config_from_loaded([("prog1", disabled)])
    assert bundle.any_ct_enabled is False
    assert bundle.asset_match_states == {}


def _asset_snapshot(programs):
    from domain_config_builder import (
        MatchingSnapshot,
        build_asset_apex_index,
        build_asset_match_states,
    )
    from variation_generator import DnstwistVariationGenerator

    states = build_asset_match_states(programs)
    return MatchingSnapshot(
        variation_generator=DnstwistVariationGenerator(),
        program_match_states={},
        asset_match_states=states,
        asset_apex_index=build_asset_apex_index(states),
    )


def test_match_certificate_returns_asset_matches():
    from certificate_matcher import match_certificate_sync
    from models import CertificateInfo

    snap = _asset_snapshot([("prog1", _program("prog1"))])
    cert = CertificateInfo(
        domains=["api.example.com", "api.other.com"],
        issuer="O",
        issuer_cn="CN",
    )
    pending, count, _skipped, assets = match_certificate_sync(cert, snap)
    assert pending == []
    assert count == 0
    assert assets == [
        ("api.example.com", "prog1", "11111111-1111-1111-1111-111111111111")
    ]


def test_match_certificate_asset_respects_out_of_scope():
    from certificate_matcher import match_certificate_sync
    from models import CertificateInfo

    prog = _program(
        "prog1",
        out_of_scope_domains=[{"pattern": "*.dev.example.com", "wildcard": True}],
    )
    snap = _asset_snapshot([("prog1", prog)])
    cert = CertificateInfo(
        domains=["api.dev.example.com", "api.example.com"],
        issuer="O",
        issuer_cn="CN",
    )
    _pending, _count, _skipped, assets = match_certificate_sync(cert, snap)
    assert [a[0] for a in assets] == ["api.example.com"]


@patch("dnstwist.Fuzzer")
def test_match_certificate_collects_skip_logs(mock_fuzzer_class):
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import build_domain_config_from_loaded
    from models import CertificateInfo

    inner = MagicMock()
    inner.generate = MagicMock()
    inner.permutations = MagicMock(return_value=[])
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = False
    mock_fuzzer_class.return_value = mock_cm

    prog = _program(
        "prog1",
        ct_monitoring_enabled=True,
        ct_asset_monitoring_enabled=False,
        protected_domains=["example.com"],
    )
    snap = build_domain_config_from_loaded([("prog1", prog)]).matching_snapshot()
    cert = CertificateInfo(
        domains=["api.example.com", "example.com"],
        issuer="O",
        issuer_cn="CN",
        fingerprint="abc123",
        source="test-log",
    )

    pending, count, _skipped, _assets, logs = match_certificate_sync(
        cert, snap, collect_logs=True
    )

    assert pending == []
    assert count == 0
    assert {log["outcome"] for log in logs} == {
        "skipped_legitimate_subdomain",
        "skipped_protected_domain",
    }
    assert all(log["program_id"] == "11111111-1111-1111-1111-111111111111" for log in logs)
    assert all(log["details"]["certificate"]["fingerprint"] == "abc123" for log in logs)


def test_match_certificate_asset_wildcard_san_stripped():
    from certificate_matcher import match_certificate_sync
    from models import CertificateInfo

    snap = _asset_snapshot([("prog1", _program("prog1"))])
    # Wildcard CN (the consumer strips SAN wildcards, but CN can stay raw)
    cert = CertificateInfo(
        domains=["*.api.example.com"],
        issuer="O",
        issuer_cn="CN",
    )
    _pending, _count, _skipped, assets = match_certificate_sync(cert, snap)
    assert [a[0] for a in assets] == ["api.example.com"]


def test_match_certificate_asset_dedups_within_cert():
    from certificate_matcher import match_certificate_sync
    from models import CertificateInfo

    snap = _asset_snapshot([("prog1", _program("prog1"))])
    cert = CertificateInfo(
        domains=["api.example.com", "*.api.example.com", "API.EXAMPLE.COM"],
        issuer="O",
        issuer_cn="CN",
    )
    _pending, _count, _skipped, assets = match_certificate_sync(cert, snap)
    assert len(assets) == 1


@patch("dnstwist.Fuzzer")
def test_asset_matching_runs_despite_legitimate_subdomain_skip(mock_fuzzer_class):
    """Legit subdomains of protected domains are skipped for typosquat but
    must still be discovered as assets."""
    from certificate_matcher import match_certificate_sync
    from domain_config_builder import (
        MatchingSnapshot,
        build_asset_apex_index,
        build_asset_match_states,
    )
    from models import CertificateInfo
    from variation_generator import DnstwistVariationGenerator

    inner = MagicMock()
    inner.generate = MagicMock()
    inner.permutations = MagicMock(
        return_value=[{"fuzzer": "replacement", "domain": "examp1e.com"}]
    )
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = False
    mock_fuzzer_class.return_value = mock_cm

    vg = DnstwistVariationGenerator(fuzzers=["replacement"])
    vg.add_protected_domain("example.com", "prog1")
    assert vg.is_legitimate_subdomain("api.example.com")

    states = build_asset_match_states([("prog1", _program("prog1"))])
    snap = MatchingSnapshot(
        variation_generator=vg,
        program_match_states={},
        asset_match_states=states,
        asset_apex_index=build_asset_apex_index(states),
    )
    cert = CertificateInfo(domains=["api.example.com"], issuer="O", issuer_cn="CN")
    pending, count, _skipped, assets = match_certificate_sync(cert, snap)
    assert pending == []  # typosquat path skipped it
    assert [a[0] for a in assets] == ["api.example.com"]
