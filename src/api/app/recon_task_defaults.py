"""
Builtin recon-task parameters: loaded from YAML next to this module (or RECON_TASK_DEFAULTS_PATH).

DB rows in recon_task_parameters shallow-merge on top; with no row, API returns these defaults only
(stored_in_database=false). The API does not insert default rows into the database on startup.

Runner loads effective parameters from GET /admin/public/recon-tasks/effective-parameters at workflow startup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_FILE = Path(__file__).resolve().parent / "recon_task_builtin_defaults.yaml"


def _load_builtin_defaults_from_yaml() -> Dict[str, Dict[str, Any]]:
    path = Path(os.environ.get("RECON_TASK_DEFAULTS_PATH", str(_DEFAULT_FILE))).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"Recon task defaults YAML not found: {path}. "
            "Set RECON_TASK_DEFAULTS_PATH or restore recon_task_builtin_defaults.yaml."
        )
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Recon task defaults must be a mapping at top level, got {type(raw)}")
    out: Dict[str, Dict[str, Any]] = {}
    for task_name, params in raw.items():
        if not isinstance(task_name, str):
            raise ValueError(f"Invalid task name key: {task_name!r}")
        if not isinstance(params, dict):
            raise ValueError(f"Task {task_name!r} parameters must be a mapping, got {type(params)}")
        out[task_name] = dict(params)
    if not out:
        raise ValueError("Recon task defaults YAML is empty")
    return out


try:
    RECON_TASK_BUILTIN_DEFAULTS: Dict[str, Dict[str, Any]] = _load_builtin_defaults_from_yaml()
except Exception as e:
    logger.exception("Failed to load recon task builtin defaults: %s", e)
    raise

KNOWN_RECON_TASKS: FrozenSet[str] = frozenset(RECON_TASK_BUILTIN_DEFAULTS.keys())

# Shown in System Settings and mutable via admin recon-task endpoints (POST/PUT/DELETE, etc.).
# Tasks still in KNOWN_RECON_TASKS (e.g. shell_command in YAML) get public GET for the runner but are omitted here.
RECON_TASKS_HIDDEN_FROM_ADMIN_CATALOG: FrozenSet[str] = frozenset({
    "shell_command",
    "asset_batch_generator",
})

# Keys removed from the recon-task contract; omitted from API responses even if still present in DB JSON.
DEPRECATED_RECON_TASK_PARAMETER_KEYS: FrozenSet[str] = frozenset({
    "max_retries",
})

GENERIC_BUILTIN_FALLBACK: Dict[str, Any] = {
    "last_execution_threshold": 24,
    "timeout": 300,
    "chunk_size": 10,
}


def is_known_recon_task(recon_task: str) -> bool:
    return recon_task in RECON_TASK_BUILTIN_DEFAULTS


def recon_task_names_for_admin_list() -> List[str]:
    """Recon tasks listed under System Settings (excludes debug / workflow-only rows)."""
    return sorted(KNOWN_RECON_TASKS - RECON_TASKS_HIDDEN_FROM_ADMIN_CATALOG)


def is_recon_task_admin_configurable(recon_task: str) -> bool:
    """True if superuser may create/update/delete stored overrides for this task."""
    if recon_task not in KNOWN_RECON_TASKS:
        return False
    return recon_task not in RECON_TASKS_HIDDEN_FROM_ADMIN_CATALOG


def builtin_parameters(recon_task: str) -> Dict[str, Any]:
    """Return a copy of builtin parameters for a task, or generic fallback if unknown."""
    base = RECON_TASK_BUILTIN_DEFAULTS.get(recon_task)
    if base:
        return dict(base)
    return dict(GENERIC_BUILTIN_FALLBACK)


def effective_parameters(
    recon_task: str,
    stored: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Builtin defaults shallow-merged with optional DB-stored parameters (stored wins per key).
    Unknown task names use GENERIC_BUILTIN_FALLBACK only (no raise).
    """
    merged = dict(builtin_parameters(recon_task))
    if stored:
        merged = {**merged, **stored}
    if DEPRECATED_RECON_TASK_PARAMETER_KEYS:
        merged = {
            k: v
            for k, v in merged.items()
            if k not in DEPRECATED_RECON_TASK_PARAMETER_KEYS
        }
    return merged


def recon_task_api_payload(
    recon_task: str,
    row: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a dict for ReconTaskParametersResponse.
    row: result of ReconTaskParameters.to_dict(), or None if no DB row.
    """
    stored = row.get("parameters") if row else None
    return {
        "id": row.get("id") if row else None,
        "recon_task": recon_task,
        "parameters": effective_parameters(recon_task, stored),
        "created_at": row.get("created_at") if row else None,
        "updated_at": row.get("updated_at") if row else None,
        "stored_in_database": row is not None,
    }
