"""Tests for ``services.kubernetes.KubernetesService``.

Kubernetes client is patched to avoid config loading; we verify pod-log
selectors, job-status mapping, and job-CRD generation.
"""

from __future__ import annotations

import re
import shlex
from unittest.mock import MagicMock

import pytest

import services.kubernetes as k8s_mod


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
        "program_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
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
    assert crd.metadata.labels.get("program-id") == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert "program-name" not in crd.metadata.labels
    assert crd.metadata.annotations.get("reconhawx.io/program-name") == "prog"
    assert crd.metadata.labels["kueue.x-k8s.io/queue-name"] == "recon-worker-queue"
    assert crd.spec.active_deadline_seconds == 1200
    assert crd.spec.suspend is True

    container = crd.spec.template.spec.containers[0]
    assert container.image == "ghcr.io/org/worker:latest"
    assert container.command[:2] == ["sh", "-c"]
    env_by_name = {e.name: e.value for e in container.env}
    downward = [
        e
        for e in container.env
        if getattr(e, "value_from", None) and getattr(e.value_from, "field_ref", None)
    ]
    node_env = next((e for e in downward if e.name == "NODE_NAME"), None)
    pod_env = next((e for e in downward if e.name == "POD_NAME"), None)
    assert node_env is not None and node_env.value_from.field_ref.field_path == "spec.nodeName"
    assert pod_env is not None and pod_env.value_from.field_ref.field_path == "metadata.name"

    assert env_by_name["TASK_ID"] == "job-1"
    assert env_by_name["OUTPUT_QUEUE_SUBJECT"] == "tasks.output.wf-1"
    assert env_by_name["WORKFLOW_ID"] == "wf-1"
    assert env_by_name["PROGRAM_NAME"] == "prog"
    assert env_by_name["STEP_NUM"] == "1"
    assert env_by_name["LOG_FORMAT"] == "json"
    assert env_by_name["LOG_LEVEL"] == "INFO"
    tpl = crd.spec.template.metadata
    assert tpl.labels.get("program-id") == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert tpl.annotations.get("reconhawx.io/program-name") == "prog"


def test_generate_job_crd_escapes_worker_shell_command_with_shlex(svc, monkeypatch) -> None:
    """Embedded ``'`` (heredoc / ``-fs``) must not break ``sh -c``; see worker Job + httpx."""
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")
    shell_like = "cat << 'EOF' | httpx -p 'a&b|c' -fs 'plain text'\nhost\nEOF"
    job_params = {
        "job_id": "jq-1",
        "workflow_id": "wf-q",
        "workflow_name": "w",
        "program_name": "p",
        "task_name": "t",
        "step_num": 0,
        "step_name": "s",
        "args": [shell_like],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
    }
    crd = svc.generate_job_crd(job_params)
    quoted = shlex.quote(shell_like)
    assert crd.spec.template.spec.containers[0].command[2].endswith(quoted)


def test_sanitize_k8s_label_value_removes_spaces() -> None:
    out = k8s_mod._sanitize_k8s_label_value("Single Task Run - resolve_domain")
    assert " " not in out
    assert re.match(r"^[A-Za-z0-9].*[A-Za-z0-9]$", out)
    assert len(out) <= 63


def test_generate_job_crd_workflow_name_with_spaces_is_valid_label(svc, monkeypatch) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")
    job_params = {
        "job_id": "j-ws",
        "workflow_id": "wf-ws",
        "workflow_name": "Single Task Run - resolve_domain",
        "program_name": "prog",
        "task_name": "resolve_domain",
        "step_num": 0,
        "step_name": "step 1 / test",
        "args": ["echo hi"],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
    }
    crd = svc.generate_job_crd(job_params)
    for k, v in crd.metadata.labels.items():
        assert len(v) <= 63, k
        if v:
            assert re.match(r"^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$", v), (k, v)
    for k, v in crd.spec.template.metadata.labels.items():
        assert len(v) <= 63, k
        if v:
            assert re.match(r"^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$", v), (k, v)


def test_generate_job_crd_long_program_name_not_in_labels(svc) -> None:
    long_name = "YWH_programme-prive-de-prime-aux-bogues-du-gouvernement-du-quebec"
    pid = "90c18002-e669-4bd8-a9f5-b7ecbb439b2f"
    job_params = {
        "job_id": "job-2",
        "workflow_id": "wf-2",
        "workflow_name": "wf",
        "program_name": long_name,
        "program_id": pid,
        "task_name": "t",
        "step_num": 0,
        "step_name": "s",
        "args": ["echo hi"],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
    }
    crd = svc.generate_job_crd(job_params)
    assert "program-name" not in crd.metadata.labels
    assert all(len(v) <= 63 for v in crd.metadata.labels.values())
    assert crd.metadata.annotations["reconhawx.io/program-name"] == long_name
    assert crd.spec.template.metadata.labels.get("program-id") == pid


def test_generate_job_crd_extra_env_list_merged(svc, monkeypatch) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")
    job_params = {
        "job_id": "jx",
        "workflow_id": "wf-x",
        "workflow_name": "w",
        "program_name": "p",
        "task_name": "t",
        "step_num": 0,
        "step_name": "s",
        "args": ["echo hi"],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
        "env": [{"name": "CUSTOM_WAF_PROBE", "value": "x"}],
    }
    crd = svc.generate_job_crd(job_params)
    env_names = {(e.name, e.value) for e in crd.spec.template.spec.containers[0].env}
    assert ("CUSTOM_WAF_PROBE", "x") in env_names


def test_generate_job_crd_excluded_nodes_sets_affinity(svc, monkeypatch) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")
    job_params = {
        "job_id": "jx",
        "workflow_id": "wf-x",
        "workflow_name": "w",
        "program_name": "p",
        "task_name": "t",
        "step_num": 0,
        "step_name": "s",
        "args": ["echo hi"],
        "image": "img",
        "job_name": "jn",
        "timeout": 60,
        "excluded_nodes": ["node-a", "node-b"],
    }
    crd = svc.generate_job_crd(job_params)
    aff = crd.spec.template.spec.affinity
    assert aff is not None
    term = (
        aff.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms[0]
    )
    expr = term.match_expressions[0]
    assert expr.operator == "NotIn"
    assert expr.key == k8s_mod.WAF_NODE_AFFINITY_KEY
    assert set(expr.values) == {"node-a", "node-b"}


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
