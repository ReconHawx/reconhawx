"""Tests for coalesced background config refresh on CTMonitorService."""

import asyncio
from unittest.mock import patch

import pytest


@pytest.fixture
def service():
    from main import CTMonitorService

    svc = CTMonitorService()
    svc._running = True
    return svc


@pytest.mark.asyncio
async def test_request_config_refresh_returns_202_semantics(service):
    refresh_started = asyncio.Event()
    refresh_done = asyncio.Event()

    async def slow_refresh():
        refresh_started.set()
        await refresh_done.wait()

    with patch.object(service, "_refresh_protected_domains", side_effect=slow_refresh):
        started = service.request_config_refresh()
        assert started is True
        await refresh_started.wait()

        coalesced = service.request_config_refresh()
        assert coalesced is False
        assert service._config_refresh_requested is True

        refresh_done.set()
        if service._config_refresh_task is not None:
            await service._config_refresh_task

    assert service._config_refresh_in_progress is False
    assert service._config_refresh_task is None


@pytest.mark.asyncio
async def test_refresh_domains_http_endpoint_returns_202(service):
    from httpx import ASGITransport, AsyncClient
    from main import http_app

    with patch.object(service, "is_running", return_value=True), patch(
        "main.get_service",
        return_value=service,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=http_app),
            base_url="http://test",
        ) as client:
            with patch.object(service, "request_config_refresh", return_value=True) as mock_req:
                response = await client.post("/refresh-domains")
                assert response.status_code == 202
                assert response.json()["status"] == "accepted"
                mock_req.assert_called_once()


def test_get_status_includes_config_refresh_fields(service):
    service._config_refresh_in_progress = True
    service._config_refresh_requested = False
    service._last_config_refresh_error = "boom"

    status = service.get_status()
    assert status["config_refresh_in_progress"] is True
    assert status["config_refresh_requested"] is False
    assert status["last_config_refresh_error"] == "boom"
