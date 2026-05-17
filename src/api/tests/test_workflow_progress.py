"""Tests for workflow execution task-level progress counting."""

from routes.workflows import _compute_workflow_progress, transform_workflow_executions_for_status_list


def _wf_def_two_steps():
    return {
        "name": "wf",
        "steps": [
            {"name": "s1", "tasks": [{"name": "t1"}, {"name": "t2"}]},
            {"name": "s2", "tasks": [{"name": "t3"}, {"name": "t4"}, {"name": "t5"}]},
        ],
    }


def test_progress_started_only_task_not_counted():
    """Runner POSTs task logs only when a task finishes; in-flight rows must not count."""
    ex = {
        "result": "running",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": [
            {"task_name": "t1", "status": "running", "started_at": "2026-01-01T00:00:00Z"},
        ],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 0
    assert p["total"] == 5


def test_progress_no_logs_running():
    ex = {
        "result": "running",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": [],
        "workflow_steps": [],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 0
    assert p["total"] == 5
    assert p["percentage"] == 0.0


def test_progress_partial_three_tasks_done():
    logs = [
        {
            "step_name": "s1",
            "task_name": "t1",
            "status": "success",
            "completed_at": "2026-01-01T00:00:01Z",
        },
        {
            "step_name": "s1",
            "task_name": "t2",
            "status": "success",
            "completed_at": "2026-01-01T00:00:02Z",
        },
        {
            "step_name": "s2",
            "task_name": "t3",
            "status": "success",
            "completed_at": "2026-01-01T00:00:03Z",
        },
    ]
    ex = {
        "result": "running",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": logs,
        "workflow_steps": [],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 3
    assert p["total"] == 5
    assert abs(p["percentage"] - 60.0) < 1e-9


def test_progress_terminal_success_sparse_logs():
    ex = {
        "result": "success",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": [],
        "workflow_steps": [],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 5
    assert p["total"] == 5
    assert p["percentage"] == 100.0


def test_progress_terminal_completed_alias():
    ex = {
        "result": "completed",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": [{"task_name": "t1", "status": "success"}],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 5
    assert p["total"] == 5


def test_progress_terminal_failed_keeps_partial():
    logs = [
        {"task_name": "t1", "status": "success", "completed_at": "2026-01-01T00:00:01Z"},
        {"task_name": "t2", "status": "success", "completed_at": "2026-01-01T00:00:02Z"},
    ]
    ex = {
        "result": "failed",
        "workflow_definition": _wf_def_two_steps(),
        "task_execution_logs": logs,
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 2
    assert p["total"] == 5


def test_progress_legacy_no_definition_workflow_steps_fallback():
    ex = {
        "result": "running",
        "workflow_definition": None,
        "task_execution_logs": [],
        "workflow_steps": [{"step_a": {}}, {"step_b": {}}],
    }
    p = _compute_workflow_progress(ex)
    assert p["completed"] == 0
    assert p["total"] == 2


def test_transform_list_wraps_progress():
    executions = [
        {
            "execution_id": "e1",
            "workflow_name": "w",
            "program_name": "p",
            "result": "running",
            "created_at": None,
            "workflow_definition": _wf_def_two_steps(),
            "task_execution_logs": [],
            "workflow_steps": [],
        }
    ]
    out = transform_workflow_executions_for_status_list(executions)
    assert len(out) == 1
    assert out[0]["progress"]["total"] == 5
    assert out[0]["progress"]["completed"] == 0
