"""CT asset monitoring program flag: model round-trip and ct-monitor sync triggers."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.user_postgres import UserResponse

_PROGRAM = {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "prog1",
    "scope_domains": [{"pattern": "*.example.com", "wildcard": True}],
    "out_of_scope_domains": [],
    "typosquat_filtering_settings": None,
    "ct_monitoring_enabled": False,
    "ct_asset_monitoring_enabled": False,
}


def test_api_program_model_defaults_ct_asset_monitoring_off():
    from app.models.program import APIProgram

    program = APIProgram(name="p1")
    assert program.ct_asset_monitoring_enabled is False
    program = APIProgram(name="p1", ct_asset_monitoring_enabled=True)
    assert program.ct_asset_monitoring_enabled is True


class TestCtAssetMonitoringSyncTriggers:
    """PUT /programs/{name} must schedule ct-monitor refresh when asset monitoring config changes."""

    async def _put(self, client, body, existing=None):
        existing = dict(_PROGRAM, **(existing or {}))
        with patch(
            "app.routes.programs.ProgramRepository.get_program_by_name",
            new_callable=AsyncMock,
            return_value=existing,
        ), patch(
            "app.routes.programs.ProgramRepository.update_program",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.put("/programs/prog1", json=body)
        assert response.status_code == 200
        return response

    @patch("routes.programs.schedule_ct_monitor_program_config_sync")
    @pytest.mark.asyncio
    async def test_enabling_ct_asset_monitoring_triggers_sync(
        self,
        mock_schedule,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(client, {"ct_asset_monitoring_enabled": True})
        mock_schedule.assert_called_once()

    @patch("routes.programs.schedule_ct_monitor_program_config_sync")
    @pytest.mark.asyncio
    async def test_scope_change_triggers_sync_when_asset_monitoring_enabled(
        self,
        mock_schedule,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"scope_domains": [{"pattern": "*.other.io", "wildcard": True}]},
            existing={"ct_asset_monitoring_enabled": True},
        )
        mock_schedule.assert_called_once()

    @patch("routes.programs.schedule_ct_monitor_program_config_sync")
    @pytest.mark.asyncio
    async def test_scope_change_does_not_trigger_sync_when_ct_disabled(
        self,
        mock_schedule,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"scope_domains": [{"pattern": "*.other.io", "wildcard": True}]},
        )
        mock_schedule.assert_not_called()

    @patch("routes.programs.schedule_ct_monitor_program_config_sync")
    @pytest.mark.asyncio
    async def test_unrelated_update_does_not_trigger_sync(
        self,
        mock_schedule,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"cidr_list": ["10.0.0.0/8"]},
            existing={"ct_asset_monitoring_enabled": True},
        )
        mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_put_returns_before_ct_sync_completes(
        self,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        """Program save must not block on CT-Monitor refresh."""
        release = asyncio.Event()

        async def blocking_sync(*args, **kwargs):
            await release.wait()

        with patch(
            "app.routes.programs.ProgramRepository.get_program_by_name",
            new_callable=AsyncMock,
            return_value=dict(_PROGRAM),
        ), patch(
            "app.routes.programs.ProgramRepository.update_program",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.services.ct_monitor_client.sync_ct_monitor_program_config",
            side_effect=blocking_sync,
        ):
            start = time.monotonic()
            response = await client.put(
                "/programs/prog1",
                json={"ct_asset_monitoring_enabled": True},
            )
            elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < 0.5
        release.set()
        if ct_client_task := __import__(
            "app.services.ct_monitor_client",
            fromlist=["_ct_sync_task"],
        )._ct_sync_task:
            if not ct_client_task.done():
                await asyncio.wait_for(ct_client_task, timeout=2.0)
