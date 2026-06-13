"""CT asset monitoring program flag: model round-trip and ct-monitor sync triggers."""

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
    """PUT /programs/{name} must refresh ct-monitor when asset monitoring config changes."""

    async def _put(self, client, body, existing=None, sync_mock=None):
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

    @patch("routes.programs.sync_ct_monitor_program_config", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_enabling_ct_asset_monitoring_triggers_sync(
        self,
        mock_sync,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(client, {"ct_asset_monitoring_enabled": True})
        mock_sync.assert_awaited_once()

    @patch("routes.programs.sync_ct_monitor_program_config", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_scope_change_triggers_sync_when_asset_monitoring_enabled(
        self,
        mock_sync,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"scope_domains": [{"pattern": "*.other.io", "wildcard": True}]},
            existing={"ct_asset_monitoring_enabled": True},
        )
        mock_sync.assert_awaited_once()

    @patch("routes.programs.sync_ct_monitor_program_config", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_scope_change_does_not_trigger_sync_when_ct_disabled(
        self,
        mock_sync,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"scope_domains": [{"pattern": "*.other.io", "wildcard": True}]},
        )
        mock_sync.assert_not_awaited()

    @patch("routes.programs.sync_ct_monitor_program_config", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_unrelated_update_does_not_trigger_sync(
        self,
        mock_sync,
        client: httpx.AsyncClient,
        mock_user_superuser: UserResponse,
    ):
        await self._put(
            client,
            {"cidr_list": ["10.0.0.0/8"]},
            existing={"ct_asset_monitoring_enabled": True},
        )
        mock_sync.assert_not_awaited()
