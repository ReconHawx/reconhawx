"""Tests for /assets/common/stats and /findings/common/stats (repository mocked)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_aggregated_asset_stats", new_callable=AsyncMock)
async def test_aggregated_asset_stats_superuser(mock_stats, client: httpx.AsyncClient, mock_user_superuser):
    mock_stats.return_value = {"total_programs": 0}
    r = await client.get("/assets/common/stats")
    assert r.status_code == 200
    assert r.json()["total_programs"] == 0
    mock_stats.assert_awaited_once_with()


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_aggregated_asset_stats", new_callable=AsyncMock)
async def test_aggregated_asset_stats_restricted_user(mock_stats, client: httpx.AsyncClient, mock_user_restricted):
    mock_stats.return_value = {"total_programs": 2}
    r = await client.get("/assets/common/stats")
    assert r.status_code == 200
    mock_stats.assert_awaited_once()
    args, _ = mock_stats.call_args
    assert set(args[0]) >= {"program-a", "program-b"}


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_detailed_asset_stats", new_callable=AsyncMock)
@patch("app.routes.common_assets.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
async def test_program_asset_stats_allowed(
    mock_get_program, mock_detail, client: httpx.AsyncClient, mock_user_manager
):
    mock_get_program.return_value = {"id": "p", "name": "program-a"}
    mock_detail.return_value = {"program_name": "program-a"}
    r = await client.get("/assets/common/stats/program-a")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_program_asset_stats_forbidden(client: httpx.AsyncClient, mock_user_manager):
    r = await client.get("/assets/common/stats/other-program")
    assert r.status_code == 403


@pytest.mark.asyncio
@patch(
    "app.routes.common_findings.CommonFindingsRepository.get_aggregated_findings_stats",
    new_callable=AsyncMock,
)
async def test_aggregated_findings_stats(mock_stats, client: httpx.AsyncClient, mock_user_superuser):
    mock_stats.return_value = {"total_programs": 0}
    r = await client.get("/findings/common/stats")
    assert r.status_code == 200


@pytest.mark.asyncio
@patch(
    "app.routes.common_findings.CommonFindingsRepository.get_detailed_findings_stats",
    new_callable=AsyncMock,
)
async def test_findings_stats_by_program(mock_detail, client: httpx.AsyncClient, mock_user_manager):
    mock_detail.return_value = {"program_name": "program-a"}
    r = await client.get("/findings/common/stats/program-a")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_findings_stats_by_program_forbidden(client: httpx.AsyncClient, mock_user_manager):
    r = await client.get("/findings/common/stats/forbidden-program")
    assert r.status_code == 403
