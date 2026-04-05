"""Tests for the event-handler HTTP API."""

import asyncio
from unittest.mock import MagicMock

import httpx

from app.http_api import create_http_app


def _mock_notifier(
    *,
    nats_connected: bool = True,
    redis_ok: bool = True,
    internal_key: str = "test-key",
    handlers: bool = True,
):
    n = MagicMock()
    if nats_connected:
        n.subscriber.nc = MagicMock()
        n.subscriber.nc.is_closed = False
    else:
        n.subscriber.nc = None
    if redis_ok:
        n.redis.ping = MagicMock(return_value=True)
    else:
        n.redis.ping = MagicMock(side_effect=OSError("redis down"))
    n.cfg.internal_service_api_key = internal_key
    n.cfg.enable_event_handlers = handlers
    n.cfg.nats_stream = "EVENTS"
    return n


async def _get_status(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/status")


def test_status_healthy():
    app = create_http_app(_mock_notifier())
    r = asyncio.run(_get_status(app))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["service"] == "event-handler"
    assert data["checks"]["nats"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"


def test_status_nats_down_returns_503():
    app = create_http_app(_mock_notifier(nats_connected=False))
    r = asyncio.run(_get_status(app))
    assert r.status_code == 503
    assert r.json()["status"] == "unhealthy"


def test_status_redis_down_degraded():
    app = create_http_app(_mock_notifier(redis_ok=False))
    r = asyncio.run(_get_status(app))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["status"] == "error"
