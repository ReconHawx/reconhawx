"""Scheduled workflow execution seeds pending workflow_logs (WAF rerun chain ownership)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.job import CronSchedule, JobSchedule, JobType, ScheduledJobRequest, ScheduleType
from services.job_scheduler import JobSchedulerService


@pytest.mark.asyncio
@patch.object(JobSchedulerService, "_get_latest_execution_id", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_record_job_execution", new_callable=AsyncMock)
@patch("repository.job_repo.JobRepository.create_job", new_callable=AsyncMock)
@patch("repository.workflow_repo.WorkflowRepository.create_workflow_log", new_callable=AsyncMock)
@patch("repository.program_repo.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
@patch("services.kubernetes.KubernetesService")
async def test_scheduled_inline_workflow_seeds_pending_log_with_metadata(
    mock_k8s_cls,
    mock_get_prog,
    mock_create_log,
    mock_create_job,
    mock_record_exec,
    mock_get_exec_id,
):
    mock_get_exec_id.return_value = None
    mock_k8s_inst = MagicMock()
    mock_k8s_inst.create_runner_job = AsyncMock()
    mock_k8s_cls.return_value = mock_k8s_inst
    mock_get_prog.return_value = {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "name": "prog-a"}

    owner = uuid.UUID("aaaaaaaa-bbbb-bbbb-bbbb-cccccccccccc")
    job_row = {
        "job_data": {
            "variables": {},
            "inputs": {"x": {"type": "direct", "values": ["https://e.example/"], "value_type": "urls"}},
            "steps": [
                {
                    "name": "step_1",
                    "tasks": [
                        {
                            "name": "t1",
                            "task_type": "test_http",
                            "input_mapping": {"urls": "inputs.x"},
                        }
                    ],
                }
            ],
            "metadata": {
                "waf_rerun_attempt": 1,
                "parent_execution_id": "22222222-2222-2222-2222-222222222222",
                "source": "waf_auto_rerun",
            },
            "priority": "normal",
        },
        "workflow_variables": {},
        "program_names": ["prog-a"],
        "user_id": owner,
    }
    req = ScheduledJobRequest(
        job_type=JobType.WORKFLOW,
        job_data=job_row["job_data"],
        schedule=JobSchedule(
            schedule_type=ScheduleType.ONCE,
            start_time=datetime.now(timezone.utc),
            timezone="UTC",
            enabled=True,
        ),
        name="WAF rerun",
        program_name="prog-a",
    )
    svc = JobSchedulerService()
    await svc._execute_multi_program_workflow("sched-test", req, job_row)

    mock_create_job.assert_not_awaited()
    mock_create_log.assert_awaited_once()
    pending = mock_create_log.await_args.args[0]
    assert pending["user_id"] == str(owner)
    assert pending["result"] == "pending"
    assert pending["workflow_steps"] == []
    wd = pending["workflow_definition"]
    assert wd["metadata"]["waf_rerun_attempt"] == 1
    assert wd["metadata"]["parent_execution_id"] == "22222222-2222-2222-2222-222222222222"
    assert wd["priority"] == "normal"
    assert wd["program_name"] == "prog-a"
    assert str(wd["program_id"]) == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
@patch.object(JobSchedulerService, "delete_scheduled_job", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_monitor_job_completion", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_get_latest_execution_id", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_record_job_execution", new_callable=AsyncMock)
@patch("repository.job_repo.JobRepository.create_job", new_callable=AsyncMock)
@patch("repository.workflow_repo.WorkflowRepository.create_workflow_log", new_callable=AsyncMock)
@patch("repository.program_repo.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
@patch("services.kubernetes.KubernetesService")
async def test_waf_once_workflow_deleted_after_runner_monitor_finishes(
    mock_k8s_cls,
    mock_get_prog,
    mock_create_log,
    mock_create_job,
    mock_record_exec,
    mock_get_exec_id,
    mock_monitor,
    mock_delete_scheduled,
):
    mock_get_exec_id.return_value = "hist-exec-0001"
    mock_monitor.return_value = True

    mock_k8s_inst = MagicMock()
    mock_k8s_inst.create_runner_job = AsyncMock()
    mock_k8s_cls.return_value = mock_k8s_inst
    mock_get_prog.return_value = {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "name": "prog-a"}

    owner = uuid.UUID("aaaaaaaa-bbbb-bbbb-bbbb-cccccccccccc")
    job_row = {
        "job_type": JobType.WORKFLOW.value,
        "tags": ["waf_auto_rerun", "parent:22222222-2222-2222-2222-222222222222"],
        "schedule_data": {
            "schedule_type": ScheduleType.ONCE.value,
            "timezone": "UTC",
            "enabled": True,
        },
        "job_data": {
            "variables": {},
            "inputs": {},
            "steps": [
                {
                    "name": "step_1",
                    "tasks": [
                        {
                            "name": "t1",
                            "task_type": "test_http",
                            "input_mapping": {"urls": "inputs.x"},
                        }
                    ],
                }
            ],
            "metadata": {"waf_rerun_attempt": 1},
            "priority": "normal",
        },
        "workflow_variables": {},
        "program_names": ["prog-a"],
        "user_id": owner,
    }
    req = ScheduledJobRequest(
        job_type=JobType.WORKFLOW,
        job_data=job_row["job_data"],
        schedule=JobSchedule(
            schedule_type=ScheduleType.ONCE,
            start_time=datetime.now(timezone.utc),
            timezone="UTC",
            enabled=True,
        ),
        name="WAF rerun",
        program_name="prog-a",
        tags=job_row["tags"],
    )
    svc = JobSchedulerService()
    await svc._execute_multi_program_workflow("sched-del-waf", req, job_row)

    mock_create_job.assert_not_awaited()
    mock_delete_scheduled.assert_awaited_once_with("sched-del-waf")
    mock_monitor.assert_awaited_once()


@pytest.mark.asyncio
@patch.object(JobSchedulerService, "delete_scheduled_job", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_monitor_job_completion", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_get_latest_execution_id", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_update_scheduled_job_status", new_callable=AsyncMock)
@patch.object(JobSchedulerService, "_record_job_execution", new_callable=AsyncMock)
@patch("repository.job_repo.JobRepository.create_job", new_callable=AsyncMock)
@patch("repository.workflow_repo.WorkflowRepository.create_workflow_log", new_callable=AsyncMock)
@patch("repository.program_repo.ProgramRepository.get_program_by_name", new_callable=AsyncMock)
@patch("repository.WorkflowDefinitionRepository")
@patch("services.kubernetes.KubernetesService")
async def test_non_waf_scheduled_workflow_not_deleted_after_monitor(
    mock_k8s_cls,
    mock_wf_def_repo_cls,
    mock_get_prog,
    mock_create_log,
    mock_create_job,
    mock_record_exec,
    mock_update_status,
    mock_get_exec_id,
    mock_monitor,
    mock_delete_scheduled,
):
    mock_get_exec_id.return_value = "hist-exec-0002"
    mock_monitor.return_value = True
    wf_uuid = uuid.UUID("33333333-3333-3333-3333-333333333333")

    mock_wf_def_repo = MagicMock()
    mock_wf_def_repo.get_workflow_definition = AsyncMock(
        return_value={
            "name": "Saved WF",
            "description": "d",
            "variables": {},
            "inputs": {},
            "steps": [
                {
                    "name": "step_1",
                    "tasks": [{"name": "t1", "task_type": "test_http", "input_mapping": {}}],
                },
            ],
        }
    )
    mock_wf_def_repo_cls.return_value = mock_wf_def_repo

    mock_k8s_inst = MagicMock()
    mock_k8s_inst.create_runner_job = AsyncMock()
    mock_k8s_cls.return_value = mock_k8s_inst
    mock_get_prog.return_value = {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "name": "prog-a"}

    owner = uuid.UUID("aaaaaaaa-bbbb-bbbb-bbbb-cccccccccccc")
    job_row = {
        "job_type": JobType.WORKFLOW.value,
        "tags": [],
        "schedule_data": {"schedule_type": ScheduleType.CRON.value},
        "job_data": {"workflow_id": str(wf_uuid), "workflow_variables": {}},
        "workflow_variables": {},
        "program_names": ["prog-a"],
        "user_id": owner,
    }
    req = ScheduledJobRequest(
        job_type=JobType.WORKFLOW,
        job_data=job_row["job_data"],
        schedule=JobSchedule(
            schedule_type=ScheduleType.CRON,
            cron_schedule=CronSchedule(),
            timezone="UTC",
            enabled=True,
        ),
        name="Daily",
        program_name="prog-a",
    )
    svc = JobSchedulerService()
    await svc._execute_multi_program_workflow("sched-keep-me", req, job_row)

    mock_create_job.assert_not_awaited()
    mock_delete_scheduled.assert_not_called()
    mock_update_status.assert_awaited()
