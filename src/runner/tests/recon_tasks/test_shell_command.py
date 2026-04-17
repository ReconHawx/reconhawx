"""Tests for ``recon_tasks.shell_command.ShellCommand`` (raw passthrough task)."""

from __future__ import annotations

import pytest

from recon_tasks.base import AssetType
from recon_tasks.shell_command import ShellCommand


@pytest.fixture
def task() -> ShellCommand:
    return ShellCommand()


def test_get_timestamp_hash_returns_none(task: ShellCommand) -> None:
    # shell_command is non-idempotent: no caching via timestamp hash.
    assert task.get_timestamp_hash("whatever") is None


def test_get_timeout_returns_fixed(task: ShellCommand) -> None:
    assert task.get_timeout("any-input") == 300


def test_get_command_without_input_just_joins_params(task: ShellCommand) -> None:
    cmd = task.get_command("", params={"command": ["echo", "hello"]})
    assert cmd == "echo hello"


def test_get_command_with_input_wraps_heredoc(task: ShellCommand) -> None:
    cmd = task.get_command(
        "payload-line-1\npayload-line-2",
        params={"command": ["grep", "-v", "foo"]},
    )
    assert cmd.startswith("cat << 'EOF' | grep -v foo\n")
    assert "payload-line-1\npayload-line-2" in cmd
    assert cmd.endswith("\nEOF")


def test_get_command_handles_none_params(task: ShellCommand) -> None:
    # None params should not raise; command collapses to empty string.
    assert task.get_command("") == ""


def test_parse_output_returns_raw_string_as_string_asset(task: ShellCommand) -> None:
    output = "line 1\nline 2"
    result = task.parse_output(output)
    assert result == {AssetType.STRING: [output]}


def test_parse_output_empty_still_wrapped(task: ShellCommand) -> None:
    assert task.parse_output("") == {AssetType.STRING: [""]}
