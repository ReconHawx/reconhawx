"""Unit tests for main.SimpleNotifierApp."""

from unittest.mock import MagicMock, patch

import pytest

from app.main import SimpleNotifierApp


@pytest.fixture
def notifier_app():
    mock_redis = MagicMock()
    mock_sub = MagicMock()
    with patch("app.main.redis.from_url", return_value=mock_redis), patch(
        "app.main.EventsSubscriber", return_value=mock_sub
    ):
        yield SimpleNotifierApp()


@pytest.mark.asyncio
async def test_handle_event_empty_batch_returns_true(notifier_app):
    ok = await notifier_app.handle_event(
        "events.batch",
        {"event": "batch", "events": []},
    )
    assert ok is True


@pytest.mark.asyncio
async def test_handle_single_event_handlers_disabled_returns_true(notifier_app):
    notifier_app.cfg.enable_event_handlers = False
    event_data = {
        "event_type": "assets.subdomain.created",
        "program_name": "p1",
        "subject": "events.assets.subdomain.created",
    }
    with patch("app.main.normalize_event_data", return_value=event_data), patch(
        "app.main.should_skip_event", return_value=False
    ):
        ok = await notifier_app._handle_single_event("events.assets.subdomain.created", {})

    assert ok is True


@pytest.mark.asyncio
async def test_flush_pending_batches_skipped_when_no_batch_manager(notifier_app):
    notifier_app.cfg.enable_event_handlers = False
    notifier_app.batch_manager = None
    out = await notifier_app.flush_pending_batches()
    assert out["status"] == "skipped"
    assert out["flushed"] == 0
    assert "reason" in out


@pytest.mark.asyncio
async def test_clear_pending_batches_skipped_when_no_batch_manager(notifier_app):
    notifier_app.cfg.enable_event_handlers = False
    notifier_app.batch_manager = None
    out = await notifier_app.clear_pending_batches()
    assert out["status"] == "skipped"
    assert out["batches_cleared"] == 0


def test_get_handler_set_uses_cache_within_ttl(notifier_app):
    notifier_app.cfg.enable_event_handlers = True
    notifier_app.cfg.api_config_cache_ttl = 60
    notifier_app.api_config_provider = MagicMock()
    notifier_app.api_config_provider.get_handlers.return_value = []
    notifier_app._handler_set_cache.clear()

    with patch("app.main.time.time", side_effect=[100.0, 105.0]):
        h1 = notifier_app._get_handler_set("prog-a")
        h2 = notifier_app._get_handler_set("prog-a")

    assert h1 is h2
    notifier_app.api_config_provider.get_handlers.assert_called_once_with("prog-a")


def test_get_handler_set_refetches_after_ttl(notifier_app):
    notifier_app.cfg.enable_event_handlers = True
    notifier_app.cfg.api_config_cache_ttl = 60
    notifier_app.api_config_provider = MagicMock()
    notifier_app.api_config_provider.get_handlers.return_value = []
    notifier_app._handler_set_cache.clear()

    with patch("app.main.time.time", side_effect=[100.0, 105.0, 200.0]):
        notifier_app._get_handler_set("prog-b")
        notifier_app._get_handler_set("prog-b")
        notifier_app._get_handler_set("prog-b")

    assert notifier_app.api_config_provider.get_handlers.call_count == 2


@pytest.mark.asyncio
async def test_pause_resume_processing_toggle(notifier_app):
    assert notifier_app.is_processing_paused() is False
    await notifier_app.pause_processing()
    assert notifier_app.is_processing_paused() is True
    await notifier_app.resume_processing()
    assert notifier_app.is_processing_paused() is False
