"""Loki-friendly logging formatters and dictConfig (copy kept in sync per service image).

Structured JSON lines use a closed ``type`` enum (see ``LOG_TYPES``):

* ``application`` — default app loggers (``JsonLineFormatter`` / ``LogfmtFormatter``).
* ``http_access`` — HTTP access lines (``UvicornAccess*`` formatters, frontend nginx).

Every JSON line includes ``timestamp``, ``level``, ``logger``, ``service``, ``type``,
and ``message``. ``http_access`` adds ``client``, ``method``, ``path``,
``http_version``, ``status`` when parseable.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Literal

LogFormat = Literal["json", "logfmt", "text"]

# Closed enum for the JSON ``type`` field; do not emit arbitrary values from callers.
LOG_TYPES: tuple[str, ...] = ("application", "http_access")


def parse_log_format(value: str | None) -> LogFormat:
    v = (value or "json").strip().lower()
    if v in ("json", "logfmt", "text"):
        return v  # type: ignore[return-value]
    return "json"


def parse_log_level(name: str | None, default: int = logging.INFO) -> int:
    if not name:
        return default
    level = getattr(logging, str(name).upper(), None)
    return level if isinstance(level, int) else default


def service_name() -> str:
    return os.environ.get("RECON_SERVICE_NAME", "unknown")


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line for Loki ``| json``."""

    def __init__(self, *args: Any, service: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        svc = self._service if self._service is not None else service_name()
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": svc,
            "type": "application",
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _escape_logfmt(s: str) -> str:
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    if any(c in s for c in (" ", "\t", "\n", "=")):
        return f'"{s}"'
    return s


class LogfmtFormatter(logging.Formatter):
    """Compact key=value lines."""

    def __init__(self, *args: Any, service: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        svc = self._service if self._service is not None else service_name()
        parts = [
            f"time={_escape_logfmt(ts)}",
            f"level={_escape_logfmt(record.levelname)}",
            f"logger={_escape_logfmt(record.name)}",
            f"message={_escape_logfmt(record.getMessage())}",
            f"service={_escape_logfmt(svc)}",
            "type=application",
        ]
        if record.exc_info:
            parts.append(f"exc_info={_escape_logfmt(self.formatException(record.exc_info))}")
        return " ".join(parts)


def parse_uvicorn_access_message(msg: str) -> dict[str, Any] | None:
    """Parse default Uvicorn access line into structured fields (best-effort).

    Expected form::

        10.0.0.1:1234 - "GET /path HTTP/1.1" 200
    """
    m = re.match(
        r'^(?P<client>[^\s]+) - "([^"]+)"\s+(?P<status>\d+)\s*$',
        str(msg).strip(),
    )
    if not m:
        return None
    inner = m.group(2)
    toks = inner.split()
    if len(toks) < 3:
        return None
    http_vers = toks[-1]
    if not http_vers.upper().startswith("HTTP/"):
        return None
    return {
        "client": m.group("client"),
        "method": toks[0],
        "path": " ".join(toks[1:-1]),
        "http_version": http_vers,
        "status": int(m.group("status")),
    }


class UvicornAccessJsonLineFormatter(logging.Formatter):
    """Structured JSON for ``uvicorn.access`` (separate from application logs)."""

    def __init__(self, *args: Any, service: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        svc = self._service if self._service is not None else service_name()
        msg = record.getMessage()
        parsed = parse_uvicorn_access_message(msg)
        payload: dict[str, Any] = {
            "type": "http_access",
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "service": svc,
        }
        if parsed is not None:
            payload["client"] = parsed["client"]
            payload["method"] = parsed["method"]
            payload["path"] = parsed["path"]
            payload["http_version"] = parsed["http_version"]
            payload["status"] = parsed["status"]
            payload["message"] = f"{parsed['method']} {parsed['path']} {parsed['status']}"
        else:
            payload["message"] = msg
            payload["access_parse_error"] = True
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class UvicornAccessLogfmtFormatter(logging.Formatter):
    """Structured logfmt for ``uvicorn.access``."""

    def __init__(self, *args: Any, service: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        svc = self._service if self._service is not None else service_name()
        msg = record.getMessage()
        parts = [
            f'type="http_access"',
            f"time={_escape_logfmt(ts)}",
            f"level={_escape_logfmt(record.levelname)}",
            f"logger={_escape_logfmt(record.name)}",
            f"service={_escape_logfmt(svc)}",
        ]
        parsed = parse_uvicorn_access_message(msg)
        if parsed is not None:
            parts.append(f"client={_escape_logfmt(parsed['client'])}")
            parts.append(f"method={_escape_logfmt(parsed['method'])}")
            parts.append(f"path={_escape_logfmt(parsed['path'])}")
            parts.append(f"http_version={_escape_logfmt(parsed['http_version'])}")
            parts.append(f"status={parsed['status']}")
            synthetic = f"{parsed['method']} {parsed['path']} {parsed['status']}"
            parts.append(f"message={_escape_logfmt(synthetic)}")
        else:
            parts.append(f"message={_escape_logfmt(msg)}")
            parts.append("access_parse_error=true")
        if record.exc_info:
            parts.append(f"exc_info={_escape_logfmt(self.formatException(record.exc_info))}")
        return " ".join(parts)


def _formatter_spec(log_format: LogFormat, service: str) -> Dict[str, Any]:
    mod = __name__
    if log_format == "json":
        return {"()": f"{mod}.JsonLineFormatter", "service": service}
    if log_format == "logfmt":
        return {"()": f"{mod}.LogfmtFormatter", "service": service}
    return {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "datefmt": None}


def build_service_dict_config(
    *,
    service: str,
    log_format: LogFormat,
    root_level: int,
    text_format: str,
    text_datefmt: str | None,
    include_uvicorn: bool,
    stream: str = "ext://sys.stdout",
) -> Dict[str, Any]:
    """Full dictConfig: root + optional uvicorn.* (for API and embedded Uvicorn services)."""
    if log_format == "text":
        cfg: Dict[str, Any] = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"standard": {"format": text_format, "datefmt": text_datefmt}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "stream": stream,
                }
            },
            "root": {"level": root_level, "handlers": ["console"]},
        }
        if include_uvicorn:
            cfg["loggers"] = {
                "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
                "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
                "uvicorn.access": {"level": "INFO", "handlers": [], "propagate": True},
            }
        return cfg

    fmt_name = "structured"
    mod = __name__
    if include_uvicorn:
        access_key = "access_structured"
        if log_format == "json":
            access_spec: Dict[str, Any] = {
                "()": f"{mod}.UvicornAccessJsonLineFormatter",
                "service": service,
            }
        else:
            access_spec = {
                "()": f"{mod}.UvicornAccessLogfmtFormatter",
                "service": service,
            }
        cfg: Dict[str, Any] = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                fmt_name: _formatter_spec(log_format, service),
                access_key: access_spec,
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": fmt_name,
                    "stream": stream,
                },
                "access": {
                    "class": "logging.StreamHandler",
                    "formatter": access_key,
                    "stream": stream,
                },
            },
            "root": {"level": root_level, "handlers": ["console"]},
            "loggers": {
                "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
                "uvicorn.error": {"level": "INFO", "handlers": ["console"], "propagate": False},
                "uvicorn.access": {"level": "INFO", "handlers": ["access"], "propagate": False},
            },
        }
        return cfg

    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {fmt_name: _formatter_spec(log_format, service)},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": fmt_name,
                "stream": stream,
            }
        },
        "root": {"level": root_level, "handlers": ["console"]},
    }
    return cfg


def apply_service_logging(
    *,
    service: str,
    include_uvicorn: bool,
    log_format: str | None = None,
    root_level: int | None = None,
    text_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    text_datefmt: str | None = None,
    stream: str = "ext://sys.stdout",
) -> None:
    os.environ.setdefault("RECON_SERVICE_NAME", service)
    fmt = parse_log_format(log_format if log_format is not None else os.environ.get("LOG_FORMAT"))
    level = (
        root_level
        if root_level is not None
        else parse_log_level(os.environ.get("LOG_LEVEL"))
    )
    cfg = build_service_dict_config(
        service=service,
        log_format=fmt,
        root_level=level,
        text_format=text_format,
        text_datefmt=text_datefmt,
        include_uvicorn=include_uvicorn,
        stream=stream,
    )
    logging.config.dictConfig(cfg)
