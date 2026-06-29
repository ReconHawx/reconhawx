"""Tests for URL ingest subdomain auto-creation."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from repository.url_assets_repo import UrlAssetsRepository


def test_hostname_is_ip():
    assert UrlAssetsRepository._hostname_is_ip("192.168.1.1") is True
    assert UrlAssetsRepository._hostname_is_ip("2001:db8::1") is True
    assert UrlAssetsRepository._hostname_is_ip("example.com") is False


def test_ensure_subdomain_for_hostname_skips_ip():
    db = MagicMock()
    program = MagicMock(id=uuid.uuid4(), name="prog")
    sub_id, events = UrlAssetsRepository._ensure_subdomain_for_hostname(
        db, "10.0.0.1", program, "nuclei_scan"
    )
    assert sub_id is None
    assert events == []
    db.query.assert_not_called()


def test_ensure_subdomain_for_hostname_returns_existing():
    program = MagicMock(id=uuid.uuid4(), name="prog")
    existing = MagicMock(id=uuid.uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    sub_id, events = UrlAssetsRepository._ensure_subdomain_for_hostname(
        db, "dummysite.h3x.it", program, "finding_ingest"
    )
    assert sub_id == str(existing.id)
    assert events == []


def test_ensure_subdomain_for_hostname_creates_apex_and_subdomain():
    program = MagicMock(id=uuid.uuid4(), name="prog")
    apex_id = uuid.uuid4()
    subdomain_id = uuid.uuid4()

    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query

    # Subdomain lookup miss, apex lookup miss, then flush assigns ids on add
    query.first.side_effect = [None, None]

    def _add_side_effect(obj):
        if getattr(obj, "name", None) == "h3x.it":
            obj.id = apex_id
        elif getattr(obj, "name", None) == "dummysite.h3x.it":
            obj.id = subdomain_id

    db.add.side_effect = _add_side_effect

    sub_id, events = UrlAssetsRepository._ensure_subdomain_for_hostname(
        db, "dummysite.h3x.it", program, "finding_ingest"
    )

    assert sub_id == str(subdomain_id)
    assert len(events) == 2
    assert events[0]["asset_type"] == "apex_domain"
    assert events[0]["name"] == "h3x.it"
    assert events[1]["asset_type"] == "subdomain"
    assert events[1]["name"] == "dummysite.h3x.it"
    assert db.add.call_count == 2
    assert db.flush.call_count == 2


def test_bulk_hostname_is_ip():
    from repository.bulk_sql.urls import _hostname_is_ip

    assert _hostname_is_ip("127.0.0.1") is True
    assert _hostname_is_ip("host.example.com") is False
