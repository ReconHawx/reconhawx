"""Unit tests for bulk_sql.scope (no database)."""

import pytest

from repository.bulk_sql.scope import domain_in_scope


def test_in_scope_requires_match():
    assert domain_in_scope("sub.example.com", [r".*\.example\.com"], []) is True


def test_out_of_scope_regex_wins():
    assert (
        domain_in_scope(
            "sub.example.com",
            [r".*\.example\.com"],
            [r"^sub\.example\.com$"],
        )
        is False
    )


def test_no_in_scope_pattern():
    assert domain_in_scope("other.com", [r".*\.example\.com"], []) is False


def test_empty_hostname():
    assert domain_in_scope("", [r".*"], []) is False


def test_structured_in_scope_bulk_helper():
    assert domain_in_scope(
        "x.example.com",
        [],
        [],
        [{"pattern": "*.example.com", "wildcard": True}],
        [],
    ) is True


def test_structured_plus_legacy():
    assert domain_in_scope(
        "sub.example.com",
        [r"^nomatch$"],
        [],
        [{"pattern": "example.com", "wildcard": True}],
        [],
    ) is True
