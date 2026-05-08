"""Tests for GET /dashboard/summary."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
@patch("routes.dashboard.run_in_threadpool", new_callable=AsyncMock)
@patch(
    "routes.dashboard.WorkflowRepository.count_active_workflow_logs",
    new_callable=AsyncMock,
)
@patch(
    "routes.dashboard.WorkflowRepository.execute_query",
    new_callable=AsyncMock,
)
@patch(
    "routes.dashboard.WorkflowRepository.sanitize_query",
    new_callable=AsyncMock,
)
@patch(
    "routes.dashboard.UrlAssetsRepository.get_technologies_with_urls",
    new_callable=AsyncMock,
)
@patch("routes.dashboard.CommonFindingsRepository.get_latest_findings", new_callable=AsyncMock)
@patch("routes.dashboard.CommonAssetsRepository.get_latest_assets", new_callable=AsyncMock)
@patch("routes.dashboard.CommonFindingsRepository.get_findings_trends", new_callable=AsyncMock)
@patch("routes.dashboard.CommonAssetsRepository.get_asset_trends", new_callable=AsyncMock)
@patch("routes.dashboard.CommonFindingsRepository.get_aggregated_findings_stats", new_callable=AsyncMock)
@patch("routes.dashboard.CommonAssetsRepository.get_aggregated_asset_stats", new_callable=AsyncMock)
async def test_dashboard_summary_ok(
    mock_asset_agg,
    mock_findings_agg,
    mock_asset_trends,
    mock_findings_trends,
    mock_latest_assets,
    mock_latest_findings,
    mock_tech_urls,
    mock_sanitize_query,
    mock_exec,
    mock_active,
    mock_threadpool,
    client: httpx.AsyncClient,
    mock_user_superuser,
):
    from app.models.postgres import (
        AggregatedAssetStatsResponse,
        AggregatedFindingsStatsResponse,
        FindingsTrendsResponse,
        AssetTrendsResponse,
    )

    mock_asset_agg.return_value = AggregatedAssetStatsResponse()
    mock_findings_agg.return_value = AggregatedFindingsStatsResponse()
    mock_asset_trends.return_value = AssetTrendsResponse(
        days=1,
        buckets=[],
        start_date="2026-01-01",
        end_date="2026-01-01",
    )
    mock_findings_trends.return_value = FindingsTrendsResponse(
        days=1,
        buckets=[],
        start_date="2026-01-01",
        end_date="2026-01-01",
    )
    mock_latest_assets.return_value = {"subdomains": [], "urls": []}
    mock_latest_findings.return_value = {"nuclei": [], "typosquat": [], "wpscan": []}
    mock_exec.return_value = []
    mock_active.return_value = 0
    mock_tech_urls.return_value = {"items": [], "pagination": {"total_items": 0}}
    mock_threadpool.return_value = {
        "queue_length": 0,
        "has_capacity": True,
        "estimated_wait_time": 0,
        "queue_name": "q",
    }
    mock_sanitize_query.return_value = {}

    r = await client.get("/dashboard/summary?latest_limit=5&days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["workflow_executions"] == []
    assert body["active_workflows"] == 0


@pytest.mark.asyncio
async def test_dashboard_summary_program_forbidden(
    client: httpx.AsyncClient,
    mock_user_manager,
):
    r = await client.get("/dashboard/summary?program_name=forbidden-program")
    assert r.status_code == 403
