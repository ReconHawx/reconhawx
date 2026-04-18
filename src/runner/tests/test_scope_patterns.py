"""Tests for ``scope_patterns``."""

from __future__ import annotations

import pytest

from scope_patterns import (
    apex_from_pattern,
    discovery_target_from_scope_pattern,
    discovery_targets_from_scope,
    validate_scope_domain_entry,
)


def test_validate_scope_domain_entry_simple() -> None:
    pat, wc = validate_scope_domain_entry({"pattern": "example.com"})
    assert pat == "example.com"
    assert wc is False


def test_validate_scope_domain_entry_sets_wildcard_from_label() -> None:
    pat, wc = validate_scope_domain_entry({"pattern": "*.example.com"})
    assert pat == "*.example.com"
    assert wc is True


def test_validate_scope_domain_entry_honors_explicit_wildcard_flag() -> None:
    _, wc = validate_scope_domain_entry({"pattern": "example.com", "wildcard": True})
    assert wc is True


@pytest.mark.parametrize("entry", [None, {}, {"pattern": ""}, {"pattern": "bad..com"}, "not-dict"])
def test_validate_scope_domain_entry_rejects_invalid(entry) -> None:
    with pytest.raises((ValueError, TypeError)):
        validate_scope_domain_entry(entry)  # type: ignore[arg-type]


def test_apex_from_pattern_variants() -> None:
    assert apex_from_pattern("sub.example.com") == "example.com"
    assert apex_from_pattern("example.co.uk") == "example.co.uk"
    assert apex_from_pattern("*.api.example.com") == "example.com"
    assert apex_from_pattern("") == ""


def test_discovery_target_uses_suffix_after_last_wildcard() -> None:
    assert discovery_target_from_scope_pattern("api.*.dev.example.com") == "dev.example.com"
    assert discovery_target_from_scope_pattern("*.example.com") == "example.com"
    assert discovery_target_from_scope_pattern("example.com") == "example.com"


def test_discovery_targets_from_scope_dedupes_and_sorts() -> None:
    targets = discovery_targets_from_scope(
        scope_domains=[
            {"pattern": "a.example.com"},
            {"pattern": "*.api.example.com"},
            {"pattern": "b.example.com"},
        ],
        domain_regex=[r"^foo\.com$"],
    )
    assert targets == sorted(set(targets))
    assert "example.com" in targets
    assert "foo.com" in targets


def test_discovery_targets_wildcard_only_filter() -> None:
    targets = discovery_targets_from_scope(
        scope_domains=[
            {"pattern": "example.com"},
            {"pattern": "*.wild.com"},
        ],
        domain_regex=None,
        filter_mode="wildcard_only",
    )
    assert "wild.com" in targets
    assert "example.com" not in targets


def test_discovery_targets_non_wildcard_only_filter() -> None:
    targets = discovery_targets_from_scope(
        scope_domains=[
            {"pattern": "example.com"},
            {"pattern": "*.wild.com"},
        ],
        domain_regex=None,
        filter_mode="non_wildcard_only",
    )
    assert "example.com" in targets
    assert "wild.com" not in targets
