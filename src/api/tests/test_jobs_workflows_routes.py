"""Route tests for /jobs and /workflows (repository and K8s submission mocks)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
@patch("routes.jobs.JobRepository.get_all_jobs", new_callable=AsyncMock)
async def test_jobs_list_success(mock_get, client: httpx.AsyncClient, mock_user_superuser):
    mock_get.return_value = ([{"id": "j1", "job_type": "x"}], 1)
    r = await client.get("/jobs", params={"page": 1, "limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["total"] == 1
    assert len(data["jobs"]) == 1


@pytest.mark.asyncio
async def test_dummy_batch_validation_empty_items(client: httpx.AsyncClient, mock_user_superuser):
    r = await client.post("/jobs/dummy-batch", json={"items": []})
    assert r.status_code == 400
    assert "items" in r.json().get("detail", "").lower()


@pytest.mark.asyncio
@patch("routes.jobs.JobSubmissionService")
@patch("routes.jobs.JobRepository.update_job_status", new_callable=AsyncMock)
@patch("routes.jobs.JobRepository.create_job", new_callable=AsyncMock)
async def test_dummy_batch_success(
    mock_create_job, mock_update_status, mock_svc_class, client: httpx.AsyncClient, mock_user_superuser
):
    mock_create_job.return_value = True
    mock_inst = MagicMock()
    mock_svc_class.return_value = mock_inst
    r = await client.post("/jobs/dummy-batch", json={"items": ["a", "b"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert "job_id" in body
    mock_inst.create_dummy_batch_job.assert_called_once()
    mock_create_job.assert_awaited_once()


@pytest.mark.asyncio
@patch("routes.jobs.JobSubmissionService")
@patch("routes.jobs.JobRepository.update_job_status", new_callable=AsyncMock)
@patch("routes.jobs.JobRepository.create_job", new_callable=AsyncMock)
async def test_dummy_batch_k8s_submit_failure(
    mock_create_job, mock_update_status, mock_svc_class, client: httpx.AsyncClient, mock_user_superuser
):
    mock_create_job.return_value = True
    mock_inst = MagicMock()
    mock_inst.create_dummy_batch_job.side_effect = RuntimeError("no cluster")
    mock_svc_class.return_value = mock_inst
    r = await client.post("/jobs/dummy-batch", json={"items": ["a"]})
    assert r.status_code == 500
    mock_update_status.assert_awaited()


@pytest.mark.asyncio
@patch("routes.workflows.workflow_definition_repository.get_workflow_definitions", new_callable=AsyncMock)
async def test_workflow_definitions_filters_by_permission(
    mock_get, client: httpx.AsyncClient, mock_user_manager
):
    mock_get.return_value = [
        {"id": "1", "name": "global", "program_name": None, "description": "", "steps": [], "variables": {}, "inputs": {}, "created_at": "2020-01-01T00:00:00", "updated_at": "2020-01-01T00:00:00"},
        {
            "id": "2",
            "name": "in-a",
            "program_name": "program-a",
            "description": "",
            "steps": [],
            "variables": {},
            "inputs": {},
            "created_at": "2020-01-01T00:00:00",
            "updated_at": "2020-01-01T00:00:00",
        },
        {
            "id": "3",
            "name": "other",
            "program_name": "secret-program",
            "description": "",
            "steps": [],
            "variables": {},
            "inputs": {},
            "created_at": "2020-01-01T00:00:00",
            "updated_at": "2020-01-01T00:00:00",
        },
    ]
    r = await client.get("/workflows/definitions")
    assert r.status_code == 200
    body = r.json()
    names = {w["name"] for w in body["workflows"]}
    assert "global" in names
    assert "in-a" in names
    assert "other" not in names


@pytest.mark.asyncio
async def test_create_workflow_definition_forbidden_not_manager(
    client: httpx.AsyncClient, mock_user_restricted
):
    """Viewer cannot create program-scoped definitions (manager required)."""
    payload = {
        "name": "wf1",
        "program_name": "program-a",
        "description": "",
        "steps": [{"name": "s", "tasks": []}],
        "variables": {},
        "inputs": {},
    }
    r = await client.post("/workflows/definitions", json=payload)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_global_workflow_forbidden_non_superuser(
    client: httpx.AsyncClient, mock_user_manager
):
    payload = {
        "name": "globalwf",
        "program_name": None,
        "description": "",
        "steps": [{"name": "s", "tasks": []}],
        "variables": {},
        "inputs": {},
    }
    r = await client.post("/workflows/definitions", json=payload)
    assert r.status_code == 403


@pytest.mark.asyncio
@patch("routes.workflows.workflow_definition_repository.create_workflow_definition", new_callable=AsyncMock)
@patch("routes.workflows.workflow_definition_repository.check_name_conflict", new_callable=AsyncMock)
async def test_create_workflow_definition_success(
    mock_conflict, mock_create, client: httpx.AsyncClient, mock_user_superuser
):
    mock_conflict.return_value = False
    mock_create.return_value = {
        "id": "wf-id",
        "name": "globalwf",
        "program_name": None,
        "description": "d",
        "steps": [],
        "variables": {},
        "inputs": {},
        "created_at": "2020-01-01T00:00:00",
        "updated_at": "2020-01-01T00:00:00",
    }
    payload = {
        "name": "globalwf",
        "program_name": None,
        "description": "d",
        "steps": [{"name": "step1", "tasks": []}],
        "variables": {},
        "inputs": {},
    }
    r = await client.post("/workflows/definitions", json=payload)
    assert r.status_code == 200
    assert r.json()["name"] == "globalwf"
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
@patch("routes.jobs.thread_pool")
@patch("routes.jobs.JobRepository.update_job_status", new_callable=AsyncMock)
@patch("routes.jobs.JobRepository.get_job_status", new_callable=AsyncMock)
async def test_stop_job_already_finished(
    mock_get_status, mock_update_status, mock_thread_pool, client: httpx.AsyncClient, mock_user_superuser
):
    mock_get_status.return_value = {
        "job_id": "job-1",
        "job_type": "phishlabs_batch",
        "status": "completed",
        "progress": 100,
        "message": "done",
    }
    r = await client.post("/jobs/job-1/stop")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "already_finished"
    mock_update_status.assert_not_awaited()
    mock_thread_pool.submit.assert_not_called()


@pytest.mark.asyncio
@patch("routes.jobs.thread_pool")
@patch("routes.jobs.JobRepository.update_job_status", new_callable=AsyncMock)
@patch("routes.jobs.JobRepository.get_job_status", new_callable=AsyncMock)
async def test_stop_job_starts_background_cleanup(
    mock_get_status, mock_update_status, mock_thread_pool, client: httpx.AsyncClient, mock_user_superuser
):
    mock_get_status.return_value = {
        "job_id": "job-2",
        "job_type": "gather_api_findings",
        "status": "running",
        "progress": 40,
        "message": "working",
    }
    mock_update_status.return_value = True

    r = await client.post("/jobs/job-2/stop")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "stopping"
    assert body["job_id"] == "job-2"

    mock_update_status.assert_awaited_once_with(
        "job-2",
        status="stopping",
        progress=40,
        message="Job is being stopped",
    )
    mock_thread_pool.submit.assert_called_once()


@pytest.mark.asyncio
@patch("routes.jobs.ScheduledJobRepository.finalize_running_execution_for_job", new_callable=AsyncMock)
@patch("routes.jobs.job_submission_service.delete_job")
@patch("routes.jobs.job_submission_service.get_batch_job_pod_logs")
@patch("routes.jobs.JobRepository.update_job_status", new_callable=AsyncMock)
@patch("routes.jobs.JobRepository.get_job_status", new_callable=AsyncMock)
async def test_stop_job_background_cleanup_posts_logs_and_stopped(
    mock_get_status,
    mock_update_status,
    mock_get_logs,
    mock_delete_job,
    mock_finalize_execution,
):
    mock_get_logs.return_value = "runner log line"
    mock_get_status.side_effect = [
        {"job_id": "job-3", "status": "running", "progress": 55, "message": "working"},
        {"job_id": "job-3", "status": "stopping", "progress": 55, "message": "stopping"},
    ]
    mock_update_status.return_value = True
    mock_finalize_execution.return_value = True

    from routes.jobs import _run_job_stop_cleanup

    await _run_job_stop_cleanup("job-3", "gather_api_findings", 55)

    mock_get_logs.assert_called_once_with("job-3")
    mock_delete_job.assert_called_once_with("job-3", job_type="gather_api_findings")
    mock_finalize_execution.assert_awaited_once_with("job-3")

    final_call = mock_update_status.await_args_list[-1]
    assert final_call.args[0] == "job-3"
    assert final_call.kwargs.get("status") == "stopped"
    assert final_call.kwargs.get("message") == "Job stopped by user"
