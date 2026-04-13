"""Unit tests for typosquat insertion filtering (including whitelisted apex domains)."""

import pytest

from app.services.typosquat_filtering_service import TyposquatFilteringService


def test_normalize_whitelisted_apex_domains_dedupes_and_extracts_apex():
    assert TyposquatFilteringService.normalize_whitelisted_apex_domains(
        ["Sub.Partner.COM", "partner.com", "", "  ", 123]
    ) == ["partner.com"]


def test_normalize_whitelisted_apex_domains_empty():
    assert TyposquatFilteringService.normalize_whitelisted_apex_domains([]) == []
    assert TyposquatFilteringService.normalize_whitelisted_apex_domains(None) == []


def test_filtering_disabled_ignores_whitelist():
    passes, reason = TyposquatFilteringService.should_insert_domain(
        "app.partner.com",
        protected_domains=["brand.com"],
        protected_subdomain_prefixes=[],
        filtering_settings={
            "enabled": False,
            "whitelisted_apex_domains": ["partner.com"],
        },
    )
    assert passes is True
    assert reason == "filtering_disabled"


def test_whitelist_filters_subdomain_when_filtering_enabled():
    passes, reason = TyposquatFilteringService.should_insert_domain(
        "app.partner.com",
        protected_domains=["brand.com"],
        protected_subdomain_prefixes=[],
        filtering_settings={
            "enabled": True,
            "min_similarity_percent": 60.0,
            "whitelisted_apex_domains": ["partner.com"],
        },
    )
    assert passes is False
    assert reason == "whitelisted_apex:partner.com"


def test_whitelist_accepts_paste_of_subdomain_entry():
    """User may paste sub.partner.com; stored/compare as registrable apex."""
    passes, reason = TyposquatFilteringService.should_insert_domain(
        "foo.partner.com",
        protected_domains=["brand.com"],
        protected_subdomain_prefixes=[],
        filtering_settings={
            "enabled": True,
            "min_similarity_percent": 60.0,
            "whitelisted_apex_domains": ["sub.partner.com"],
        },
    )
    assert passes is False
    assert reason == "whitelisted_apex:partner.com"


def test_whitelist_miss_continues_to_similarity():
    passes, reason = TyposquatFilteringService.should_insert_domain(
        "examp1e.com",
        protected_domains=["example.com"],
        protected_subdomain_prefixes=[],
        filtering_settings={
            "enabled": True,
            "min_similarity_percent": 60.0,
            "whitelisted_apex_domains": ["partner.com"],
        },
    )
    assert passes is True
    assert reason.startswith("similarity:")


def test_empty_whitelist_no_effect():
    passes, reason = TyposquatFilteringService.should_insert_domain(
        "examp1e.com",
        protected_domains=["example.com"],
        protected_subdomain_prefixes=[],
        filtering_settings={
            "enabled": True,
            "min_similarity_percent": 60.0,
            "whitelisted_apex_domains": [],
        },
    )
    assert passes is True
    assert reason.startswith("similarity:")
