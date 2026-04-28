"""Tests for worker JSON logging to stderr and stdout cleanliness in command_wrapper."""

import json
import logging
import shlex
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import recon_log_format
from command_wrapper import publish_result, run_command
from worker_logging import configure_worker_logging


def test_parse_log_level_defaults_with_worker_recon_log():
    assert recon_log_format.parse_log_level(None) == logging.INFO
    assert recon_log_format.parse_log_level("DEBUG") == logging.DEBUG
    assert recon_log_format.parse_log_level("bogus") == logging.INFO


def test_configure_worker_logging_respects_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_worker_logging()
    assert logging.getLogger().level == logging.WARNING
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_worker_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_configure_worker_logging_stderr_json_parseable(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_worker_logging()
    logging.getLogger("worker_smoke").warning("hello-stderr")
    out = capsys.readouterr()
    assert out.out == "", "worker logs must never use stdout (subprocess payload channel)"
    line = out.err.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["service"] == "worker"
    assert data["level"] == "WARNING"
    assert data["message"] == "hello-stderr"
    assert data["logger"] == "worker_smoke"
    assert data["type"] == "application"


def test_root_handler_uses_stderr(monkeypatch):
    """configure_worker_logging must send logs to stderr, not stdout."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_worker_logging()
    h = logging.getLogger().handlers[0]
    assert h.stream is sys.stderr


def test_run_command_drains_large_stderr_without_deadlock(monkeypatch):
    """Child must not block on a full stderr pipe while parent reads stdout only."""
    monkeypatch.delenv("NATS_URL", raising=False)
    monkeypatch.delenv("TASK_ID", raising=False)

    def fake_exit(code=0):
        raise SystemExit(code)

    monkeypatch.setattr("command_wrapper.sys.exit", fake_exit)

    # ~250KiB on stderr (multiple lines), single JSON line on stdout
    py_code = (
        "import json as j, sys\n"
        "for _ in range(2500):\n"
        "    print('x' * 100, file=sys.stderr)\n"
        "print(j.dumps({'ok': True}))\n"
    )
    cmd = f"{sys.executable} -c {shlex.quote(py_code)}"

    with pytest.raises(SystemExit) as exc_info:
        run_command(cmd)

    assert exc_info.value.code == 0


@pytest.mark.asyncio
async def test_publish_result_does_not_write_to_stdout(
    capsys, monkeypatch
) -> None:
    """NATS path must not emit anything on stdout; payload is from subprocess only."""
    monkeypatch.setenv("OUTPUT_QUEUE_SUBJECT", "tasks.output.wf-123")
    monkeypatch.setenv("NATS_URL", "nats://nats:4222")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("TASK_ID", "t1")
    monkeypatch.setenv("WORKFLOW_ID", "wf-123")
    mock_nc = AsyncMock()
    mock_js = MagicMock()
    mock_js.publish = AsyncMock(return_value=MagicMock(seq=42))
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    mock_nc.drain = AsyncMock()
    capsys.readouterr()  # flush
    with patch("command_wrapper.nats.connect", new=AsyncMock(return_value=mock_nc)):
        ok = await publish_result("out", True)
    assert ok is True
    captured = capsys.readouterr()
    assert captured.out == ""

