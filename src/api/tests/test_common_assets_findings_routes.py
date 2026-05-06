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
async def test_program_asset_stats_allowed(mock_detail, client: httpx.AsyncClient, mock_user_manager):
    mock_detail.return_value = {"program_name": "program-a"}
    r = await client.get("/assets/common/stats/program-a")
    assert r.status_code == 200
    mock_detail.assert_awaited_once_with({"program_name": "program-a"})


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_detailed_asset_stats", new_callable=AsyncMock)
async def test_program_asset_stats_unknown_program_returns_empty(mock_detail, client: httpx.AsyncClient, mock_user_superuser):
    from app.models.postgres import AssetStatsResponse

    mock_detail.return_value = AssetStatsResponse()
    r = await client.get("/assets/common/stats/no-such-program")
    assert r.status_code == 200
    mock_detail.assert_awaited_once_with({"program_name": "no-such-program"})


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


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_asset_trends", new_callable=AsyncMock)
async def test_asset_trends_superuser(mock_trends, client: httpx.AsyncClient, mock_user_superuser):
    from app.models.postgres import AssetTrendBucket, AssetTrendsResponse

    mock_trends.return_value = AssetTrendsResponse(
        days=2,
        buckets=[
            AssetTrendBucket(date="2026-01-01", subdomains=1, apex_domains=0, ips=0, urls=0, services=0, certificates=0),
            AssetTrendBucket(date="2026-01-02", subdomains=2, apex_domains=0, ips=0, urls=0, services=0, certificates=0),
        ],
        start_date="2026-01-01",
        end_date="2026-01-02",
    )
    r = await client.get("/assets/common/trends?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 2
    assert len(body["buckets"]) == 2
    mock_trends.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_asset_trends", new_callable=AsyncMock)
async def test_asset_trends_restricted_user_programs(mock_trends, client: httpx.AsyncClient, mock_user_restricted):
    from app.models.postgres import AssetTrendsResponse

    mock_trends.return_value = AssetTrendsResponse(days=1, buckets=[], start_date="2026-01-01", end_date="2026-01-01")
    r = await client.get("/assets/common/trends?days=7")
    assert r.status_code == 200
    mock_trends.assert_awaited_once()
    kwargs = mock_trends.call_args.kwargs
    assert set(kwargs["program_names"]) >= {"program-a", "program-b"}


@pytest.mark.asyncio
async def test_asset_trends_custom_range_incomplete(client: httpx.AsyncClient, mock_user_superuser):
    r = await client.get("/assets/common/trends?start_date=2026-01-01")
    assert r.status_code == 400


@pytest.mark.asyncio
@patch("app.routes.common_findings.CommonFindingsRepository.get_findings_trends", new_callable=AsyncMock)
async def test_findings_trends_mock(mock_trends, client: httpx.AsyncClient, mock_user_superuser):
    from app.models.postgres import FindingsTrendBucket, FindingsTrendsResponse

    mock_trends.return_value = FindingsTrendsResponse(
        days=1,
        buckets=[
            FindingsTrendBucket(
                date="2026-01-01",
                nuclei_total=3,
                nuclei_critical=1,
                nuclei_high=0,
                typosquat_total=2,
                typosquat_new=1,
            )
        ],
        start_date="2026-01-01",
        end_date="2026-01-01",
    )
    r = await client.get("/findings/common/trends?days=14")
    assert r.status_code == 200
    body = r.json()
    assert body["buckets"][0]["nuclei_total"] == 3
    mock_trends.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.routes.common_assets.CommonAssetsRepository.get_asset_trends", new_callable=AsyncMock)
@patch("app.routes.common_assets.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
async def test_asset_trends_passes_program_when_found(
    mock_get_program, mock_trends, client: httpx.AsyncClient, mock_user_superuser
):
    from app.models.postgres import AssetTrendsResponse

    mock_get_program.return_value = {"id": "p1", "name": "acme"}
    mock_trends.return_value = AssetTrendsResponse(days=1, buckets=[], start_date="2026-01-01", end_date="2026-01-01")
    r = await client.get("/assets/common/trends?days=7&program_name=acme")
    assert r.status_code == 200
    kwargs = mock_trends.call_args.kwargs
    assert kwargs["program_names"] == ["acme"]


@pytest.mark.asyncio
@patch("app.routes.common_findings.CommonFindingsRepository.get_findings_trends", new_callable=AsyncMock)
@patch("app.routes.common_findings.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
async def test_findings_trends_passes_program_when_found(
    mock_get_program, mock_trends, client: httpx.AsyncClient, mock_user_superuser
):
    from app.models.postgres import FindingsTrendsResponse

    mock_get_program.return_value = {"id": "p1", "name": "acme"}
    mock_trends.return_value = FindingsTrendsResponse(days=1, buckets=[], start_date="2026-01-01", end_date="2026-01-01")
    r = await client.get("/findings/common/trends?days=7&program_name=acme")
    assert r.status_code == 200
    kwargs = mock_trends.call_args.kwargs
    assert kwargs["program_names"] == ["acme"]

