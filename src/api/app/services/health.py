"""
Aggregated health checks for the API (database, Redis, NATS, internal auth).

Default readiness: HTTP 503 only when PostgreSQL is unavailable. Redis, NATS,
or internal-auth failures set overall ``degraded`` with HTTP 200.

Set ``API_READINESS_STRICT=true`` to return 503 if any check fails (strict
cluster readiness).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Literal, Tuple, TypedDict

import redis
from nats.aio.client import Client as NATS

from config.settings import settings
from db import test_connection

logger = logging.getLogger(__name__)

CheckStatus = Literal["ok", "error", "skipped"]


class CheckResult(TypedDict, total=False):
    status: CheckStatus
    detail: str
    stream: str


async def _check_database() -> CheckResult:
    try:
        ok = await asyncio.to_thread(test_connection)
        if ok:
            return {"status": "ok"}
        return {"status": "error", "detail": "connection or query failed"}
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        return {"status": "error", "detail": str(e)}


async def _check_redis() -> CheckResult:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    def _ping() -> None:
        r = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            r.ping()
        finally:
            r.close()

    try:
        await asyncio.to_thread(_ping)
        return {"status": "ok"}
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        return {"status": "error", "detail": str(e)}


async def _check_nats() -> CheckResult:
    url = settings.NATS_URL
    stream = settings.EVENTS_STREAM

    async def _probe() -> CheckResult:
        nc = NATS()
        try:
            await nc.connect(
                url,
                connect_timeout=2,
                reconnect_time_wait=0.1,
                max_reconnect_attempts=0,
                allow_reconnect=False,
            )
            js = nc.jetstream()
            await js.stream_info(stream)
            return {"status": "ok", "stream": stream}
        finally:
            try:
                await nc.close()
            except Exception:
                pass

    try:
        # Bounded so readiness probes (see api-deployment readinessProbe) stay reliable.
        return await asyncio.wait_for(_probe(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("NATS health check timed out (%s)", url)
        return {
            "status": "error",
            "detail": "connection or JetStream probe timed out",
            "stream": stream,
        }
    except Exception as e:
        logger.warning("NATS health check failed: %s", e)
        return {"status": "error", "detail": str(e), "stream": stream}


async def _check_internal_auth() -> CheckResult:
    key = os.getenv("INTERNAL_SERVICE_API_KEY")
    if not key:
        return {
            "status": "error",
            "detail": "INTERNAL_SERVICE_API_KEY is not set",
        }
    try:
        from services.internal_token_service import InternalTokenService

        token_service = InternalTokenService()
        data = await token_service.validate_token(key)
        if data:
            return {"status": "ok"}
        return {"status": "error", "detail": "token invalid or revoked"}
    except Exception as e:
        logger.warning("Internal auth health check failed: %s", e)
        return {"status": "error", "detail": str(e)}


def _rollup_status(checks: Dict[str, CheckResult]) -> Literal["healthy", "degraded", "unhealthy"]:
    db = checks.get("database", {}).get("status")
    if db != "ok":
        return "unhealthy"

    optional_keys: List[str] = ["redis", "nats", "internal_auth"]
    for k in optional_keys:
        if checks.get(k, {}).get("status") != "ok":
            return "degraded"
    return "healthy"


def _strict_mode() -> bool:
    return os.getenv("API_READINESS_STRICT", "").lower() in ("1", "true", "yes")


async def get_health_payload() -> Tuple[Dict[str, Any], int]:
    """
    Run all checks and return (response_body, http_status).
    """
    database = await _check_database()
    if database["status"] != "ok":
        redis_r, nats_r = await asyncio.gather(_check_redis(), _check_nats())
        internal_r: CheckResult = {
            "status": "error",
            "detail": "skipped while database is unavailable",
        }
    else:
        redis_r, nats_r, internal_r = await asyncio.gather(
            _check_redis(),
            _check_nats(),
            _check_internal_auth(),
        )

    checks: Dict[str, CheckResult] = {
        "database": database,
        "redis": redis_r,
        "nats": nats_r,
        "internal_auth": internal_r,
    }

    strict = _strict_mode()
    all_ok = all(c.get("status") == "ok" for c in checks.values())

    if strict:
        overall: Literal["healthy", "degraded", "unhealthy"] = (
            "healthy" if all_ok else "unhealthy"
        )
        http_status = 200 if all_ok else 503
    else:
        overall = _rollup_status(checks)
        http_status = 503 if checks["database"]["status"] != "ok" else 200

    body: Dict[str, Any] = {
        "status": overall,
        "service": "api",
        "version": os.getenv("APP_VERSION", "undefined"),
        "checks": checks,
    }
    if strict:
        body["readiness_mode"] = "strict"
    return body, http_status
