"""Tests for CT monitor client scheduling and coalescing."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.services.ct_monitor_client as ct_client


@pytest.fixture(autouse=True)
def reset_ct_sync_state():
    """Isolate module-level scheduler state between tests."""
    ct_client._ct_sync_task = None
    ct_client._ct_sync_rerun_requested = False
    yield
    if ct_client._ct_sync_task is not None and not ct_client._ct_sync_task.done():
        ct_client._ct_sync_task.cancel()
    ct_client._ct_sync_task = None
    ct_client._ct_sync_rerun_requested = False


@pytest.mark.asyncio
async def test_schedule_starts_background_sync():
    with patch.object(
        ct_client,
        "sync_ct_monitor_program_config",
        new_callable=AsyncMock,
    ) as mock_sync:
        ct_client.schedule_ct_monitor_program_config_sync(reason="test")
        await asyncio.sleep(0.05)
        mock_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_coalesces_concurrent_requests():
    started = asyncio.Event()
    release = asyncio.Event()
    call_count = 0

    async def slow_sync():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            started.set()
            await release.wait()
        return None

    with patch.object(ct_client, "sync_ct_monitor_program_config", side_effect=slow_sync):
        ct_client.schedule_ct_monitor_program_config_sync(reason="first")
        await started.wait()
        ct_client.schedule_ct_monitor_program_config_sync(reason="second")
        release.set()
        if ct_client._ct_sync_task is not None:
            await ct_client._ct_sync_task

    assert call_count == 2


@pytest.mark.asyncio
async def test_sync_accepts_202_from_refresh_endpoint():
    class FakeResponse:
        status_code = 202
        text = ""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url):
            if url.endswith("/start"):
                return FakeResponse()
            if url.endswith("/refresh-domains"):
                resp = FakeResponse()
                resp.status_code = 202
                return resp
            raise AssertionError(url)

    with patch.object(ct_client, "ensure_ct_monitor_started", new_callable=AsyncMock):
        with patch("app.services.ct_monitor_client.httpx.AsyncClient", return_value=FakeClient()):
            await ct_client.sync_ct_monitor_program_config()
