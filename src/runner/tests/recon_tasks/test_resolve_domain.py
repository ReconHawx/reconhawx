"""Tests for ``recon_tasks.resolve_domain.ResolveDomain``."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType
from recon_tasks.resolve_domain import ResolveDomain


@pytest.fixture
def task() -> ResolveDomain:
    return ResolveDomain()


def test_get_timestamp_hash_is_reversible(task: ResolveDomain) -> None:
    digest = task.get_timestamp_hash("example.com")
    decoded = base64.b64decode(digest).decode()
    assert "example.com" in decoded
    assert "resolve_domain" in decoded


def test_get_command_filters_invalid_domains(task: ResolveDomain, patched_resolvers) -> None:
    cmd = task.get_command(["example.com", "not a domain", "sub.example.com"])

    assert cmd.startswith("cat << 'EOF' | python3 dnsx_wrapper.py\n")
    assert "example.com" in cmd
    assert "sub.example.com" in cmd
    assert "not a domain" not in cmd


def test_get_command_all_invalid_returns_noop(task: ResolveDomain, patched_resolvers) -> None:
    assert task.get_command(["not a domain", "invalid..com"]) == "echo ''"


def test_get_command_handles_single_string_input(task: ResolveDomain, patched_resolvers) -> None:
    cmd = task.get_command("example.com")
    assert cmd.startswith("cat << 'EOF' | python3 dnsx_wrapper.py\n")
    assert "example.com" in cmd


def test_parse_output_success(task: ResolveDomain, load_fixture) -> None:
    raw = load_fixture("resolve_domain/dnsx_success.json")
    result = task.parse_output(raw)

    domains = result[AssetType.SUBDOMAIN]
    ips = result[AssetType.IP]

    names = sorted(d.name for d in domains)
    assert names == ["example.com", "sub.example.com"]

    for domain in domains:
        if domain.name == "example.com":
            assert sorted(domain.ip) == ["1.2.3.4", "5.6.7.8"]
            assert domain.cname_record is None
        else:
            assert domain.ip == ["1.2.3.4"]
            assert domain.cname_record == "alias.example.com"

    ip_strings = sorted(ip.ip for ip in ips)
    assert ip_strings == ["1.2.3.4", "1.2.3.4", "5.6.7.8"]
    assert {ip.discovered_via_domain for ip in ips} == {"example.com", "sub.example.com"}


def test_parse_output_wildcard(task: ResolveDomain, load_fixture) -> None:
    raw = load_fixture("resolve_domain/dnsx_wildcard.json")
    result = task.parse_output(raw)

    domains = result[AssetType.SUBDOMAIN]
    assert len(domains) == 1
    wildcard = domains[0]
    assert wildcard.name == "random.wild.example.com"
    assert wildcard.is_wildcard is True
    assert wildcard.wildcard_type == ["A"]


def test_parse_output_empty_returns_empty(task: ResolveDomain) -> None:
    result = task.parse_output("")
    assert result == {AssetType.SUBDOMAIN: [], AssetType.IP: []}


def test_parse_output_malformed_json_raises(task: ResolveDomain, load_fixture) -> None:
    raw = load_fixture("resolve_domain/dnsx_malformed.json")
    import json

    with pytest.raises(json.JSONDecodeError):
        task.parse_output(raw)


def test_parse_output_skips_domain_without_a_or_cname(task: ResolveDomain, load_fixture) -> None:
    raw = load_fixture("resolve_domain/dnsx_wildcard.json")
    result = task.parse_output(raw)
    names = {d.name for d in result[AssetType.SUBDOMAIN]}
    assert "noresolve.example.com" not in names
