"""Tests for ``worker_job_manager`` pure helpers and data classes.

The K8s / NATS spawn paths are network-bound; this file unit-tests the
deterministic helpers: JobResult, BatchResult, and WorkerJobManager name /
param construction.
"""

from __future__ import annotations

import pytest

from worker_job_manager import BatchResult, JobResult, WorkerJobManager


def test_job_result_status_helpers() -> None:
    jr = JobResult("tid", "job", status="pending")
    assert jr.is_completed is False
    assert jr.is_successful is False
    jr.status = "completed"
    assert jr.is_completed is True
    assert jr.is_successful is False
    jr.output = "hi"
    assert jr.is_successful is True


def test_job_result_duration() -> None:
    jr = JobResult("tid", "job")
    assert jr.duration is None
    jr.start_time = 100.0
    jr.end_time = 103.5
    assert jr.duration == pytest.approx(3.5)


def test_batch_result_aggregates_stats() -> None:
    batch = BatchResult("b-1")
    a = JobResult("a", "j", status="completed")
    a.output = "x"
    b = JobResult("b", "j", status="failed")
    c = JobResult("c", "j", status="timeout")
    d = JobResult("d", "j", status="pending")
    for j in (a, b, c, d):
        batch.add_job(j)

    assert batch.total_jobs == 4
    assert batch.completed_jobs == 3
    assert batch.successful_jobs == 1
    assert batch.failed_jobs == 2
    assert batch.is_completed is False
    assert batch.success_rate == 0.25


def test_batch_result_empty_success_rate() -> None:
    assert BatchResult("b").success_rate == 1.0


@pytest.fixture
def mgr(monkeypatch) -> WorkerJobManager:
    monkeypatch.setenv("WORKFLOW_ID", "wf-1")
    monkeypatch.setenv("EXECUTION_ID", "exec-1")
    monkeypatch.setenv("PROGRAM_NAME", "prog")
    return WorkerJobManager(task_queue_client=object(), k8s_service=object())


@pytest.mark.parametrize(
    "given,expected",
    [
        ("resolve_ip", "resolve-ip"),
        ("  BAD_Name!!  ", "bad-name"),
        ("123-start", "job-123-start"),
        ("---", "job"),
        ("", "job"),
    ],
)
def test_make_rfc1123_compliant(mgr: WorkerJobManager, given: str, expected: str) -> None:
    assert mgr._make_rfc1123_compliant(given) == expected


def test_build_job_params_injects_required_env(mgr: WorkerJobManager, monkeypatch) -> None:
    monkeypatch.setenv("WORKER_IMAGE", "worker:0.1")
    params = mgr._build_job_params("resolve_ip", "echo hi", timeout=60, step_num=3)
    assert params["task_name"] == "resolve-ip"
    assert params["timeout"] == 60
    assert params["step_num"] == 3
    assert params["image"] == "worker:0.1"
    assert params["workflow_id"] == "exec-1"

    env_by_name = {e["name"]: e["value"] for e in params["env"]}
    assert env_by_name["OUTPUT_QUEUE_SUBJECT"] == "tasks.output.exec-1"
    assert env_by_name["EXECUTION_ID"] == "exec-1"
    assert env_by_name["WORKFLOW_ID"] == "wf-1"
    assert env_by_name["PROGRAM_NAME"] == "prog"


def test_build_job_params_preserves_existing_env(mgr: WorkerJobManager) -> None:
    params = mgr._build_job_params(
        "resolve_ip", "echo hi", env=[{"name": "PROGRAM_NAME", "value": "override"}]
    )
    env_by_name = {e["name"]: e["value"] for e in params["env"]}
    assert env_by_name["PROGRAM_NAME"] == "override"
