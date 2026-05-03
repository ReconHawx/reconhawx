"""Serialization of runner workflow snapshots for POST /workflow/executions/.../logs.

Kept standalone so tests can validate metadata/priority merges without importing
the full ``run-workflow.py`` stack (avoid ``models.*`` clashes with API tests).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def serialize_workflow_definition_snapshot(
    workflow: Any,
    raw_workflow_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Serialize workflow definition to JSON-serializable dict for the API."""

    def serialize_input_definition(input_def: Any) -> Any:
        if hasattr(input_def, "model_dump"):
            return input_def.model_dump()
        if hasattr(input_def, "dict"):
            return input_def.dict()
        if isinstance(input_def, dict):
            return input_def
        return {
            "type": getattr(input_def, "type", None),
            "asset_type": getattr(input_def, "asset_type", None),
            "finding_type": getattr(input_def, "finding_type", None),
            "value_type": getattr(input_def, "value_type", None),
            "values": getattr(input_def, "values", None),
            "filter": getattr(input_def, "filter", None),
            "filter_type": getattr(input_def, "filter_type", None),
            "limit": getattr(input_def, "limit", None),
            "min_similarity_percent": getattr(input_def, "min_similarity_percent", None),
            "similarity_protected_domain": getattr(input_def, "similarity_protected_domain", None),
            "scope_domains_filter": getattr(input_def, "scope_domains_filter", None),
        }

    serialized_inputs: Dict[str, Any] = {}
    if hasattr(workflow, "inputs") and workflow.inputs:
        for k, v in workflow.inputs.items():
            serialized_inputs[k] = serialize_input_definition(v)

    out = {
        "name": workflow.name,
        "description": getattr(workflow, "description", None),
        "steps": [
            {
                "name": step.name,
                "tasks": [
                    {
                        "name": task.name,
                        "task_type": getattr(task, "task_type", None) or task.name,
                        "params": getattr(task, "params", {}) or {},
                        "input_mapping": getattr(task, "input_mapping", None),
                        "output_mode": getattr(task, "output_mode", None),
                        "use_proxy": getattr(task, "use_proxy", None),
                    }
                    for task in step.tasks
                ],
            }
            for step in workflow.steps
        ],
        "inputs": serialized_inputs,
        "variables": getattr(workflow, "variables", {}) or {},
    }
    if isinstance(raw_workflow_payload, dict):
        meta = raw_workflow_payload.get("metadata")
        if isinstance(meta, dict) and meta:
            out["metadata"] = dict(meta)
        if "priority" in raw_workflow_payload and raw_workflow_payload["priority"] is not None:
            out["priority"] = raw_workflow_payload["priority"]
    return out
