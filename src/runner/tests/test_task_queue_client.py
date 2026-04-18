"""Tests for ``TaskQueueClient`` constructor / pure helpers.

The setup/listen/process_output methods interact with NATS JetStream and are
covered through integration; this file pins down the environment-variable
contract and derived state.
"""

from __future__ import annotations

import pytest


def test_task_queue_client_requires_execution_id(monkeypatch) -> None:
    monkeypatch.delenv("EXECUTION_ID", raising=False)
    from task_queue_client import TaskQueueClient

    with pytest.raises(ValueError, match="EXECUTION_ID"):
        TaskQueueClient()


def test_task_queue_client_builds_workflow_output_subject(monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_ID", "exec-123")
    monkeypatch.setenv("WORKFLOW_ID", "wf-7")
    monkeypatch.setenv("OUTPUT_QUEUE_SUBJECT", "tasks.output")

    import importlib
    import task_queue_client as mod

    importlib.reload(mod)
    client = mod.TaskQueueClient()
    assert client.execution_id == "exec-123"
    assert client.workflow_id == "wf-7"
    assert client.workflow_output_subject == "tasks.output.exec-123"
    assert client.consumer_name.startswith("runner-")
    assert client.nc is None
    assert client.js is None
    assert client.running is False
    assert client.task_outputs == {}
    assert client.task_chunks == {}
