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
