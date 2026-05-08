"""Tests for ``recon_tasks.nuclei_scan.NucleiScan`` (multi-type input)."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType, FindingType
from recon_tasks.nuclei_scan import NucleiScan


@pytest.fixture
def task() -> NucleiScan:
    return NucleiScan()


def test_get_timestamp_hash_is_reversible(task: NucleiScan) -> None:
    digest = task.get_timestamp_hash("https://example.com", params={"t": 1})
    decoded = base64.b64decode(digest).decode()
    assert "nuclei_scan" in decoded
    assert "https://example.com" in decoded


def test_parse_matched_at_ip_port_ipv4(task: NucleiScan) -> None:
    assert task._parse_matched_at_ip_port("192.168.1.1:8080") == ("192.168.1.1", 8080)


def test_parse_matched_at_ip_port_ipv6(task: NucleiScan) -> None:
    result = task._parse_matched_at_ip_port("[::1]:443")
    assert result is not None
    ip, port = result
    assert port == 443
    assert "::1" in ip


def test_parse_matched_at_ip_port_none(task: NucleiScan) -> None:
    assert task._parse_matched_at_ip_port("") is None
    assert task._parse_matched_at_ip_port("https://example.com") is None


def test_get_command_accepts_mixed_input_types(task: NucleiScan) -> None:
    cmd = task.get_command(
        ["example.com", "1.2.3.4", "https://foo.test"],
        params={"template": {"official": ["http/cves"]}, "cmd_args": ["-severity", "high"]},
    )
    assert "example.com" in cmd
    assert "1.2.3.4" in cmd
    assert "https://foo.test" in cmd
    assert "-t http/cves" in cmd
    assert "-severity high" in cmd


def test_get_command_custom_templates_build_api_url(task: NucleiScan) -> None:
    cmd = task.get_command(["x.test"], params={"template": {"custom": ["mine"]}})
    assert "http://api.recon.svc.cluster.local:8000/nuclei-templates/raw/mine.yaml" in cmd


def test_get_command_structured_options_before_cmd_args(task: NucleiScan) -> None:
    cmd = task.get_command(
        ["https://t.example"],
        params={
            "template": {"official": ["http/cves"]},
            "rate_limit": 50,
            "automatic_scan": True,
            "tags": "cve,xss",
            "severity": ["high", "critical"],
            "interactsh_server": "https://oast.example",
            "interactsh_token": "secret",
            "http_timeout": 30,
            "retries": 2,
            "headless": True,
            "cmd_args": ["-verbose"],
        },
    )
    assert "https://t.example" in cmd
    assert "-t http/cves" in cmd
    assert "-rate-limit 50" in cmd
    assert "-automatic-scan" in cmd
    assert "-tags" in cmd and "cve,xss" in cmd
    assert "-severity high,critical" in cmd
    assert "-interactsh-server" in cmd and "oast.example" in cmd
    assert "-interactsh-token" in cmd and "secret" in cmd
    assert "-timeout 30" in cmd
    assert "-retries 2" in cmd
    assert "-headless" in cmd
    idx_verbose = cmd.index("-verbose")
    idx_headless = cmd.index("-headless")
    assert idx_headless < idx_verbose


def test_get_command_structured_options_skipped_when_empty(task: NucleiScan) -> None:
    cmd = task.get_command(["x"], params={"template": {}, "severity": [], "tags": ""})
    assert "-rate-limit" not in cmd
    assert "-severity" not in cmd
    assert "-tags" not in cmd
    assert "-automatic-scan" not in cmd


def test_parse_output_emits_finding_plus_derived_assets(
    task: NucleiScan, load_fixture
) -> None:
    raw = load_fixture("nuclei_scan/nuclei_findings.jsonl")
    result = task.parse_output(raw)

    findings = result[FindingType.NUCLEI]
    assert len(findings) == 3
    template_ids = {f.template_id for f in findings}
    assert template_ids == {"cve-2024-0001", "tls-detect", "nginx-detect"}

    # Service extracted from explicit ip/port + matched_at ip:port.
    services = result[AssetType.SERVICE]
    service_keys = {(s.ip, s.port) for s in services}
    assert ("1.2.3.4", 443) in service_keys
    assert ("192.168.1.10", 8443) in service_keys

    # Technology detection path builds a Url asset with technologies.
    urls = result[AssetType.URL]
    assert any(u.technologies and "nginx" in u.technologies for u in urls)


def test_parse_output_empty_returns_empty_structures(task: NucleiScan) -> None:
    result = task.parse_output("")
    assert result[FindingType.NUCLEI] == []
    assert result[AssetType.SERVICE] == []
    assert result[AssetType.URL] == []
    assert result[AssetType.SUBDOMAIN] == []
    assert result[AssetType.IP] == []


def test_parse_output_malformed_line_skipped_others_kept(task: NucleiScan) -> None:
    raw = (
        '{"template-id": "ok", "info": {"name": "OK", "severity": "low"}, "type": "http"}\n'
        "{bad json\n"
        '{"template-id": "ok2", "info": {"severity": "info"}, "type": "http"}'
    )
    result = task.parse_output(raw)
    ids = {f.template_id for f in result[FindingType.NUCLEI]}
    assert ids == {"ok", "ok2"}
