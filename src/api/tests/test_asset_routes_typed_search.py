"""Typed search smoke tests for asset routes (repository mocked)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from auth.dependencies import get_current_user

_SEARCH_BODY = {"page": 1, "page_size": 10}
_EMPTY_PAGE = {
    "status": "success",
    "pagination": {
        "total_items": 0,
        "total_pages": 1,
        "current_page": 1,
        "page_size": 10,
        "has_next": False,
        "has_previous": False,
    },
    "items": [],
}


@pytest.mark.asyncio
@patch("app.routes.ip_assets.IPAssetsRepository.search_ips_typed", new_callable=AsyncMock)
async def test_ip_search_superuser(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 1, "items": [{"ip_address": "1.1.1.1"}]}
    r = await client.post("/assets/ip/search", json=_SEARCH_BODY)
    assert r.status_code == 200
    assert r.json()["pagination"]["total_items"] == 1


@pytest.mark.asyncio
async def test_ip_search_no_program_access_empty(client: httpx.AsyncClient, mock_user_no_programs):
    r = await client.post("/assets/ip/search", json=_SEARCH_BODY)
    assert r.status_code == 200
    assert r.json() == _EMPTY_PAGE


@pytest.mark.asyncio
@patch("app.routes.url_assets.UrlAssetsRepository.search_urls_typed", new_callable=AsyncMock)
async def test_url_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": []}
    r = await client.post("/assets/url/search", json=_SEARCH_BODY)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch("app.routes.url_assets.UrlAssetsRepository.search_urls_typed", new_callable=AsyncMock)
async def test_url_search_forwards_asset_fk_filters(
    mock_search, client: httpx.AsyncClient, mock_user_superuser
):
    mock_search.return_value = {"total_count": 0, "items": []}
    asset_id = "123e4567-e89b-12d3-a456-426614174002"
    payload = {
        **_SEARCH_BODY,
        "subdomain_id": asset_id,
        "certificate_id": asset_id,
        "service_id": asset_id,
    }
    r = await client.post("/assets/url/search", json=payload)
    assert r.status_code == 200
    kwargs = mock_search.call_args.kwargs
    assert kwargs["subdomain_id"] == asset_id
    assert kwargs["certificate_id"] == asset_id
    assert kwargs["service_id"] == asset_id


@pytest.mark.asyncio
@patch("app.routes.service_assets.ServiceAssetsRepository.search_services_typed", new_callable=AsyncMock)
async def test_service_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": []}
    r = await client.post("/assets/service/search", json=_SEARCH_BODY)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch("app.routes.apexdomain_assets.ApexDomainAssetsRepository.search_apex_domains_typed", new_callable=AsyncMock)
async def test_apex_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": []}
    r = await client.post("/assets/apex-domain/search", json=_SEARCH_BODY)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch(
    "app.routes.certificate_assets.CertificateAssetsRepository.search_certificates_typed",
    new_callable=AsyncMock,
)
async def test_certificate_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    mock_search.return_value = {"total_count": 0, "items": []}
    r = await client.post("/assets/certificate/search", json=_SEARCH_BODY)
    assert r.status_code == 200


@pytest.mark.asyncio
@patch("app.routes.screenshot_assets.ScreenshotRepository.search_screenshots_typed", new_callable=AsyncMock)
async def test_screenshot_search(mock_search, client: httpx.AsyncClient, mock_user_superuser):
    """Screenshot search uses Depends(get_current_user); override it (Depends binds at import time)."""

    async def _override_current_user():
        return mock_user_superuser

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        mock_search.return_value = {"total_count": 0, "items": []}
        r = await client.post("/assets/screenshot/search", json=_SEARCH_BODY)
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
