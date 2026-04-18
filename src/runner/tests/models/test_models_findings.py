"""Tests for ``models.findings``."""

from __future__ import annotations

from models.findings import NucleiFinding, TyposquatDomain


def test_nuclei_finding_requires_core_fields() -> None:
    f = NucleiFinding(template_id="t-1", name="Test", severity="low", type="http")
    assert f.template_id == "t-1"
    assert f.tags == []
    assert f.extracted_results == []


def test_typosquat_domain_defaults() -> None:
    d = TyposquatDomain(typo_domain="exarnple.com")
    assert d.typo_domain == "exarnple.com"
    assert d.fuzzers == []
    assert d.domain_registered is None


def test_typosquat_domain_accepts_normalized_fields() -> None:
    d = TyposquatDomain(
        typo_domain="exarnple.com",
        fuzzers=["homoglyph"],
        domain_registered=True,
        dns_a_records=["1.2.3.4"],
        is_wildcard=False,
    )
    assert d.domain_registered is True
    assert d.dns_a_records == ["1.2.3.4"]
