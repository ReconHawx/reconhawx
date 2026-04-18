"""Tests for ``services.kubernetes.KubernetesService``.

Kubernetes client is patched to avoid config loading; we verify pod-log
selectors, job-status mapping, and job-CRD generation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def svc(monkeypatch):
    import services.kubernetes as k8s

    monkeypatch.setattr(k8s.config, "load_incluster_config", lambda: None)
    monkeypatch.setattr(k8s.config, "load_kube_config", lambda: None)
    monkeypatch.setattr(k8s.client, "BatchV1Api", MagicMock)
    monkeypatch.setattr(k8s.client, "CoreV1Api", MagicMock)
    monkeypatch.setenv("KUBERNETES_NAMESPACE", "recon-test")
    service = k8s.KubernetesService()
    return service


def test_get_pod_logs_rejects_invalid_type(svc) -> None:
    assert svc.get_pod_logs("invalid", "x") == "Invalid pod type. Must be runner or worker"


def test_get_pod_logs_returns_message_when_no_pods(svc) -> None:
    svc.core_api.list_namespaced_pod = MagicMock(return_value=MagicMock(items=[]))
    assert svc.get_pod_logs("worker", "abc") == "No pods found"


def test_get_pod_logs_uses_correct_selector(svc) -> None:
    mock_list = MagicMock(return_value=MagicMock(items=[]))
    svc.core_api.list_namespaced_pod = mock_list
    svc.get_pod_logs("runner", "wf-1")
    _, kwargs = mock_list.call_args
    assert kwargs["label_selector"] == "app=runner,workflow-id=wf-1"


def test_get_job_status_maps_running(svc) -> None:
    status = MagicMock(active=1, failed=None, succeeded=None)
    svc.batch_api.read_namespaced_job_status = MagicMock(return_value=MagicMock(status=status))
    assert svc.get_job_status("worker", "abc") == "Running"


def test_get_job_status_maps_completed(svc) -> None:
    status = MagicMock(active=None, failed=None, succeeded=1)
    svc.batch_api.read_namespaced_job_status = MagicMock(return_value=MagicMock(status=status))
    assert svc.get_job_status("worker", "abc") == "Completed"


def test_get_job_status_maps_timeout_vs_failed(svc) -> None:
    cond = MagicMock(reason="DeadlineExceeded")
    status = MagicMock(active=None, failed=1, succeeded=None, conditions=[cond])
    svc.batch_api.read_namespaced_job_status = MagicMock(return_value=MagicMock(status=status))
    assert svc.get_job_status("worker", "abc") == "TimedOut"

    cond.reason = "BackoffLimitExceeded"
    assert svc.get_job_status("worker", "abc") == "Failed"


def test_get_job_status_returns_completed_on_404(svc) -> None:
    import services.kubernetes as k8s

    err = k8s.ApiException(status=404, reason="Not Found")
    svc.batch_api.read_namespaced_job_status = MagicMock(side_effect=err)
    assert svc.get_job_status("worker", "abc") == "Completed"


def test_generate_job_crd_sets_labels_and_env(svc, monkeypatch) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")

    job_params = {
        "job_id": "job-1",
        "workflow_id": "wf-1",
        "workflow_name": "my-wf",
        "program_name": "prog",
        "task_name": "resolve_ip",
        "step_num": 1,
        "step_name": "resolve",
        "args": ["echo hello"],
        "image": "ghcr.io/org/worker:latest",
        "job_name": "worker-container",
        "timeout": 1200,
    }
    crd = svc.generate_job_crd(job_params)
    assert crd.metadata.name == "worker-job-1"
    assert crd.metadata.labels["task-id"] == "job-1"
    assert crd.metadata.labels["kueue.x-k8s.io/queue-name"] == "recon-worker-queue"
    assert crd.spec.active_deadline_seconds == 1200
    assert crd.spec.suspend is True

    container = crd.spec.template.spec.containers[0]
    assert container.image == "ghcr.io/org/worker:latest"
    assert container.command[:2] == ["sh", "-c"]
    env_by_name = {e.name: e.value for e in container.env}
    assert env_by_name["TASK_ID"] == "job-1"
    assert env_by_name["OUTPUT_QUEUE_SUBJECT"] == "tasks.output.wf-1"
    assert env_by_name["WORKFLOW_ID"] == "wf-1"
    assert env_by_name["STEP_NUM"] == "1"


def test_generate_job_crd_quotes_commands_with_pipes(svc) -> None:
    params = {
        "job_id": "j",
        "workflow_id": "w",
        "workflow_name": "n",
        "program_name": "p",
        "task_name": "t",
        "step_num": 0,
        "step_name": "s",
        "args": ["echo hi | grep h"],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
    }
    crd = svc.generate_job_crd(params)
    cmd = crd.spec.template.spec.containers[0].command[2]
    assert "'echo hi | grep h'" in cmd
