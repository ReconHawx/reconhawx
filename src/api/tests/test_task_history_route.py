"""Tests for GET /assets/{type}/{id}/task-history."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
@patch("routes.task_history.check_program_permission_by_id", new_callable=AsyncMock)
@patch("routes.task_history.TaskHistoryRepository.get_task_history", new_callable=AsyncMock)
@patch("routes.task_history.TaskHistoryRepository.get_asset_program_id", new_callable=AsyncMock)
async def test_task_history_ok(
    mock_program_id,
    mock_history,
    mock_perm,
    client: httpx.AsyncClient,
    mock_user_superuser,
):
    pid = uuid.uuid4()
    aid = uuid.uuid4()
    mock_program_id.return_value = pid
    mock_perm.return_value = True
    mock_history.return_value = (
        [
            {
                "workflow_log_id": str(uuid.uuid4()),
                "execution_id": "exec-1",
                "workflow_name": "wf",
                "step_name": "s",
                "task_name": "test_http",
                "task_type": "test_http",
                "started_at": "2020-01-01T00:00:00Z",
                "completed_at": None,
                "status": "success",
            }
        ],
        1,
    )
    r = await client.get(f"/assets/subdomain/{aid}/task-history?page=1&page_size=10")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["pagination"]["total_items"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["execution_id"] == "exec-1"


@pytest.mark.asyncio
@patch("routes.task_history.TaskHistoryRepository.get_asset_program_id", new_callable=AsyncMock)
async def test_task_history_asset_missing(mock_program_id, client: httpx.AsyncClient, mock_user_superuser):
    mock_program_id.return_value = None
    aid = uuid.uuid4()
    r = await client.get(f"/assets/url/{aid}/task-history")
    assert r.status_code == 404


@pytest.mark.asyncio
@patch("routes.task_history.check_program_permission_by_id", new_callable=AsyncMock)
@patch("routes.task_history.TaskHistoryRepository.get_asset_program_id", new_callable=AsyncMock)
async def test_task_history_forbidden_returns_404(
    mock_program_id,
    mock_perm,
    client: httpx.AsyncClient,
    mock_user_superuser,
):
    mock_program_id.return_value = uuid.uuid4()
    mock_perm.return_value = False
    aid = uuid.uuid4()
    r = await client.get(f"/assets/subdomain/{aid}/task-history")
    assert r.status_code == 404


@pytest.mark.asyncio
@patch("routes.task_history.check_program_permission_by_id", new_callable=AsyncMock)
@patch("routes.task_history.TaskHistoryRepository.get_task_history", new_callable=AsyncMock)
@patch("routes.task_history.TaskHistoryRepository.get_asset_program_id", new_callable=AsyncMock)
async def test_task_history_empty_items(
    mock_program_id,
    mock_history,
    mock_perm,
    client: httpx.AsyncClient,
    mock_user_superuser,
):
    mock_program_id.return_value = uuid.uuid4()
    mock_perm.return_value = True
    mock_history.return_value = ([], 0)
    aid = uuid.uuid4()
    r = await client.get(f"/assets/ip/{aid}/task-history")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["pagination"]["total_items"] == 0
