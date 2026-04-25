"""Smoke tests for Loki-friendly JSON / logfmt formatters."""

from __future__ import annotations

import json
import logging

import recon_log_format


def test_json_line_formatter_produces_parseable_json():
    fmt = recon_log_format.JsonLineFormatter(service="api")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    line = fmt.format(record)
    data = json.loads(line)
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "hello"
    assert data["service"] == "api"
    assert data["type"] == "application"
    assert data["timestamp"].endswith("Z")


def test_apply_service_logging_json_stdout(capsys, monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.delenv("RECON_SERVICE_NAME", raising=False)
    recon_log_format.apply_service_logging(
        service="api",
        include_uvicorn=False,
        log_format="json",
        root_level=logging.WARNING,
    )
    logging.getLogger("smoke").error("oops")
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert parsed["message"] == "oops"
    assert parsed["type"] == "application"


def test_apply_service_logging_stream_stderr(capsys, monkeypatch):
    """``stream=`` can send structured logs to stderr (worker pods; stdout = payload)."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.delenv("RECON_SERVICE_NAME", raising=False)
    recon_log_format.apply_service_logging(
        service="api",
        include_uvicorn=False,
        log_format="json",
        root_level=logging.WARNING,
        stream="ext://sys.stderr",
    )
    logging.getLogger("smoke2").error("eek")
    out = capsys.readouterr()
    assert out.out == ""
    parsed = json.loads(out.err.strip())
    assert parsed["message"] == "eek"
    assert parsed["type"] == "application"


def test_logfmt_formatter_basic():
    fmt = recon_log_format.LogfmtFormatter(service="runner")
    record = logging.LogRecord(
        name="x",
        level=logging.ERROR,
        pathname=__file__,
        lineno=2,
        msg='a b "c"',
        args=(),
        exc_info=None,
    )
    line = fmt.format(record)
    assert "level=ERROR" in line
    assert "service=runner" in line
    assert "type=application" in line
    assert "message=" in line


def test_parse_uvicorn_access_message():
    line = (
        '10.244.21.45:57108 - "GET /admin/event-handler/status HTTP/1.1" 200'
    )
    p = recon_log_format.parse_uvicorn_access_message(line)
    assert p is not None
    assert p["client"] == "10.244.21.45:57108"
    assert p["method"] == "GET"
    assert p["path"] == "/admin/event-handler/status"
    assert p["http_version"] == "HTTP/1.1"
    assert p["status"] == 200


def test_uvicorn_access_json_line_formatter(monkeypatch):
    monkeypatch.setenv("RECON_SERVICE_NAME", "api")
    sample = '10.0.0.1:1234 - "GET /status HTTP/1.1" 200'
    fmt = recon_log_format.UvicornAccessJsonLineFormatter(service="api")
    rec = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=sample,
        args=(),
        exc_info=None,
    )
    line = fmt.format(rec)
    data = json.loads(line)
    assert data["type"] == "http_access"
    assert data["client"] == "10.0.0.1:1234"
    assert data["method"] == "GET"
    assert data["path"] == "/status"
    assert data["status"] == 200
    assert data["service"] == "api"
    assert data["message"] == "GET /status 200"


def test_uvicorn_access_logfmt_includes_message(monkeypatch):
    monkeypatch.setenv("RECON_SERVICE_NAME", "api")
    sample = '10.0.0.1:1234 - "GET /status HTTP/1.1" 200'
    fmt = recon_log_format.UvicornAccessLogfmtFormatter(service="api")
    rec = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=sample,
        args=(),
        exc_info=None,
    )
    line = fmt.format(rec)
    assert 'type="http_access"' in line
    assert "message=" in line
    assert "GET /status 200" in line


def test_apply_with_uvicorn_access_uses_separate_formatters(
    capsys, monkeypatch
) -> None:
    """``uvicorn.access`` gets structured http_access; app loggers get default JSON."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.delenv("RECON_SERVICE_NAME", raising=False)
    recon_log_format.apply_service_logging(
        service="api",
        include_uvicorn=True,
        log_format="json",
        root_level=logging.INFO,
    )
    capsys.readouterr()
    logging.getLogger("db").info("db ping")
    # pylint: disable=line-too-long
    logging.getLogger("uvicorn.access").info(
        '10.0.0.1:1 - "POST /v1/thing HTTP/1.1" 201',
    )
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    app_line = json.loads(out[0])
    access_line = json.loads(out[1])
    assert app_line["type"] == "application"
    assert "message" in app_line
    assert access_line["type"] == "http_access"
    assert access_line["method"] == "POST"
    assert access_line["path"] == "/v1/thing"
    assert access_line["status"] == 201
    assert access_line["message"] == "POST /v1/thing 201"
