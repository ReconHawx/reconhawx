"""Tests for URL bulk SQL helper."""

import pytest


def test_urls_require_full_orm_empty():
    from repository.bulk_sql.urls import urls_require_full_orm

    assert urls_require_full_orm([]) is False


def test_urls_require_full_orm_plain():
    from repository.bulk_sql.urls import urls_require_full_orm

    assert urls_require_full_orm([{"url": "https://a/b"}]) is False


def test_urls_require_full_orm_technologies():
    from repository.bulk_sql.urls import urls_require_full_orm

    assert urls_require_full_orm([{"url": "x", "technologies": ["nginx"]}]) is True


def test_urls_require_full_orm_extracted_links():
    from repository.bulk_sql.urls import urls_require_full_orm

    assert urls_require_full_orm([{"url": "x", "extracted_links": ["http://ext"]}]) is True


def test_lower_url_host_merges_duplicate_batch_keys_case_only():
    """Bulk URL dedupe keys use lower_url_host — same DNS host must collide."""
    from utils.url_utils import lower_url_host

    u1 = lower_url_host("https://Aa.Com/p")
    u2 = lower_url_host("HTTPS://aa.COM/p")
    assert u1 == u2 == "https://aa.com/p"
