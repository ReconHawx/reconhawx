"""Unit tests for utils.scope_patterns."""

from utils.scope_patterns import (
    discovery_targets_from_scope,
    is_domain_in_scope_structured_and_legacy,
    validate_scope_domain_entry,
)


def test_validate_scope_star_forces_wildcard():
    p, w = validate_scope_domain_entry({"pattern": "*.example.com", "wildcard": False})
    assert p == "*.example.com"
    assert w is True


def test_in_scope_structured_exact():
    assert (
        is_domain_in_scope_structured_and_legacy(
            "api.example.com",
            [{"pattern": "api.example.com", "wildcard": False}],
            [],
            [],
            [],
        )
        is True
    )


def test_in_scope_structured_wildcard_apex():
    assert (
        is_domain_in_scope_structured_and_legacy(
            "sub.example.com",
            [{"pattern": "example.com", "wildcard": True}],
            [],
            [],
            [],
        )
        is True
    )


def test_in_scope_structured_leading_star():
    assert (
        is_domain_in_scope_structured_and_legacy(
            "a.b.example.com",
            [{"pattern": "*.example.com", "wildcard": True}],
            [],
            [],
            [],
        )
        is True
    )


def test_out_of_scope_structured_wins():
    assert (
        is_domain_in_scope_structured_and_legacy(
            "dev.api.example.com",
            [{"pattern": "*.example.com", "wildcard": True}],
            [{"pattern": "dev.*.example.com", "wildcard": True}],
            [],
            [],
        )
        is False
    )


def test_legacy_regex_still_used():
    assert (
        is_domain_in_scope_structured_and_legacy(
            "sub.example.com",
            [],
            [],
            [r".*\.example\.com"],
            [],
        )
        is True
    )


def test_discovery_targets_filter_wildcard_only():
    t = discovery_targets_from_scope(
        [
            {"pattern": "example.com", "wildcard": True},
            {"pattern": "*.other.com", "wildcard": True},
            {"pattern": "fixed.third.com", "wildcard": False},
        ],
        [],
        "wildcard_only",
    )
    assert "example.com" in t
    assert "other.com" in t
    assert "third.com" not in t


def test_discovery_targets_wildcard_suffix_after_last_star():
    """Internal * zones: use suffix after last *, not apex_from_pattern only."""
    t = discovery_targets_from_scope(
        [
            {"pattern": "*.h3x.it", "wildcard": True},
            {"pattern": "h3xit.io", "wildcard": False},
            {"pattern": "api.*.dev.h3x.it", "wildcard": True},
        ],
        [],
        "wildcard_only",
    )
    assert "h3x.it" in t
    assert "dev.h3x.it" in t
    assert len(t) == 2
    assert "h3xit.io" not in t
