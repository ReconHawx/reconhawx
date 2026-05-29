"""Tests for TLD duplication of typosquat variation domains."""

from __future__ import annotations

from recon_tasks.typosquat_components import expand_variations_with_duplicate_tlds


def test_empty_duplicate_tlds_unchanged() -> None:
    base = {"d0main.com": ["insertion"], "domaln.com": ["replacement"]}
    assert expand_variations_with_duplicate_tlds(base, []) == base


def test_example_from_plan_org_and_live() -> None:
    base = {
        "d0main.com": ["insertion"],
        "domaln.com": ["replacement"],
    }
    result = expand_variations_with_duplicate_tlds(base, ["org", "live"])
    assert set(result.keys()) == {
        "d0main.com",
        "domaln.com",
        "d0main.org",
        "domaln.org",
        "d0main.live",
        "domaln.live",
    }
    assert result["d0main.com"] == ["insertion"]
    assert result["domaln.com"] == ["replacement"]
    assert result["d0main.org"] == ["insertion"]
    assert result["domaln.live"] == ["replacement"]


def test_tld_normalization_strips_dot_and_lowercases() -> None:
    base = {"foo.com": ["homoglyph"]}
    result = expand_variations_with_duplicate_tlds(base, [".ORG", " LIVE "])
    assert "foo.org" in result
    assert "foo.live" in result
    assert result["foo.org"] == ["homoglyph"]


def test_skip_when_duplicate_tld_matches_existing_domain() -> None:
    base = {"d0main.com": ["insertion"]}
    result = expand_variations_with_duplicate_tlds(base, ["com"])
    assert result == {"d0main.com": ["insertion"]}


def test_merge_fuzzers_when_candidate_already_exists() -> None:
    base = {
        "d0main.com": ["insertion"],
        "d0main.org": ["various"],
    }
    result = expand_variations_with_duplicate_tlds(base, ["org"])
    assert result["d0main.org"] == ["various", "insertion"]


def test_invalid_domain_without_dot_skipped() -> None:
    base = {"nodot": ["insertion"], "valid.com": ["replacement"]}
    result = expand_variations_with_duplicate_tlds(base, ["net"])
    assert "nodot" in result
    assert "nodot.net" not in result
    assert "valid.net" in result
    assert result["valid.net"] == ["replacement"]


def test_co_uk_public_suffix_not_split_on_last_dot() -> None:
    base = {"d0main.domain.co.uk": ["insertion"]}
    result = expand_variations_with_duplicate_tlds(base, ["org"])
    assert "d0main.domain.org" in result
    assert "d0main.domain.co.org" not in result
    assert result["d0main.domain.org"] == ["insertion"]


def test_co_uk_subdomain_variation() -> None:
    base = {"www.example.co.uk": ["homoglyph"]}
    result = expand_variations_with_duplicate_tlds(base, ["net"])
    assert "www.example.net" in result
    assert "www.example.co.net" not in result
