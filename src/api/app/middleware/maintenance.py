"""Return 503 during coordinated database maintenance (except allowlisted routes)."""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from services import maintenance_settings as maint_cfg

# Keep login/refresh reachable so operators can authenticate during maintenance (admin routes still
# require credentials). Aligns with AuthMiddleware public_paths for /auth/login and /auth/refresh.
ALLOWLIST_EXACT = frozenset({"/", "/status", "/auth/login", "/auth/refresh"})
ALLOWLIST_PREFIX = (
    "/admin/database/",
    "/internal/database-restore/pull",
)


def maintenance_bypass_for_tests() -> bool:
    return os.getenv("DISABLE_MAINTENANCE_MIDDLEWARE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class MaintenanceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable):
        if maintenance_bypass_for_tests():
            return await call_next(request)

        enabled, message, _meta = await maint_cfg.get_effective_maintenance()
        if not enabled:
            return await call_next(request)

        path = request.url.path
        if path in ALLOWLIST_EXACT:
            return await call_next(request)
        if any(path.startswith(p) for p in ALLOWLIST_PREFIX):
            return await call_next(request)

        body = {"detail": message, "code": "maintenance"}
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)
