"""Tests for ``recon_tasks.wpscan.WPScan``."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import FindingType
from recon_tasks.wpscan import WPScan


@pytest.fixture
def task() -> WPScan:
    return WPScan()


def test_get_timestamp_hash_is_reversible(task: WPScan) -> None:
    digest = task.get_timestamp_hash("https://example.com", params={})
    decoded = base64.b64decode(digest).decode()
    assert "wpscan" in decoded
    assert "https://example.com" in decoded


def test_get_command_one_command_per_url(task: WPScan) -> None:
    cmds = task.get_command(
        ["https://a.test", "https://b.test", "ftp://skip.test"],
        params={"enumerate": ["ap", "at"]},
    )
    assert len(cmds) == 2
    assert all("wpscan" in c for c in cmds)
    assert any("--url 'https://a.test'" in c for c in cmds)
    assert any("--url 'https://b.test'" in c for c in cmds)
    assert all("--enumerate ap,at" in c for c in cmds)


def test_get_command_injects_api_token(task: WPScan) -> None:
    cmds = task.get_command(["https://a.test"], params={"api_token": "secret-token"})
    assert "--api-token secret-token" in cmds[0]


def test_get_command_default_enumerate_flags(task: WPScan) -> None:
    cmds = task.get_command(["https://a.test"])
    assert "--enumerate ap,at,u" in cmds[0]


def test_get_command_no_valid_urls_returns_echo_noop(task: WPScan) -> None:
    assert task.get_command(["not a url"]) == ["echo ''"]
    assert task.get_command([]) == ["echo ''"]


def test_parse_output_builds_wpscan_findings(task: WPScan, load_fixture) -> None:
    raw = load_fixture("wpscan/wpscan_success.json")
    result = task.parse_output(raw)
    findings = result[FindingType.WPSCAN]

    # Expect: 1 WP core vuln + 1 plugin vuln + 1 interesting finding + 3 enumeration
    # findings (users, plugins, wp version). main_theme has no vuln, but a theme
    # enumeration finding is emitted.
    titles = [f.title for f in findings]
    assert any("SQL Injection" in t for t in titles)
    assert any("Vulnerable Plugin XSS" in t for t in titles)
    assert any("wp-content" in t.lower() for t in titles)
    assert any(t == "Enumerated users" for t in titles)
    assert any(t == "Enumerated plugins" for t in titles)
    assert any(t == "WordPress version" for t in titles)

    # CVE extraction: plugin vuln has explicit CVE, WP core has it under references.cve.
    cve_finding = next(f for f in findings if "SQL Injection" in f.title)
    assert "2024-1234" in cve_finding.cve_ids or any(
        "2024-1234" in c for c in cve_finding.cve_ids
    )

    plugin_finding = next(f for f in findings if f.item_name == "vulnerable-plugin")
    assert plugin_finding.item_type == "plugin"
    assert any("CVE-2024-5678" in c for c in plugin_finding.cve_ids)


def test_parse_output_invalid_json_returns_empty(task: WPScan) -> None:
    assert task.parse_output("not json at all") == {FindingType.WPSCAN: []}


def test_parse_output_empty_returns_empty(task: WPScan) -> None:
    assert task.parse_output("") == {FindingType.WPSCAN: []}


def test_parse_output_no_target_url_returns_empty(task: WPScan) -> None:
    # Missing target_url / url / effective_url -> empty (logged as warning).
    assert task.parse_output('{"version": {"number": "6.0"}}') == {FindingType.WPSCAN: []}
