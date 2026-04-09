"""Tests for TaskParameterManager API manifest loading."""

import os
from unittest.mock import MagicMock, patch

import pytest

from tasks.base import TaskParameterManager


def test_load_all_from_api_success():
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "tasks": {"port_scan": {"timeout": 900, "chunk_size": 5}},
    }
    with patch.dict(
        os.environ,
        {
            "RUNNER_RECON_PARAMS_RETRIES": "2",
            "RUNNER_RECON_PARAMS_BACKOFF_SECONDS": "0",
        },
    ):
        with patch("tasks.base.requests.get", return_value=fake_resp):
            mgr.load_all_from_api()
    assert mgr.get_task_parameters("port_scan") == {"timeout": 900, "chunk_size": 5}


def test_load_all_from_api_raises_after_retries():
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.text = "unavailable"
    with patch.dict(
        os.environ,
        {
            "RUNNER_RECON_PARAMS_RETRIES": "3",
            "RUNNER_RECON_PARAMS_BACKOFF_SECONDS": "0",
        },
    ):
        with patch("tasks.base.requests.get", return_value=fake_resp):
            with pytest.raises(RuntimeError, match="Failed to load recon task parameters"):
                mgr.load_all_from_api()


def test_get_task_parameters_before_load_raises():
    mgr = TaskParameterManager()
    with pytest.raises(RuntimeError, match="not loaded"):
        mgr.get_task_parameters("resolve_domain")


def test_get_task_parameters_unknown_key_after_load():
    mgr = TaskParameterManager()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"tasks": {"a": {}}}
    with patch.dict(os.environ, {"RUNNER_RECON_PARAMS_BACKOFF_SECONDS": "0"}):
        with patch("tasks.base.requests.get", return_value=fake_resp):
            mgr.load_all_from_api()
    with pytest.raises(KeyError, match="nonexistent"):
        mgr.get_task_parameters("nonexistent")
