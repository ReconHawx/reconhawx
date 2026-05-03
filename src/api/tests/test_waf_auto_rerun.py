"""Tests for ``services.waf_auto_rerun``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.waf_auto_rerun as war
from models.job import JobSchedule, JobType, ScheduleType, ScheduledJobRequest
from services.job_scheduler import JobSchedulerService
from services.workflow_waf_auto_rerun_settings import CANONICAL_DEFAULTS


@pytest.fixture
def mock_waf_effective_policy():
    with patch(
        "services.workflow_waf_auto_rerun_settings.get_workflow_waf_auto_rerun_effective",
        new_callable=AsyncMock,
    ) as m:
        m.return_value = {
            **dict(CANONICAL_DEFAULTS),
            "max_attempts": 10,
            "delay_seconds": 90,
        }
        yield m


@pytest.fixture
def base_waf_log() -> dict:
    exec_id = "11111111-1111-1111-1111-111111111111"
    return {
        "execution_id": exec_id,
        "program_name": "program-a",
        "user_id": "aaaaaaaa-bbbb-bbbb-bbbb-cccccccccccc",
        "workflow_name": "WF",
        "result": "partial_waf",
        "workflow_definition": {
            "name": "Parent WF",
            "variables": {},
            "inputs": {},
            "priority": "normal",
            "metadata": {},
            "steps": [
                {
                    "name": "HeavyStep",
                    "tasks": [
                        {
                            "name": "c1",
                            "task_type": "crawl_website",
                            "input_mapping": {"urls": "inputs.src"},
                        }
                    ],
                }
            ],
        },
        "workflow_steps": [
            {
                "HeavyStep": {
                    "total_assets": 0,
                    "waf_status": {
                        "skipped_originals": [
                            "https://a.example/x",
                            "https://b.example/y",
                        ],
                    },
                }
            }
        ],
    }


@pytest.mark.asyncio
@patch(
    "repository.program_repo.ProgramRepository.get_program_by_name",
    new_callable=AsyncMock,
)
@patch(
    "services.job_scheduler.scheduler_service.create_scheduled_job",
    new_callable=AsyncMock,
)
async def test_partial_waf_schedules_inline_workflow_no_workflow_id(
    mock_sched: AsyncMock,
    mock_prog: AsyncMock,
    base_waf_log: dict,
    mock_waf_effective_policy: AsyncMock,
):
    mock_prog.return_value = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
    mock_sched.return_value = MagicMock(schedule_id="sched-abc")

    sid = await war.maybe_schedule_waf_rerun(base_waf_log)
    assert sid == "sched-abc"
    mock_sched.assert_awaited_once()
    req = mock_sched.await_args.args[0]
    assert req.job_type.value == "workflow"
    assert req.job_data.get("workflow_id") is None
    assert len(req.job_data["steps"]) == 1
    slot = "__waf_rerun_HeavyStep_c1_urls"
    assert req.job_data["inputs"][slot]["type"] == "direct"
    assert req.job_data["inputs"][slot]["values"] == [
        "https://a.example/x",
        "https://b.example/y",
    ]
    assert req.job_data["steps"][0]["tasks"][0]["input_mapping"]["urls"] == f"inputs.{slot}"
    assert "waf_auto_rerun" in req.tags
    assert f"parent:{base_waf_log['execution_id']}" in req.tags
    root = base_waf_log["execution_id"]
    assert f"chain_root:{root}" in req.tags
    assert req.job_data["metadata"]["root_execution_id"] == root


@pytest.mark.asyncio
@patch(
    "repository.scheduled_job_repo.ScheduledJobRepository.has_pending_waf_rerun_conflict",
    new_callable=AsyncMock,
)
@patch(
    "repository.program_repo.ProgramRepository.get_program_by_name",
    new_callable=AsyncMock,
)
@patch(
    "services.job_scheduler.scheduler_service.create_scheduled_job",
    new_callable=AsyncMock,
)
async def test_maybe_schedule_skipped_when_pending_chain_conflict(
    mock_sched: AsyncMock,
    mock_prog: AsyncMock,
    mock_conflict: AsyncMock,
    base_waf_log: dict,
    mock_waf_effective_policy: AsyncMock,
):
    mock_prog.return_value = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
    mock_conflict.return_value = True

    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None
    mock_sched.assert_not_called()
    mock_conflict.assert_awaited_once()
    base_waf_log["result"] = "success"
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
@patch(
    "repository.scheduled_job_repo.ScheduledJobRepository.has_pending_waf_rerun_conflict",
    new_callable=AsyncMock,
)
@patch(
    "repository.program_repo.ProgramRepository.get_program_by_name",
    new_callable=AsyncMock,
)
@patch(
    "services.job_scheduler.scheduler_service.create_scheduled_job",
    new_callable=AsyncMock,
)
async def test_chain_root_carried_from_metadata(
    mock_sched: AsyncMock,
    mock_prog: AsyncMock,
    mock_conflict: AsyncMock,
    base_waf_log: dict,
    mock_waf_effective_policy: AsyncMock,
):
    mock_prog.return_value = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
    mock_sched.return_value = MagicMock(schedule_id="sched-xyz")
    mock_conflict.return_value = False

    outer = "99999999-9999-9999-9999-999999999999"
    base_waf_log["execution_id"] = "88888888-8888-8888-8888-888888888888"
    base_waf_log["workflow_definition"]["metadata"] = {
        "waf_rerun_attempt": 1,
        "root_execution_id": outer,
    }

    sid = await war.maybe_schedule_waf_rerun(base_waf_log)
    assert sid == "sched-xyz"
    req = mock_sched.await_args.args[0]
    assert f"chain_root:{outer}" in req.tags
    assert req.job_data["metadata"]["root_execution_id"] == outer


@pytest.mark.asyncio
async def test_missing_user_id(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    base_waf_log.pop("user_id", None)
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
async def test_waf_auto_rerun_off(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    mock_waf_effective_policy.return_value = {
        **dict(CANONICAL_DEFAULTS),
        "enabled": False,
        "max_attempts": 3,
    }
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


@pytest.mark.asyncio
async def test_max_attempts_blocks(base_waf_log: dict, mock_waf_effective_policy: AsyncMock):
    mock_waf_effective_policy.return_value = {
        **dict(CANONICAL_DEFAULTS),
        "max_attempts": 1,
    }
    base_waf_log["workflow_definition"]["metadata"] = {"waf_rerun_attempt": 1}
    assert await war.maybe_schedule_waf_rerun(base_waf_log) is None


def test_extract_waf_targets_prefers_top_level_waf_status() -> None:
    steps = [
        {
            "step_1": {
                "waf_status": {"skipped_originals": ["https://x.example/"]},
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"step_1": ["https://x.example/"]}


def test_extract_waf_targets_nested_status_fallback() -> None:
    steps = [
        {
            "S": {
                "status": {"waf_status": {"skipped_originals": ["https://nested/"]}},
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"S": ["https://nested/"]}


def test_extract_waf_targets_blocked_keys_fallback() -> None:
    steps = [
        {
            "S": {
                "waf_status": {
                    "skipped": "waf_all_nodes_blocked",
                    "blocked_all_nodes_keys": ["https://k1"],
                },
            },
        },
    ]
    assert war._extract_waf_targets_by_step(steps) == {"S": ["https://k1"]}


def _make_once_workflow_request(tags: list[str] | None, start_time: datetime | None) -> ScheduledJobRequest:
    return ScheduledJobRequest(
        job_type=JobType.WORKFLOW,
        job_data={"workflow_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "workflow_variables": {}},
        schedule=JobSchedule(
            schedule_type=ScheduleType.ONCE,
            start_time=start_time,
            timezone="UTC",
            enabled=True,
        ),
        name="Test once job",
        description="",
        program_name="prog",
        tags=list(tags) if tags is not None else [],
    )


@pytest.mark.asyncio
async def test_waf_once_schedule_passes_unbounded_misfire_grace() -> None:
    svc = JobSchedulerService()
    start = datetime.now(timezone.utc) + timedelta(minutes=45)
    req = _make_once_workflow_request(tags=["waf_auto_rerun"], start_time=start)

    with patch.object(svc.scheduler, "add_job") as mock_add:
        await svc._schedule_job("sched-waf-1", req)

    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["misfire_grace_time"] is None


@pytest.mark.asyncio
async def test_non_waf_once_schedule_omits_misfire_grace_kwarg() -> None:
    svc = JobSchedulerService()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    req = _make_once_workflow_request(tags=[], start_time=start)

    with patch.object(svc.scheduler, "add_job") as mock_add:
        await svc._schedule_job("sched-generic-1", req)

    mock_add.assert_called_once()
    assert "misfire_grace_time" not in mock_add.call_args.kwargs
