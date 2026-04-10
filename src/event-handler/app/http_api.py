"""
Small HTTP control surface for the event-handler (health today; pause/start later).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from .main import SimpleNotifierApp

logger = logging.getLogger(__name__)


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def create_internal_auth_dependency(notifier: "SimpleNotifierApp"):
    def _require_internal_auth(
        authorization: Optional[str] = Header(None, alias="Authorization"),
    ) -> None:
        expected = (notifier.cfg.internal_service_api_key or "").strip()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="INTERNAL_SERVICE_API_KEY is not configured; control endpoints disabled",
            )
        token = _bearer_token(authorization)
        if not token or token != expected:
            raise HTTPException(status_code=401, detail="Invalid or missing internal service token")

    return _require_internal_auth


def create_http_app(notifier: "SimpleNotifierApp") -> FastAPI:
    app = FastAPI(
        title="Event Handler",
        description="HTTP API for health and future control operations",
        version=os.getenv("APP_VERSION", "dev"),
    )
    internal_auth = create_internal_auth_dependency(notifier)

    @app.get("/status")
    async def status() -> JSONResponse:
        payload, status_code = await _status_payload(notifier)
        return JSONResponse(content=payload, status_code=status_code)

    @app.post("/control/pause")
    async def pause(_: None = Depends(internal_auth)) -> Dict[str, Any]:
        await notifier.pause_processing()
        return {"status": "ok", "processing_paused": True}

    @app.post("/control/resume")
    async def resume(_: None = Depends(internal_auth)) -> Dict[str, Any]:
        await notifier.resume_processing()
        return {"status": "ok", "processing_paused": False}

    @app.post("/control/flush-batches")
    async def flush_batches(_: None = Depends(internal_auth)) -> Dict[str, Any]:
        return await notifier.flush_pending_batches()

    @app.post("/control/clear-batches")
    async def clear_batches(_: None = Depends(internal_auth)) -> Dict[str, Any]:
        return await notifier.clear_pending_batches()

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
    processing_paused = notifier.is_processing_paused()

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
        "processing": {
            "status": "paused" if processing_paused else "running",
            "paused": processing_paused,
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
        "processing_paused": processing_paused,
        "checks": checks,
    }
    return body, http_status
