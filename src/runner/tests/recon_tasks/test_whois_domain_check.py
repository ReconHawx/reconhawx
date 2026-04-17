"""Tests for ``recon_tasks.whois_domain_check.WhoisDomainCheck``."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType, CommandSpec
from recon_tasks.whois_domain_check import WhoisDomainCheck, _RAW_RESPONSE_MAX


@pytest.fixture
def task() -> WhoisDomainCheck:
    return WhoisDomainCheck()


def test_get_timestamp_hash_is_reversible(task: WhoisDomainCheck) -> None:
    digest = task.get_timestamp_hash("example.com")
    decoded = base64.b64decode(digest).decode()
    assert "whois_domain_check" in decoded
    assert "example.com" in decoded


def test_collect_unique_apex_domains_deduplicates_and_lowercases(
    task: WhoisDomainCheck,
) -> None:
    result = task._collect_unique_apex_domains(
        [
            "Api.Example.com",
            "www.example.com",
            "EXAMPLE.COM",
            "other.example.co.uk",
            "other.example.co.uk",
        ]
    )
    assert result == ["example.com", "example.co.uk"]


def test_collect_unique_apex_domains_rejects_invalid(task: WhoisDomainCheck) -> None:
    result = task._collect_unique_apex_domains(
        ["not a domain", "", None, 42, "invalid..com", "   "]
    )
    assert result == []


def test_get_command_joins_with_heredoc(task: WhoisDomainCheck) -> None:
    cmd = task.get_command(["example.com", "other.test"])
    assert cmd.startswith("cat << 'EOF' | python3 whois_domain_wrapper.py\n")
    assert "example.com" in cmd
    assert "other.test" in cmd


def test_get_command_empty_returns_noop_object(task: WhoisDomainCheck) -> None:
    assert task.get_command([]) == "echo '{}'"


@pytest.mark.asyncio
async def test_generate_commands_one_cmdspec_per_chunk(task: WhoisDomainCheck) -> None:
    commands = await task.generate_commands(
        input_data=["a.example.com", "b.example.com", "c.other.co.uk"],
        params={"chunk_size": 1},
        context={},
    )
    # Two unique apex domains (example.com, other.co.uk) -> 2 worker jobs.
    assert len(commands) == 2
    for spec in commands:
        assert isinstance(spec, CommandSpec)
        assert spec.task_name == "whois_domain_check"
        assert spec.command.startswith("cat << 'EOF' | python3 whois_domain_wrapper.py\n")


@pytest.mark.asyncio
async def test_generate_commands_empty_returns_empty_list(
    task: WhoisDomainCheck,
) -> None:
    commands = await task.generate_commands(
        input_data=["not a domain"], params={}, context={}
    )
    assert commands == []


def test_parse_output_structured_whois_fields(
    task: WhoisDomainCheck, load_fixture
) -> None:
    raw = load_fixture("whois_domain_check/whois_success.json")
    result = task.parse_output(raw)
    assets = result[AssetType.APEX_DOMAIN]

    by_name = {a["name"]: a for a in assets}
    assert set(by_name) == {"example.com", "notfound.test"}

    ok = by_name["example.com"]
    assert ok["whois_registrar"] == "Example Registrar, Inc."
    assert ok["whois_name_servers"] == ["ns1.example.net", "ns2.example.net"]
    assert ok["whois_response_source"] == "rdap"

    err = by_name["notfound.test"]
    assert err["whois_status"] == "Error"
    assert "timeout" in err["whois_error"]
    assert err["whois_response_source"] == "parse"


def test_parse_output_truncates_long_raw_response(task: WhoisDomainCheck) -> None:
    big = "x" * (_RAW_RESPONSE_MAX + 500)
    raw = '{"example.com": {"raw_response": "' + big + '"}}'
    asset = task.parse_output(raw)[AssetType.APEX_DOMAIN][0]
    assert asset["whois_raw_response"].endswith("...")
    assert len(asset["whois_raw_response"]) == _RAW_RESPONSE_MAX + 3


def test_parse_output_empty_returns_empty(task: WhoisDomainCheck) -> None:
    assert task.parse_output("") == {AssetType.APEX_DOMAIN: []}
    assert task.parse_output("   ") == {AssetType.APEX_DOMAIN: []}


def test_parse_output_invalid_json_returns_empty(task: WhoisDomainCheck) -> None:
    assert task.parse_output("not json {") == {AssetType.APEX_DOMAIN: []}


def test_parse_output_non_dict_top_level_returns_empty(task: WhoisDomainCheck) -> None:
    assert task.parse_output('["list", "not", "dict"]') == {AssetType.APEX_DOMAIN: []}


def test_parse_output_normalizes_empty_name_servers_to_none(
    task: WhoisDomainCheck,
) -> None:
    raw = '{"example.com": {"name_servers": []}}'
    asset = task.parse_output(raw)[AssetType.APEX_DOMAIN][0]
    assert asset["whois_name_servers"] is None
