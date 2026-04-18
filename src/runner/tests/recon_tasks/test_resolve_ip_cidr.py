"""Tests for ``recon_tasks.resolve_ip_cidr.ResolveIPCIDR`` pure helpers."""

from __future__ import annotations

import base64
import json

import pytest

from recon_tasks.base import AssetType
from recon_tasks.resolve_ip_cidr import ResolveIPCIDR


@pytest.fixture
def task() -> ResolveIPCIDR:
    return ResolveIPCIDR()


def test_get_timestamp_hash_ip_is_reversible(task: ResolveIPCIDR) -> None:
    digest = task.get_timestamp_hash("10.0.0.5")
    decoded = base64.b64decode(digest).decode()
    assert "10.0.0.5" in decoded
    assert "resolve_ip_cidr" in decoded


def test_get_timestamp_hash_cidr_returns_empty(task: ResolveIPCIDR) -> None:
    assert task.get_timestamp_hash("10.0.0.0/24") == ""


def test_get_command_returns_empty_for_orchestrator(task: ResolveIPCIDR) -> None:
    assert task.get_command(["10.0.0.0/24"]) == ""


def test_expand_cidr_with_offset(task: ResolveIPCIDR) -> None:
    ips = task._expand_cidr_with_offset("10.0.0.0/30", offset=0, limit=10)
    # /30 has 2 host addresses.
    assert ips == ["10.0.0.1", "10.0.0.2"]


def test_expand_cidr_with_offset_respects_offset_and_limit(task: ResolveIPCIDR) -> None:
    ips = task._expand_cidr_with_offset("192.168.0.0/24", offset=5, limit=3)
    assert ips == ["192.168.0.6", "192.168.0.7", "192.168.0.8"]


def test_expand_cidr_invalid_returns_empty(task: ResolveIPCIDR) -> None:
    assert task._expand_cidr_with_offset("not-a-cidr", 0, 10) == []


def test_calculate_adaptive_chunk_size_small(task: ResolveIPCIDR) -> None:
    # Small /24 → at most chunk_size, capped by ip_limit.
    result = task._calculate_adaptive_chunk_size(total_hosts=256, ip_limit=500)
    assert 1 <= result <= task.chunk_size


def test_calculate_adaptive_chunk_size_scales(task: ResolveIPCIDR) -> None:
    result = task._calculate_adaptive_chunk_size(total_hosts=200_000, ip_limit=1000)
    assert result == 100


def test_calculate_adaptive_chunk_size_disabled(task: ResolveIPCIDR, monkeypatch) -> None:
    monkeypatch.setattr(task, "adaptive_chunking_enabled", False)
    assert task._calculate_adaptive_chunk_size(10, 10) == task.chunk_size


def test_determine_task_type_by_id(task: ResolveIPCIDR) -> None:
    assert task._determine_task_type_from_output("port_scan-abc", "") == "port_scan"
    assert task._determine_task_type_from_output("resolve_ip-xyz", "") == "resolve_ip"


def test_determine_task_type_by_output_content(task: ResolveIPCIDR) -> None:
    assert task._determine_task_type_from_output("misc", "nmap scan results") == "port_scan"
    assert task._determine_task_type_from_output("misc", "dnsx output") == "resolve_ip"


def test_parse_dnsx_json_empty(task: ResolveIPCIDR) -> None:
    result = task._parse_dnsx_json({})
    assert result == {AssetType.SUBDOMAIN: [], AssetType.IP: []}


def test_parse_output_invalid_json(task: ResolveIPCIDR) -> None:
    result = task.parse_output("not-json{")
    assert result == {AssetType.SUBDOMAIN: [], AssetType.IP: []}


def test_parse_output_entry_without_dnsx_skipped(task: ResolveIPCIDR) -> None:
    payload = json.dumps({"1.2.3.4": {"provider": "Acme"}})
    result = task.parse_output(payload)
    assert result[AssetType.IP] == []
    assert result[AssetType.SUBDOMAIN] == []
