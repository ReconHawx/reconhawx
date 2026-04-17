"""Tests for ``recon_tasks.subdomain_finder.SubdomainFinder``."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType
from recon_tasks.subdomain_finder import SubdomainFinder


@pytest.fixture
def task() -> SubdomainFinder:
    return SubdomainFinder()


def test_get_timestamp_hash_is_reversible(task: SubdomainFinder) -> None:
    digest = task.get_timestamp_hash("example.com")
    decoded = base64.b64decode(digest).decode()
    assert "example.com" in decoded
    assert "subdomain_finder" in decoded


def test_get_command_emits_subfinder_and_assetfinder_per_target(task: SubdomainFinder) -> None:
    commands = task.get_command(["example.com", "example.org"])

    assert isinstance(commands, list)
    assert f"subfinder -d example.com -silent" in commands
    assert f"echo example.com | assetfinder -subs-only" in commands
    assert f"subfinder -d example.org -silent" in commands
    assert f"echo example.org | assetfinder -subs-only" in commands
    # Two tools per target.
    assert len(commands) == 4


def test_get_command_accepts_single_string(task: SubdomainFinder) -> None:
    commands = task.get_command("example.com")
    assert any("subfinder -d example.com" in c for c in commands)


def test_parse_output_filters_non_domains(task: SubdomainFinder, load_fixture) -> None:
    raw = load_fixture("subdomain_finder/subfinder_mixed.txt")
    result = task.parse_output(raw)

    names = [d.name for d in result[AssetType.SUBDOMAIN]]

    assert "api.example.com" in names
    assert "www.example.com" in names
    assert "sub.example.co.uk" in names
    # URLs and banner lines are filtered out by get_valid_domains.
    assert not any("https://" in n for n in names)
    assert not any("[INF]" in n for n in names)
    assert "invalid..com" not in names


def test_parse_output_empty_returns_empty_list(task: SubdomainFinder) -> None:
    assert task.parse_output("") == {AssetType.SUBDOMAIN: []}
    assert task.parse_output("\n\n\n") == {AssetType.SUBDOMAIN: []}


def test_parse_output_strips_whitespace(task: SubdomainFinder) -> None:
    result = task.parse_output("  mail.example.com  \n")
    names = [d.name for d in result[AssetType.SUBDOMAIN]]
    assert names == ["mail.example.com"]
