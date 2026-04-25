"""Tests for shared runner logging configuration."""

import json
import logging

from recon_log_format import parse_log_level
from runner_logging import configure_runner_logging


def test_parse_log_level_defaults():
    assert parse_log_level(None) == logging.INFO
    assert parse_log_level("DEBUG") == logging.DEBUG
    assert parse_log_level("bogus") == logging.INFO


def test_configure_runner_logging_respects_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_runner_logging()
    assert logging.getLogger().level == logging.WARNING
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_runner_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_configure_runner_logging_sets_library_levels(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_runner_logging()
    assert logging.getLogger("kubernetes").level == logging.WARNING
    assert logging.getLogger("task_executor").level == logging.DEBUG


def test_configure_runner_logging_json_line_parseable(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_runner_logging()
    logging.getLogger("runner_smoke").warning("hello-json")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["service"] == "runner"
    assert data["level"] == "WARNING"
    assert data["message"] == "hello-json"
    assert data["logger"] == "runner_smoke"
    assert data["type"] == "application"
