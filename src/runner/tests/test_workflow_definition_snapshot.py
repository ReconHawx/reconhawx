"""Tests for ``workflow_definition_snapshot`` (runner log payloads)."""

from __future__ import annotations

import sys
from pathlib import Path

_runner_app_dir = str(Path(__file__).resolve().parents[1] / "app")
if _runner_app_dir not in sys.path:
    sys.path.insert(0, _runner_app_dir)

from workflow_definition_snapshot import serialize_workflow_definition_snapshot


class _FakeTask:
    name = "t1"
    task_type = "test_http"
    params = {}
    input_mapping = None
    output_mode = None
    use_proxy = None


class _FakeStep:
    name = "s1"
    tasks = [_FakeTask()]


class _FakeWf:
    name = "wf1"
    description = None
    inputs = {}
    variables = {"k": "v"}
    steps = [_FakeStep()]


class TestSerializeWorkflowDefinitionMetadata:
    def test_merges_metadata_and_priority_from_raw_payload(self) -> None:
        raw = {
            "metadata": {"waf_rerun_attempt": 2, "parent_execution_id": "parent-uuid"},
            "priority": "high",
        }
        out = serialize_workflow_definition_snapshot(_FakeWf(), raw)
        assert out["metadata"] == raw["metadata"]
        assert out["priority"] == "high"
        assert out["name"] == "wf1"
        assert out["variables"] == {"k": "v"}

    def test_omitted_when_payload_has_no_extra_fields(self) -> None:
        wf = _FakeWf()
        wf.variables = {}
        out = serialize_workflow_definition_snapshot(wf, {})
        assert "metadata" not in out
        assert "priority" not in out

    def test_none_payload_safe(self) -> None:
        wf = _FakeWf()
        wf.variables = {}
        out = serialize_workflow_definition_snapshot(wf, None)
        assert "metadata" not in out
