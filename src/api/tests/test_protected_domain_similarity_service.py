"""Unit tests for multi-view protected domain similarity (apex, collapsed, suffix scan)."""

import pytest

from app.services.protected_domain_similarity_service import (
    best_similarity_typo_to_protected,
    ProtectedDomainSimilarityService,
    _typo_suffix_hostnames,
)


def test_dot_split_brand_high_similarity():
    typo = "dcs-entre.prise.com"
    protected = "dcs-entreprise.com"
    # Collapsed forms match but FQDNs differ — capped below 100%
    assert best_similarity_typo_to_protected(typo, protected) == 0.99


def test_deep_benign_prefix_still_matches_tail():
    typo = "user.login.secure-access.dcs-entre.prise.com"
    protected = "dcs-entreprise.com"
    assert best_similarity_typo_to_protected(typo, protected) == 0.99


def test_apex_typo_regression_examp1e():
    assert best_similarity_typo_to_protected("examp1e.com", "example.com") >= 0.85


def test_literal_fqdn_match_is_full_similarity():
    assert best_similarity_typo_to_protected("dcs-entreprise.com", "dcs-entreprise.com") == 1.0
    assert best_similarity_typo_to_protected("dcs-Entreprise.COM.", "dcs-entreprise.com") == 1.0


def test_unrelated_domain_stays_low():
    sim = best_similarity_typo_to_protected(
        "foo.bar.totally-unrelated-site.xyz",
        "dcs-entreprise.com",
    )
    assert sim < 0.6


def test_calculate_similarities_sorts_and_prefers_brand_match():
    typo = "user.login.secure-access.dcs-entre.prise.com"
    protected = [
        "unrelated-corp.io",
        "dcs-entreprise.com",
        "other-brand.net",
    ]
    rows = ProtectedDomainSimilarityService.calculate_similarities_for_domain(typo, protected)
    assert rows[0]["protected_domain"] == "dcs-entreprise.com"
    assert rows[0]["similarity_percent"] == 99.0
    assert all("similarity_percent" in r for r in rows)


def test_typo_suffix_hostnames_multi_label():
    labels = _typo_suffix_hostnames("a.b.c.d.com")
    assert "a.b.c.d.com" in labels
    assert "d.com" in labels
    assert all(len(s.split(".")) >= 2 for s in labels)


def test_typo_suffix_single_label():
    assert _typo_suffix_hostnames("localhost") == ["localhost"]
