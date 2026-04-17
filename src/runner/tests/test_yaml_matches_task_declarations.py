"""
Cross-checks that recon_task_builtin_defaults.yaml (API side) mirrors the Python
Task.input_type / Task.output_types declarations in the runner. This locks the
"single source of truth" invariant: the YAML is the serialized form of the code.

The YAML lives in src/api/app/recon_task_builtin_defaults.yaml relative to the
repo root. Test file path: src/runner/tests/test_yaml_matches_task_declarations.py
(parents[3] == repo root).
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

import tasks as _tasks_pkg  # noqa: F401  populates TaskRegistry on import
from tasks import TaskRegistry


def _repo_root() -> Path:
    # test file: src/runner/tests/test_yaml_matches_task_declarations.py
    return Path(__file__).resolve().parents[3]


def _load_yaml() -> Dict[str, Dict[str, object]]:
    yaml_path = _repo_root() / "src" / "api" / "app" / "recon_task_builtin_defaults.yaml"
    if not yaml_path.is_file():
        pytest.skip(f"YAML not found at {yaml_path}; runner tests may be run in isolation")
    with open(yaml_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    assert isinstance(raw, dict) and raw, "YAML must be a non-empty mapping"
    return raw


def _to_names(value) -> Set[str]:
    if value is None:
        return set()
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    out: Set[str] = set()
    for item in value:
        if isinstance(item, Enum):
            out.add(str(item.value).lower())
        elif isinstance(item, str) and item.strip():
            out.add(item.strip().lower())
    return out


def _yaml_types(entry: Dict[str, object], key: str) -> Set[str]:
    value = entry.get(key, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return set()
    return {str(v).strip().lower() for v in value if str(v).strip()}


def test_yaml_has_entry_for_every_registered_task():
    yaml_tasks = _load_yaml()
    registered: List[str] = sorted(TaskRegistry._tasks.keys())
    missing = [name for name in registered if name not in yaml_tasks]
    assert not missing, (
        f"recon_task_builtin_defaults.yaml is missing entries for registered tasks: {missing}"
    )


def test_yaml_io_types_match_python_declarations():
    yaml_tasks = _load_yaml()
    mismatches: List[str] = []
    for name, task_cls in sorted(TaskRegistry._tasks.items()):
        if name not in yaml_tasks:
            continue  # covered by the previous test
        entry = yaml_tasks[name] or {}
        code_inputs = _to_names(getattr(task_cls, "input_type", None))
        code_outputs = _to_names(getattr(task_cls, "output_types", None))
        yaml_inputs = _yaml_types(entry, "input_types")
        yaml_outputs = _yaml_types(entry, "output_types")
        if code_inputs != yaml_inputs:
            mismatches.append(
                f"task '{name}': input_types mismatch "
                f"(code={sorted(code_inputs)}, yaml={sorted(yaml_inputs)})"
            )
        if code_outputs != yaml_outputs:
            mismatches.append(
                f"task '{name}': output_types mismatch "
                f"(code={sorted(code_outputs)}, yaml={sorted(yaml_outputs)})"
            )
    assert not mismatches, (
        "recon_task_builtin_defaults.yaml drifted from runner Task declarations:\n  - "
        + "\n  - ".join(mismatches)
    )
