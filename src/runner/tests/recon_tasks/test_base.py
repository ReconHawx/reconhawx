"""Tests for helpers in ``recon_tasks.base``."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from recon_tasks import base as base_module
from recon_tasks.base import AssetType, CommandSpec, FindingType, Task, _type_attr_to_names
from recon_tasks.base import Ip as BaseIp, Service as BaseService


class _DummyTask(Task):
    name = "dummy"
    description = "test"
    input_type = AssetType.SUBDOMAIN
    output_types = [AssetType.SUBDOMAIN]

    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        return ""

    def parse_output(self, output: Any, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        return {AssetType.SUBDOMAIN: []}

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        return "hash"


@pytest.fixture
def task() -> _DummyTask:
    return _DummyTask()


def test_type_attr_to_names_enum_and_str() -> None:
    assert _type_attr_to_names(AssetType.IP) == {"ip"}
    assert _type_attr_to_names([AssetType.IP, "Subdomain"]) == {"ip", "subdomain"}
    assert _type_attr_to_names(None) == set()
    assert _type_attr_to_names([AssetType.URL, FindingType.NUCLEI]) == {"url", "nuclei"}


def test_base_ip_equality_and_hash() -> None:
    a = BaseIp("1.2.3.4")
    b = BaseIp("1.2.3.4", ptr=["example.com"])
    assert a == b
    assert hash(a) == hash(b)
    assert a != BaseIp("5.6.7.8")
    assert a != "1.2.3.4"
    assert a.to_dict() == {"ip": "1.2.3.4", "ptr": []}


def test_base_service_to_dict_round_trip() -> None:
    svc = BaseService(ip="1.2.3.4", port=80, protocol="tcp", service="http", banner="nginx")
    assert svc.to_dict() == {
        "ip": "1.2.3.4",
        "port": 80,
        "protocol": "tcp",
        "service": "http",
        "banner": "nginx",
        "program_name": None,
    }


def test_command_spec_defaults() -> None:
    spec = CommandSpec(task_name="t", command="echo x")
    assert spec.params is None
    assert spec.batch_group is None


def test_normalize_output_for_parsing_string_passthrough(task: _DummyTask) -> None:
    assert task.normalize_output_for_parsing("abc") == "abc"


def test_normalize_output_for_parsing_dict_with_output(task: _DummyTask) -> None:
    assert task.normalize_output_for_parsing({"output": "payload"}) == "payload"


def test_normalize_output_for_parsing_dict_fallback_to_json(task: _DummyTask) -> None:
    result = task.normalize_output_for_parsing({"a": 1})
    assert json.loads(result) == {"a": 1}


def test_normalize_output_for_parsing_none(task: _DummyTask) -> None:
    assert task.normalize_output_for_parsing(None) == ""


def test_extract_transformation_context_filters_and_aliases(task: _DummyTask) -> None:
    ctx = task._extract_transformation_context(
        {
            "typo_domain": "a.com",
            "risk_factors": {"x": 1},
            "program_name": "p",
            "wordlist": "foo.txt",
            "context_extra": "bar",
            "ignored": "no",
        }
    )
    assert ctx == {
        "typo_domain": "a.com",
        "risk_factors": {"x": 1},
        "program_name": "p",
        "fuzzer_wordlist": "foo.txt",
        "extra": "bar",
    }


def test_extract_transformation_context_empty_params(task: _DummyTask) -> None:
    assert task._extract_transformation_context(None) == {}
    assert task._extract_transformation_context({}) == {}


def test_get_timeout_respects_param_override(task: _DummyTask, monkeypatch) -> None:
    monkeypatch.setattr(base_module.parameter_manager, "get_timeout", lambda name: 99)
    assert task.get_timeout(["x"], {"timeout": 42}) == 42
    assert task.get_timeout(["x"], None) == 99
    # Invalid values fall back to default.
    assert task.get_timeout(["x"], {"timeout": 0}) == 99
    assert task.get_timeout(["x"], {"timeout": "bad"}) == 99


def test_get_chunk_size_respects_param_override(task: _DummyTask, monkeypatch) -> None:
    monkeypatch.setattr(base_module.parameter_manager, "get_chunk_size", lambda name: 5)
    assert task.get_chunk_size(["x"], {"chunk_size": 12}) == 12
    assert task.get_chunk_size(["x"], None) == 5
    assert task.get_chunk_size(["x"], {"chunk_size": "bad"}) == 5
    assert task.get_chunk_size(["x"], {"chunk_size": -1}) == 5


def test_get_last_execution_threshold_delegates(task: _DummyTask, monkeypatch) -> None:
    monkeypatch.setattr(
        base_module.parameter_manager, "get_last_execution_threshold", lambda name: 48
    )
    assert task.get_last_execution_threshold() == 48


def test_transform_to_findings_default_is_empty(task: _DummyTask) -> None:
    assert task.transform_to_findings({}, {}) == {}


def test_process_output_for_typosquat_mode_no_assets(task: _DummyTask) -> None:
    result = task.process_output_for_typosquat_mode("ignored", {})
    assert result == {}
