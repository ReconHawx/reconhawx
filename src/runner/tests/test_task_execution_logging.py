"""Tests for per-target task execution logging (executed_input_data)."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from task_executor import TaskExecutor


def _load_run_workflow_module():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    path = app_dir / "run-workflow.py"
    spec = importlib.util.spec_from_file_location("_run_workflow_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTaskExecutedInputTracking:
    def test_record_and_get_executed_input_per_step_task(self) -> None:
        executor = TaskExecutor.__new__(TaskExecutor)
        executor._task_executed_input_by_key = {}
        executor._record_task_executed_input("step_a", "test_http", ["a.example"])
        executor._record_task_executed_input("step_a", "nuclei_scan", [])
        assert executor.get_task_executed_input("step_a", "test_http") == ["a.example"]
        assert executor.get_task_executed_input("step_a", "nuclei_scan") == []
        assert executor.get_task_executed_input("step_b", "test_http") == []


@pytest.mark.asyncio
async def test_log_task_execution_skipped_when_no_executed_targets() -> None:
    mod = _load_run_workflow_module()
    task_def = MagicMock()
    task_def.name = "test_http"
    task_def.task_type = "test_http"
    task_def.params = {}

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)

    with patch.object(mod.requests, "post") as mock_post:
        await mod._log_task_execution(
            execution_id="exec-1",
            program_id="prog-1",
            program_name="prog",
            step_name="step1",
            task_def=task_def,
            task_start_time=start,
            task_end_time=end,
            executed_input_data=[],
            output={},
            status="skipped",
        )

    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    entry = payload["task_execution_logs"][0]
    assert entry["status"] == "skipped"
    assert entry["input_count"] == 0
    assert entry["input_data"] == []
    assert entry["executed_input_data"] == []
