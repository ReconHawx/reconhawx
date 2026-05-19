"""Tests for GET /workflows/executions (filters, sorting, pagination wiring)."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_invalid_sort_field_returns_400(client, mock_user_superuser):
    """progress is computed client-side only; sorting by it must be rejected."""
    r = await client.get(
        "/workflows/executions", params={"sort_field": "progress"}
    )
    assert r.status_code == 400
    assert "Invalid sort_field" in r.json()["detail"]


@pytest.mark.asyncio
async def test_sort_field_status_maps_to_workflow_logs_status_column(client, mock_user_superuser):
    """Regression: sort_field=status must order by WorkflowLog.status, not a missing ``result`` column."""
    import routes.workflows as wf

    sanitize = AsyncMock(side_effect=lambda q: q)
    count_mock = AsyncMock(return_value=0)
    exec_mock = AsyncMock(return_value=[])

    with patch.object(wf.workflow_repository, "sanitize_query", sanitize):
        with patch.object(wf.workflow_repository, "count_workflow_logs", count_mock):
            with patch.object(wf.workflow_repository, "execute_query", exec_mock):
                r = await client.get(
                    "/workflows/executions",
                    params={"sort_field": "status", "sort_order": "asc"},
                )

    assert r.status_code == 200
    exec_mock.assert_awaited_once()
    assert exec_mock.await_args.kwargs["sort"] == {"status": 1}


@pytest.mark.asyncio
async def test_started_at_sort_desc_passed_to_repository(client, mock_user_superuser):
    import routes.workflows as wf

    sanitize = AsyncMock(side_effect=lambda q: q)
    count_mock = AsyncMock(return_value=0)
    exec_mock = AsyncMock(return_value=[])

    with patch.object(wf.workflow_repository, "sanitize_query", sanitize):
        with patch.object(wf.workflow_repository, "count_workflow_logs", count_mock):
            with patch.object(wf.workflow_repository, "execute_query", exec_mock):
                r = await client.get(
                    "/workflows/executions",
                    params={
                        "sort_field": "started_at",
                        "sort_order": "desc",
                        "limit": 10,
                    },
                )

    assert r.status_code == 200
    assert exec_mock.await_args.kwargs["sort"] == {"started_at": -1}


@pytest.mark.asyncio
async def test_filter_query_params_merge_into_execution_query(client, mock_user_superuser):
    import routes.workflows as wf

    sanitize = AsyncMock(side_effect=lambda q: q)
    count_mock = AsyncMock(return_value=0)
    exec_mock = AsyncMock(return_value=[])

    with patch.object(wf.workflow_repository, "sanitize_query", sanitize):
        with patch.object(wf.workflow_repository, "count_workflow_logs", count_mock):
            with patch.object(wf.workflow_repository, "execute_query", exec_mock):
                r = await client.get(
                    "/workflows/executions",
                    params={
                        "workflow_name": "audit",
                        "status": "Running",
                        "execution_id": "abc-def",
                        "program_name": "program-a",
                    },
                )

    assert r.status_code == 200
    qexec = exec_mock.await_args.args[0]
    assert qexec["program_name"] == "program-a"
    assert qexec["workflow_name"] == {"$regex": "audit", "$options": "i"}
    assert qexec["execution_id"] == {"$regex": "abc-def", "$options": "i"}
    assert qexec["status"] == "running"


@pytest.mark.asyncio
async def test_distinct_execution_statuses_post_returns_repository_values(
    client, mock_user_superuser
):
    """POST /workflows/executions/distinct/status returns DB-backed list from repository."""
    import routes.workflows as wf

    sanitize = AsyncMock(side_effect=lambda q: q)
    distinct_mock = AsyncMock(return_value=["failed", "pending", "success"])

    with patch.object(wf.workflow_repository, "sanitize_query", sanitize):
        with patch.object(
            wf.workflow_repository,
            "get_distinct_workflow_execution_statuses",
            distinct_mock,
        ):
            r = await client.post("/workflows/executions/distinct/status", json=None)
    assert r.status_code == 200
    assert r.json() == ["failed", "pending", "success"]
    distinct_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_distinct_execution_status_forbidden_program_returns_empty_without_db(
    client, mock_user_restricted,
):
    """Scoped user cannot probe other programs; repository is not called."""
    import routes.workflows as wf

    distinct_mock = AsyncMock()

    with patch.object(
        wf.workflow_repository,
        "get_distinct_workflow_execution_statuses",
        distinct_mock,
    ):
        r = await client.post(
            "/workflows/executions/distinct/status",
            json={"program": "program-z"},
        )
    assert r.status_code == 200
    assert r.json() == []
    distinct_mock.assert_not_called()
