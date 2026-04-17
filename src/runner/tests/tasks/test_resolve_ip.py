"""Tests for ``tasks.resolve_ip.ResolveIP``."""

from __future__ import annotations

import base64

import pytest

from tasks.base import AssetType
from tasks.resolve_ip import ResolveIP


@pytest.fixture
def task() -> ResolveIP:
    return ResolveIP()


def test_get_timestamp_hash_is_reversible(task: ResolveIP) -> None:
    digest = task.get_timestamp_hash("8.8.8.8")
    decoded = base64.b64decode(digest).decode()
    assert "8.8.8.8" in decoded
    assert "resolve_ip" in decoded


def test_get_command_accepts_list_and_string(task: ResolveIP, patched_resolvers) -> None:
    list_cmd = task.get_command(["1.1.1.1", "8.8.8.8"])
    str_cmd = task.get_command("1.1.1.1\n8.8.8.8")

    assert "1.1.1.1" in list_cmd and "8.8.8.8" in list_cmd
    assert "1.1.1.1" in str_cmd and "8.8.8.8" in str_cmd


def test_get_command_ipv4_octet_validation(task: ResolveIP, patched_resolvers) -> None:
    cmd = task.get_command(["1.1.1.1", "256.1.1.1", "not-an-ip", ""])

    assert "1.1.1.1" in cmd
    assert "256.1.1.1" not in cmd
    assert "not-an-ip" not in cmd


def test_get_command_all_invalid_returns_noop(task: ResolveIP, patched_resolvers) -> None:
    assert task.get_command(["not-an-ip", "also not an ip"]) == "echo ''"


def test_get_command_handles_nested_list_fallback(task: ResolveIP, patched_resolvers) -> None:
    cmd = task.get_command([["1.1.1.1", "8.8.8.8"], "9.9.9.9"])
    for ip in ("1.1.1.1", "8.8.8.8", "9.9.9.9"):
        assert ip in cmd


def test_parse_output_builds_ip_with_ptr(task: ResolveIP, load_fixture) -> None:
    raw = load_fixture("resolve_ip/dnsx_ptr.json")
    result = task.parse_output(raw)

    ips = result[AssetType.IP]
    by_ip = {ip.ip: ip for ip in ips}
    assert set(by_ip) == {"8.8.8.8", "1.1.1.1"}
    assert by_ip["8.8.8.8"].ptr == "dns.google"
    assert by_ip["8.8.8.8"].service_provider == "Google"
    assert by_ip["1.1.1.1"].service_provider == "Cloudflare"

    domains = {d.name for d in result[AssetType.SUBDOMAIN]}
    assert "dns.google" in domains
    assert "one.one.one.one" in domains


def test_parse_output_no_ptr_still_emits_ip(task: ResolveIP, load_fixture) -> None:
    raw = load_fixture("resolve_ip/dnsx_no_ptr.json")
    result = task.parse_output(raw)

    ips = result[AssetType.IP]
    assert [ip.ip for ip in ips] == ["192.0.2.1"]
    assert ips[0].ptr is None
    assert result[AssetType.SUBDOMAIN] == []


def test_parse_output_bad_dnsx_shape_skipped(task: ResolveIP, load_fixture) -> None:
    raw = load_fixture("resolve_ip/dnsx_no_ptr.json")
    result = task.parse_output(raw)
    ips = [ip.ip for ip in result[AssetType.IP]]
    assert "192.0.2.2" not in ips


def test_parse_output_json_error_returns_empty(task: ResolveIP) -> None:
    result = task.parse_output("not-json{")
    assert result == {AssetType.SUBDOMAIN: [], AssetType.IP: []}
