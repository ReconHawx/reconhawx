"""Typed search tests for findings routes (repositories mocked)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

_SEARCH = {"page": 1, "page_size": 10}


@pytest.mark.asyncio
@patch("app.routes.nuclei_findings.NucleiFindingsRepository.search_nuclei_typed", new_callable=AsyncMock)
async def test_nuclei_search_superuser(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 2, "items": [{"id": "1"}], "severity_distribution": {}}
    r = await client.post("/findings/nuclei/search", json=_SEARCH)
    assert r.status_code == 200
    assert r.json()["pagination"]["total_items"] == 2


@pytest.mark.asyncio
async def test_nuclei_search_no_program_access(client: httpx.AsyncClient, mock_user_no_programs):
    r = await client.post("/findings/nuclei/search", json=_SEARCH)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total_items"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
@patch("app.routes.wpscan_findings.WPScanFindingsRepository.search_wpscan_typed", new_callable=AsyncMock)
async def test_wpscan_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": [], "severity_distribution": {}}
    r = await client.post("/findings/wpscan/search", json=_SEARCH)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch("app.routes.typosquat_findings.TyposquatFindingsRepository.search_typosquat_typed", new_callable=AsyncMock)
async def test_typosquat_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": []}
    r = await client.post("/findings/typosquat/search", json=_SEARCH)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch("app.routes.broken_links.BrokenLinksRepository.search_broken_links", new_callable=AsyncMock)
async def test_broken_links_search_superuser(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {
        "findings": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "total_pages": 0,
    }
    r = await client.post("/findings/broken-links/search", json={"page": 1, "page_size": 10})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_broken_links_search_forbidden_program(client: httpx.AsyncClient, mock_user_manager):
    r = await client.post(
        "/findings/broken-links/search",
        json={"page": 1, "page_size": 10, "program_name": "not-allowed"},
    )
    assert r.status_code == 403
