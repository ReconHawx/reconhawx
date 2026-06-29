"""Tests for finding → asset ID resolution at ingest."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.finding_asset_resolve import (
    ensure_finding_url_asset,
    resolve_finding_asset_ids,
    resolve_finding_asset_ids_with_url_ensure,
    url_lookup_variants,
)


def _mock_db_query_chain(rows):
    """Return a mock db whose .query(...).filter(...).first() yields rows[0] or None."""
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.first.side_effect = rows
    return db


@pytest.mark.parametrize(
    "hostname,sub_row",
    [
        ("www.example.com", (uuid.uuid4(),)),
        ("www.example.com", None),
    ],
)
def test_resolve_subdomain(hostname, sub_row):
    program_id = uuid.uuid4()
    db = _mock_db_query_chain([sub_row])
    resolved = resolve_finding_asset_ids(
        db,
        program_id,
        hostname=hostname,
        resolve_url=False,
        resolve_ip=False,
        resolve_service=False,
    )
    if sub_row:
        assert resolved.subdomain_id == sub_row[0]
    else:
        assert resolved.subdomain_id is None


def test_resolve_url_id():
    program_id = uuid.uuid4()
    url_id = uuid.uuid4()
    db = _mock_db_query_chain([(url_id,)])
    resolved = resolve_finding_asset_ids(
        db,
        program_id,
        url="https://example.com:443/",
        resolve_subdomain=False,
        resolve_ip=False,
        resolve_service=False,
    )
    assert resolved.url_id == url_id


def test_resolve_url_falls_back_without_program_filter():
    program_id = uuid.uuid4()
    url_id = uuid.uuid4()
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.first.side_effect = [None, (url_id,)]
    resolved = resolve_finding_asset_ids(
        db,
        program_id,
        url="https://example.com:443/",
        resolve_subdomain=False,
        resolve_ip=False,
        resolve_service=False,
    )
    assert resolved.url_id == url_id


def test_resolve_ip_and_service():
    program_id = uuid.uuid4()
    ip_id = uuid.uuid4()
    service_id = uuid.uuid4()
    db = _mock_db_query_chain([(ip_id,), (service_id,)])
    resolved = resolve_finding_asset_ids(
        db,
        program_id,
        ip="104.21.91.163",
        port=443,
        resolve_subdomain=False,
        resolve_url=False,
    )
    assert resolved.ip_id == ip_id
    assert resolved.service_id == service_id


@pytest.mark.asyncio
async def test_resolve_with_url_ensure_creates_when_missing():
    program_id = uuid.uuid4()
    new_url_id = uuid.uuid4()
    db = _mock_db_query_chain([None, None])  # url lookup misses

    with patch(
        "utils.finding_asset_resolve.ensure_finding_url_asset",
        new_callable=AsyncMock,
        return_value=new_url_id,
    ) as ensure_mock:
        resolved = await resolve_finding_asset_ids_with_url_ensure(
            db,
            program_id,
            "prog",
            url="https://example.com:443/",
            resolve_subdomain=False,
            resolve_ip=False,
            resolve_service=False,
        )
    ensure_mock.assert_awaited_once()
    assert resolved.url_id == new_url_id


@pytest.mark.asyncio
async def test_resolve_with_url_ensure_backfills_subdomain_from_url():
    program_id = uuid.uuid4()
    new_url_id = uuid.uuid4()
    subdomain_id = uuid.uuid4()
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.first.side_effect = [None, None, None, (subdomain_id,)]

    with patch(
        "utils.finding_asset_resolve.ensure_finding_url_asset",
        new_callable=AsyncMock,
        return_value=new_url_id,
    ) as ensure_mock:
        resolved = await resolve_finding_asset_ids_with_url_ensure(
            db,
            program_id,
            "prog",
            url="https://dummysite.h3x.it:443/",
            hostname="dummysite.h3x.it",
            resolve_ip=False,
            resolve_service=False,
        )
    ensure_mock.assert_awaited_once()
    assert resolved.url_id == new_url_id
    assert resolved.subdomain_id == subdomain_id


@pytest.mark.asyncio
async def test_ensure_finding_url_asset_returns_id_from_repo():
    url_id = uuid.uuid4()
    with patch(
        "repository.url_assets_repo.UrlAssetsRepository.create_or_update_url",
        new_callable=AsyncMock,
        return_value=(str(url_id), "created", [], []),
    ):
        got = await ensure_finding_url_asset(
            "prog",
            url="https://example.com:443/",
            hostname="example.com",
            port=443,
            scheme="https",
        )
    assert got == url_id


def test_nuclei_dict_includes_asset_ids():
    from repository.findings_repo import _nuclei_dict_from_finding

    f = MagicMock()
    f.id = uuid.uuid4()
    f.url = "https://example.com/"
    f.title = "test"
    f.severity = "info"
    f.hostname = "example.com"
    f.port = 443
    f.scheme = "https"
    f.description = None
    f.notes = None
    f.created_at = None
    f.updated_at = None
    f.details = {"template_id": "t", "type": "http", "tags": []}
    f.program = None
    f.ip = None
    sid = uuid.uuid4()
    uid = uuid.uuid4()
    iid = uuid.uuid4()
    svid = uuid.uuid4()
    f.subdomain_id = sid
    f.url_id = uid
    f.ip_id = iid
    f.service_id = svid

    d = _nuclei_dict_from_finding(f)
    assert d["domain_id"] == str(sid)
    assert d["url_id"] == str(uid)
    assert d["ip_id"] == str(iid)
    assert d["service_id"] == str(svid)
