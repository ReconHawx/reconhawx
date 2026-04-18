"""Tests for ``recon_tasks.dns_bruteforce.DnsBruteforce``."""

from __future__ import annotations

import base64
import json

import pytest

from recon_tasks.base import AssetType, FindingType
from recon_tasks.dns_bruteforce import DnsBruteforce


@pytest.fixture
def task() -> DnsBruteforce:
    return DnsBruteforce()


def test_get_timestamp_hash_includes_wordlist(task: DnsBruteforce) -> None:
    digest = task.get_timestamp_hash("example.com", {"wordlist": "my.txt"})
    decoded = base64.b64decode(digest).decode()
    assert "example.com" in decoded
    assert "my.txt" in decoded
    assert "dns_bruteforce" in decoded


def test_get_command_is_empty_for_orchestrator(task: DnsBruteforce) -> None:
    assert task.get_command(["example.com"]) == ""


@pytest.mark.parametrize(
    "value,expected_prefix",
    [
        ("12345678-1234-1234-1234-123456789012", "http"),
        ("https://example.com/list.txt", "https://"),
        ("/abs/path/list.txt", "/abs/"),
        ("rel/list.txt", "rel/"),
    ],
)
def test_resolve_wordlist_path_variants(task: DnsBruteforce, value: str, expected_prefix: str) -> None:
    assert task._resolve_wordlist_path(value).startswith(expected_prefix)


def test_infer_wildcard_subnets_requires_two_matching(task: DnsBruteforce) -> None:
    assert task._infer_wildcard_subnets(["1.2.3.4"]) == []
    subnets = task._infer_wildcard_subnets(["1.2.3.4", "1.2.3.99"])
    assert "1.2.3.0/24" in subnets


def test_infer_wildcard_subnets_skips_invalid(task: DnsBruteforce) -> None:
    assert task._infer_wildcard_subnets(["not-an-ip", "also-bad"]) == []


def test_parse_output_json_lines(task: DnsBruteforce) -> None:
    lines = [
        json.dumps({"domain": "a.example.com", "ips": ["1.2.3.4"], "cname": ""}),
        json.dumps({"domain": "b.example.com", "ips": ["5.6.7.8"], "cname": "target.elb.net"}),
    ]
    result = task.parse_output("\n".join(lines))

    domains = {d.name for d in result[AssetType.SUBDOMAIN]}
    assert domains == {"a.example.com", "b.example.com"}

    ips = {ip.ip for ip in result[AssetType.IP]}
    assert ips == {"1.2.3.4", "5.6.7.8"}


def test_parse_output_plain_line_fallback(task: DnsBruteforce) -> None:
    result = task.parse_output("sub.example.com\n")
    domains = {d.name for d in result[AssetType.SUBDOMAIN]}
    assert "sub.example.com" in domains


def test_parse_output_empty(task: DnsBruteforce) -> None:
    result = task.parse_output("")
    assert result == {AssetType.SUBDOMAIN: [], AssetType.IP: []}


def test_transform_to_findings_skips_unresolved(task: DnsBruteforce) -> None:
    raw = json.dumps({"domain": "bad.example.com", "ips": [], "cname": ""})
    assets = task.parse_output(raw)
    findings = task.transform_to_findings(assets, {"program_name": "p1"})
    assert findings.get(FindingType.TYPOSQUAT_DOMAIN, []) == []


def test_transform_to_findings_builds_typosquat_records(task: DnsBruteforce) -> None:
    raw = json.dumps({"domain": "x.example.com", "ips": ["1.1.1.1"], "cname": ""})
    assets = task.parse_output(raw)
    findings = task.transform_to_findings(assets, {"program_name": "p1"})
    records = findings[FindingType.TYPOSQUAT_DOMAIN]
    assert len(records) == 1
    assert records[0].typo_domain == "x.example.com"
    assert records[0].program_name == "p1"
    assert records[0].source == "dns_bruteforce"
