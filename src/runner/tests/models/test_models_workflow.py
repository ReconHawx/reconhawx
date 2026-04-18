"""Tests for ``models.workflow``."""

from __future__ import annotations

from models.workflow import (
    InputDefinition,
    Step,
    TaskDefinition,
    Workflow,
    WorkflowDefinition,
    WorkflowStep,
)


def test_task_definition_allows_extra_fields() -> None:
    t = TaskDefinition(name="resolve_ip", extra_thing=123)
    assert t.name == "resolve_ip"
    assert t.force is False


def test_input_definition_defaults_scope_filter_to_all() -> None:
    inp = InputDefinition(type="program_asset", asset_type="domain")
    assert inp.scope_domains_filter == "all"


def test_workflow_extracts_steps_from_definition() -> None:
    step = WorkflowStep(name="one", tasks=[TaskDefinition(name="resolve_ip")])
    definition = WorkflowDefinition(steps=[step])
    wf = Workflow(name="wf", steps=[Step(name="legacy", tasks=[])], definition=definition)

    assert len(wf.steps) == 1
    assert wf.steps[0].name == "one"


def test_workflow_keeps_original_steps_when_no_definition() -> None:
    wf = Workflow(name="wf", steps=[Step(name="legacy", tasks=[])])
    assert wf.steps[0].name == "legacy"
