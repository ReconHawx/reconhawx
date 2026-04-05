"""
Small HTTP control surface for the event-handler (health today; pause/start later).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Literal, Tuple

from fastapi import FastAPI
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from .main import SimpleNotifierApp

logger = logging.getLogger(__name__)


def create_http_app(notifier: "SimpleNotifierApp") -> FastAPI:
    app = FastAPI(
        title="Event Handler",
        description="HTTP API for health and future control operations",
        version=os.getenv("APP_VERSION", "dev"),
    )

    @app.get("/status")
    async def status() -> JSONResponse:
        payload, status_code = await _status_payload(notifier)
        return JSONResponse(content=payload, status_code=status_code)

    return app


async def _status_payload(notifier: "SimpleNotifierApp") -> Tuple[Dict[str, Any], int]:
    nc = notifier.subscriber.nc
    nats_connected = nc is not None and not nc.is_closed

    redis_check: Dict[str, Any]
    try:
        await asyncio.to_thread(notifier.redis.ping)
        redis_check = {"status": "ok"}
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        redis_check = {"status": "error", "detail": str(e)}

    internal_key = notifier.cfg.internal_service_api_key
    internal_check: Dict[str, Any]
    if internal_key:
        internal_check = {"status": "ok", "configured": True}
    else:
        internal_check = {
            "status": "error",
            "configured": False,
            "detail": "INTERNAL_SERVICE_API_KEY is not set",
        }

    handlers_enabled = notifier.cfg.enable_event_handlers

    checks = {
        "nats": {
            "status": "ok" if nats_connected else "error",
            **(
                {"detail": "not connected"}
                if not nats_connected
                else {"stream": notifier.cfg.nats_stream}
            ),
        },
        "redis": redis_check,
        "internal_auth": internal_check,
        "event_handlers": {
            "status": "ok" if handlers_enabled else "skipped",
            "enabled": handlers_enabled,
        },
    }

    overall: Literal["healthy", "degraded", "unhealthy"]
    if not nats_connected:
        overall = "unhealthy"
        http_status = 503
    elif redis_check["status"] != "ok":
        overall = "degraded"
        http_status = 200
    elif internal_check["status"] != "ok":
        overall = "degraded"
        http_status = 200
    else:
        overall = "healthy"
        http_status = 200

    body: Dict[str, Any] = {
        "status": overall,
        "service": "event-handler",
        "version": os.getenv("APP_VERSION", "undefined"),
        "checks": checks,
    }
    return body, http_status
