"""Tests for DnstwistVariationGenerator (mocked dnstwist Fuzzer)."""

from unittest.mock import MagicMock, patch

import pytest


def test_invalid_fuzzers_filtered():
    from variation_generator import DnstwistVariationGenerator

    g = DnstwistVariationGenerator(fuzzers=["homoglyph", "not-a-real-fuzzer", "bitsquatting"])
    assert "not-a-real-fuzzer" not in g.fuzzers
    assert "homoglyph" in g.fuzzers
    assert "bitsquatting" in g.fuzzers


def test_generate_variations_invalid_domain_no_dot():
    from variation_generator import DnstwistVariationGenerator

    g = DnstwistVariationGenerator()
    if not g.dnstwist_available:
        pytest.skip("dnstwist not installed")
    assert g.generate_variations("nodot", "p") == {}


@patch("dnstwist.Fuzzer")
def test_add_protected_domain_mocked_fuzzer(mock_fuzzer_class):
    from variation_generator import DnstwistVariationGenerator

    inner = MagicMock()
    inner.generate = MagicMock()
    inner.permutations = MagicMock(
        return_value=[
            {"fuzzer": "*original", "domain": "example.com"},
            {"fuzzer": "bitsquatting", "domain": "example.com"},
            {"fuzzer": "insertion", "domain": "exammple.com"},
        ]
    )
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = False
    mock_fuzzer_class.return_value = mock_cm

    g = DnstwistVariationGenerator(fuzzers=["bitsquatting", "insertion"])
    added = g.add_protected_domain("example.com", "prog1", max_variations=100)
    assert added == 1
    info = g.match("exammple.com")
    assert info is not None
    assert info.protected_domain == "example.com"
    assert info.fuzzer == "insertion"
    assert info.program_name == "prog1"
    assert g.is_protected_domain("example.com") is True
    assert g.is_legitimate_subdomain("www.example.com") is True
    assert g.add_protected_domain("example.com", "prog1") == 0
    g.clear()
    assert g.get_variation_count() == 0
    stats = g.get_stats()
    assert stats["total_variations"] == 0
    assert stats["programs"] == 0
    assert "dnstwist_available" in stats
