"""Tests for ``recon_tasks.subdomain_permutations.SubdomainPermutations``."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType
from recon_tasks.subdomain_permutations import SubdomainPermutations


@pytest.fixture
def task() -> SubdomainPermutations:
    return SubdomainPermutations()


def test_get_timestamp_hash_is_reversible(task: SubdomainPermutations) -> None:
    digest = task.get_timestamp_hash("example.com")
    decoded = base64.b64decode(digest).decode()
    assert "example.com" in decoded
    assert "subdomain_permutations" in decoded


def test_get_command_is_empty_for_orchestrator(task: SubdomainPermutations) -> None:
    assert task.get_command(["example.com"]) == ""


@pytest.mark.parametrize(
    "value,expected_prefix",
    [
        ("/abs/path/list.txt", "/abs/"),
        ("rel/list.txt", "rel/"),
    ],
)
def test_resolve_permutation_list_path_local(task: SubdomainPermutations, value: str, expected_prefix: str) -> None:
    assert task._resolve_permutation_list_path(value).startswith(expected_prefix)


def test_parse_output_is_noop_for_orchestrator(task: SubdomainPermutations) -> None:
    assert task.parse_output("anything") == {AssetType.SUBDOMAIN: [], AssetType.IP: []}
