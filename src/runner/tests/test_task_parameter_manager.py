"""Tests for TaskParameterManager API manifest loading."""

import os
from unittest.mock import MagicMock, patch

import pytest

from recon_tasks.base import TaskParameterManager


def _patch_http(fake_resp):
    return patch("recon_tasks.base.requests.get", return_value=fake_resp)


def _env_no_backoff(retries: str = "2"):
    return patch.dict(
        os.environ,
        {
            "RUNNER_RECON_PARAMS_RETRIES": retries,
            "RUNNER_RECON_PARAMS_BACKOFF_SECONDS": "0",
        },
    )


def test_load_all_from_api_success_nested_shape():
    """New manifest shape: {parameters, input_types, output_types}."""
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "tasks": {
            "port_scan": {
                "parameters": {"timeout": 900, "chunk_size": 5},
                "input_types": ["ip"],
                "output_types": ["service"],
            }
        },
    }
    with _env_no_backoff(), _patch_http(fake_resp):
        mgr.load_all_from_api(check_registry=False)
    assert mgr.get_task_parameters("port_scan") == {"timeout": 900, "chunk_size": 5}
    assert mgr.get_task_input_types("port_scan") == ["ip"]
    assert mgr.get_task_output_types("port_scan") == ["service"]


def test_load_all_from_api_success_legacy_flat_shape():
    """Old manifest shape (flat parameters dict) must still load for forward compat."""
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "tasks": {"port_scan": {"timeout": 900, "chunk_size": 5}},
    }
    with _env_no_backoff(), _patch_http(fake_resp):
        mgr.load_all_from_api(check_registry=False)
    assert mgr.get_task_parameters("port_scan") == {"timeout": 900, "chunk_size": 5}
    assert mgr.get_task_input_types("port_scan") == []
    assert mgr.get_task_output_types("port_scan") == []


def test_load_all_from_api_raises_after_retries():
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.text = "unavailable"
    with _env_no_backoff("3"), _patch_http(fake_resp):
        with pytest.raises(RuntimeError, match="Failed to load recon task parameters"):
            mgr.load_all_from_api(check_registry=False)


def test_get_task_parameters_before_load_raises():
    mgr = TaskParameterManager()
    with pytest.raises(RuntimeError, match="not loaded"):
        mgr.get_task_parameters("resolve_domain")


def test_get_task_parameters_unknown_key_after_load():
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"tasks": {"a": {}}}
    with _env_no_backoff(), _patch_http(fake_resp):
        mgr.load_all_from_api(check_registry=False)
    with pytest.raises(KeyError, match="nonexistent"):
        mgr.get_task_parameters("nonexistent")


def test_drift_check_raises_when_manifest_missing_registered_task():
    """With check_registry=True, a manifest that omits a registered task must fail."""
    import recon_tasks  # noqa: F401  ensure registry populated

    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "tasks": {
            "port_scan": {
                "parameters": {},
                "input_types": ["ip"],
                "output_types": ["service"],
            }
        },
    }
    with _env_no_backoff(), _patch_http(fake_resp):
        with pytest.raises(RuntimeError, match="do not match API manifest"):
            mgr.load_all_from_api(check_registry=True)


def test_drift_check_raises_on_input_type_mismatch():
    """With check_registry=True, a mismatching input_type must fail."""
    import recon_tasks as _tasks_pkg

    registered = dict(getattr(_tasks_pkg.TaskRegistry, "_tasks", {}))
    assert registered, "TaskRegistry must be populated for this test"

    def _entry(task_cls):
        inputs = task_cls.input_type
        outputs = task_cls.output_types or []
        if not isinstance(inputs, (list, tuple, set)):
            inputs = [inputs]
        return {
            "parameters": {},
            "input_types": [getattr(x, "value", str(x)) for x in inputs],
            "output_types": [getattr(x, "value", str(x)) for x in outputs],
        }

    tasks_payload = {name: _entry(cls) for name, cls in registered.items()}
    first_name = next(iter(registered))
    tasks_payload[first_name]["input_types"] = ["definitely-not-a-real-type"]

    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"tasks": tasks_payload}
    with _env_no_backoff(), _patch_http(fake_resp):
        with pytest.raises(RuntimeError, match="input_type mismatch"):
            mgr.load_all_from_api(check_registry=True)
