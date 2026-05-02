"""Tests for workflow logs WAF summary persistence and GET response."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_post_workflow_execution_logs_passes_waf_summary(
    client: httpx.AsyncClient, mock_user_superuser
):
    """Runner POST should forward waf_summary through the repository mapping."""
    captured: dict = {}

    async def fake_create(log_object: dict) -> str:
        captured.update(dict(log_object))
        return "wf-log-id"

    waf = {"any_skips": True, "fully_skipped_steps": ["S1"], "partial_skip_steps": []}
    exec_id = "eeeeeeee-aaaa-bbbb-cccc-000000000111"
    body = {
        "execution_id": exec_id,
        "program_id": "00000000-0000-0000-0000-000000000001",
        "workflow_name": "t",
        "result": "cancelled_waf",
        "waf_summary": waf,
        "workflow_steps": [],
    }

    with patch("routes.workflows.workflow_repository.create_workflow_log", new_callable=AsyncMock) as m:
        m.side_effect = fake_create
        with patch("routes.workflows.k8s_service.delete_workflow_configmap"):
            with patch("routes.workflows.thread_pool.submit", new_callable=MagicMock):
                r = await client.post(f"/workflows/executions/{exec_id}/logs", json=body)
                assert r.status_code == 200
                m.assert_awaited_once()
    assert captured.get("waf_summary") == waf
    assert captured.get("result") == "cancelled_waf"


@pytest.mark.asyncio
@patch(
    "routes.workflows.workflow_repository.get_workflow_logs_by_execution_id",
    new_callable=AsyncMock,
)
async def test_get_workflow_execution_logs_includes_waf_summary(
    mock_get, client: httpx.AsyncClient, mock_user_superuser
):
    waf = {
        "any_skips": True,
        "fully_skipped_steps": [],
        "partial_skip_steps": [{"step": "Probe", "skipped_inputs": 3}],
    }
    mock_get.return_value = {
        "execution_id": "ex-1",
        "program_name": "program-a",
        "workflow_name": "w",
        "result": "partial_waf",
        "workflow_steps": [],
        "waf_summary": waf,
        "started_at": "2020-01-01T00:00:00Z",
        "completed_at": "2020-01-01T01:00:00Z",
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T01:00:00Z",
    }
    r = await client.get("/workflows/executions/ex-1/logs")
    assert r.status_code == 200
    data = r.json()
    assert data["result"] == "partial_waf"
    assert data["waf_summary"] == waf
