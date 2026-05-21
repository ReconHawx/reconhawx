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


def test_canonical_url_merges_duplicate_batch_keys_case_only():
    """Bulk URL dedupe keys use normalize_url_asset_payload — same URL must collide."""
    from utils.url_utils import normalize_url_asset_payload

    d1 = {"url": "https://Aa.Com/p"}
    d2 = {"url": "HTTPS://aa.COM/p"}
    assert normalize_url_asset_payload(d1) == normalize_url_asset_payload(d2) == "https://aa.com:443/p"
