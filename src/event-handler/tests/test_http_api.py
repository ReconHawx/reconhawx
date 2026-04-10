"""Tests for the event-handler HTTP API."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.http_api import create_http_app


def _mock_notifier(
    *,
    nats_connected: bool = True,
    redis_ok: bool = True,
    internal_key: str = "test-key",
    handlers: bool = True,
    processing_paused: bool = False,
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
    n.is_processing_paused = MagicMock(return_value=processing_paused)
    n.pause_processing = AsyncMock()
    n.resume_processing = AsyncMock()
    n.flush_pending_batches = AsyncMock(
        return_value={
            "status": "ok",
            "flushed": 0,
            "orphans_cleared": 0,
            "errors": [],
            "pending_seen": 0,
        }
    )
    n.clear_pending_batches = AsyncMock(
        return_value={
            "status": "ok",
            "batches_cleared": 0,
            "events_discarded": 0,
            "errors": [],
        }
    )
    return n


async def _get_status(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/status")


async def _post(app, path: str, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, headers=headers or {})


def test_status_healthy():
    app = create_http_app(_mock_notifier())
    r = asyncio.run(_get_status(app))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["service"] == "event-handler"
    assert data["processing_paused"] is False
    assert data["checks"]["nats"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"
    assert data["checks"]["processing"]["paused"] is False


def test_status_when_paused_still_200():
    app = create_http_app(_mock_notifier(processing_paused=True))
    r = asyncio.run(_get_status(app))
    assert r.status_code == 200
    data = r.json()
    assert data["processing_paused"] is True
    assert data["checks"]["processing"]["paused"] is True
    assert data["checks"]["processing"]["status"] == "paused"


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


def test_pause_requires_auth():
    app = create_http_app(_mock_notifier())
    r = asyncio.run(_post(app, "/control/pause"))
    assert r.status_code == 401


def test_pause_accepts_bearer():
    notifier = _mock_notifier()
    app = create_http_app(notifier)
    r = asyncio.run(
        _post(app, "/control/pause", headers={"Authorization": "Bearer test-key"})
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "processing_paused": True}
    notifier.pause_processing.assert_awaited_once()


def test_resume_accepts_bearer():
    notifier = _mock_notifier()
    app = create_http_app(notifier)
    r = asyncio.run(
        _post(app, "/control/resume", headers={"Authorization": "Bearer test-key"})
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "processing_paused": False}
    notifier.resume_processing.assert_awaited_once()


def test_control_503_when_no_internal_key_configured():
    notifier = _mock_notifier(internal_key="")
    app = create_http_app(notifier)
    r = asyncio.run(
        _post(app, "/control/pause", headers={"Authorization": "Bearer x"})
    )
    assert r.status_code == 503


def test_flush_batches_requires_auth():
    app = create_http_app(_mock_notifier())
    r = asyncio.run(_post(app, "/control/flush-batches"))
    assert r.status_code == 401


def test_flush_batches_accepts_bearer():
    notifier = _mock_notifier()
    app = create_http_app(notifier)
    r = asyncio.run(
        _post(app, "/control/flush-batches", headers={"Authorization": "Bearer test-key"})
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "flushed" in data
    notifier.flush_pending_batches.assert_awaited_once()


def test_clear_batches_requires_auth():
    app = create_http_app(_mock_notifier())
    r = asyncio.run(_post(app, "/control/clear-batches"))
    assert r.status_code == 401


def test_clear_batches_accepts_bearer():
    notifier = _mock_notifier()
    app = create_http_app(notifier)
    r = asyncio.run(
        _post(app, "/control/clear-batches", headers={"Authorization": "Bearer test-key"})
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "batches_cleared" in data
    notifier.clear_pending_batches.assert_awaited_once()
