"""Unit tests for nats_client.py (EventsSubscriber, concurrent message processing)."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.nats_client import EventsSubscriber
from app.config import NotifierConfig


def _make_msg(subject: str, payload: dict):
    msg = MagicMock()
    msg.subject = subject
    msg.data = json.dumps(payload).encode("utf-8")
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()
    return msg


class TestProcessOneMessage:
    """Tests for _process_one_message in isolation."""

    @pytest.mark.asyncio
    async def test_handler_success_calls_ack(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        msg = _make_msg("events.test.one", {"key": "value"})
        handler = AsyncMock(return_value=True)

        await subscriber._process_one_message(msg, handler, None)

        handler.assert_awaited_once_with("events.test.one", {"key": "value"})
        msg.ack.assert_awaited_once()
        msg.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_failure_calls_nak(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        msg = _make_msg("events.test.two", {"key": "value"})
        handler = AsyncMock(return_value=False)

        await subscriber._process_one_message(msg, handler, None)

        handler.assert_awaited_once()
        msg.nak.assert_awaited_once()
        msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_raises_calls_nak(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        msg = _make_msg("events.test.three", {})
        handler = AsyncMock(side_effect=ValueError("handler failed"))

        await subscriber._process_one_message(msg, handler, None)

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_decode_error_passes_empty_payload_then_ack_or_nak_by_handler(self):
        """On JSON decode error, payload is {} and handler is still called; ack/nak follows handler return."""
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        msg = MagicMock()
        msg.subject = "events.test.bad"
        msg.data = b"not valid json {"
        msg.ack = AsyncMock()
        msg.nak = AsyncMock()
        handler = AsyncMock(return_value=True)

        await subscriber._process_one_message(msg, handler, None)

        handler.assert_awaited_once_with("events.test.bad", {})
        msg.ack.assert_awaited_once()
        msg.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_semaphore_when_given(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        msg = _make_msg("events.test.sem", {"x": 1})
        handler = AsyncMock(return_value=True)
        sem = asyncio.Semaphore(1)

        await subscriber._process_one_message(msg, handler, sem)

        handler.assert_awaited_once()
        msg.ack.assert_awaited_once()


class TestRunSequential:
    """Tests for run() with max_concurrent_messages=0 (sequential)."""

    @pytest.mark.asyncio
    async def test_processes_messages_sequentially_then_exits(self):
        cfg = NotifierConfig()
        cfg.max_concurrent_messages = 0
        subscriber = EventsSubscriber(cfg)
        subscriber.subscription = MagicMock()

        msg1 = _make_msg("events.a", {"i": 1})
        msg2 = _make_msg("events.b", {"i": 2})
        call_order = []

        async def track_handler(subject: str, payload: dict):
            call_order.append((subject, payload["i"]))
            return True

        fetch_calls = 0

        async def fetch_mock(*args, **kwargs):
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                return [msg1, msg2]
            await asyncio.sleep(100)

        subscriber.subscription.fetch = AsyncMock(side_effect=fetch_mock)

        task = asyncio.create_task(subscriber.run(track_handler))
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert call_order == [("events.a", 1), ("events.b", 2)]
        msg1.ack.assert_awaited_once()
        msg2.ack.assert_awaited_once()


class TestRunConcurrent:
    """Tests for run() with max_concurrent_messages > 0 (concurrent)."""

    @pytest.mark.asyncio
    async def test_processes_batch_concurrently_then_exits(self):
        cfg = NotifierConfig()
        cfg.max_concurrent_messages = 10
        subscriber = EventsSubscriber(cfg)
        subscriber.subscription = MagicMock()

        msg1 = _make_msg("events.c1", {"i": 1})
        msg2 = _make_msg("events.c2", {"i": 2})
        msg3 = _make_msg("events.c3", {"i": 3})
        handler_results = []

        async def track_handler(subject: str, payload: dict):
            await asyncio.sleep(0.02)
            handler_results.append((subject, payload["i"]))
            return True

        fetch_calls = 0

        async def fetch_mock(*args, **kwargs):
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                return [msg1, msg2, msg3]
            await asyncio.sleep(100)

        subscriber.subscription.fetch = AsyncMock(side_effect=fetch_mock)

        task = asyncio.create_task(subscriber.run(track_handler))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(handler_results) == 3
        assert set(r[0] for r in handler_results) == {"events.c1", "events.c2", "events.c3"}
        msg1.ack.assert_awaited_once()
        msg2.ack.assert_awaited_once()
        msg3.ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concurrent_respects_per_message_ack_nak(self):
        cfg = NotifierConfig()
        cfg.max_concurrent_messages = 5
        subscriber = EventsSubscriber(cfg)
        subscriber.subscription = MagicMock()

        msg_ack = _make_msg("events.ok", {"r": "ok"})
        msg_nak = _make_msg("events.fail", {"r": "fail"})
        handler = AsyncMock(side_effect=[True, False])

        fetch_calls = 0

        async def fetch_mock(*args, **kwargs):
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                return [msg_ack, msg_nak]
            await asyncio.sleep(100)

        subscriber.subscription.fetch = AsyncMock(side_effect=fetch_mock)

        task = asyncio.create_task(subscriber.run(handler))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert handler.await_count == 2
        msg_ack.ack.assert_awaited_once()
        msg_nak.nak.assert_awaited_once()


class TestRunPaused:
    """When is_paused returns True, fetch is not called."""

    @pytest.mark.asyncio
    async def test_paused_skips_fetch(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        subscriber.subscription = MagicMock()
        subscriber.subscription.fetch = AsyncMock(return_value=[])

        handler = AsyncMock(return_value=True)

        task = asyncio.create_task(
            subscriber.run(handler, is_paused=lambda: True),
        )
        await asyncio.sleep(0.4)
        subscriber.subscription.fetch.assert_not_called()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestRunRequiresSubscription:
    """Tests for run() preconditions."""

    @pytest.mark.asyncio
    async def test_run_raises_if_subscription_not_initialized(self):
        cfg = NotifierConfig()
        subscriber = EventsSubscriber(cfg)
        subscriber.subscription = None
        handler = AsyncMock(return_value=True)

        with pytest.raises(RuntimeError, match="not initialized"):
            await subscriber.run(handler)


class TestConfigMaxConcurrent:
    """Tests that config max_concurrent_messages is respected."""

    def test_config_has_max_concurrent_messages(self):
        cfg = NotifierConfig()
        assert hasattr(cfg, "max_concurrent_messages")
        assert isinstance(cfg.max_concurrent_messages, int)
        assert cfg.max_concurrent_messages >= 0

    def test_config_zero_means_sequential(self):
        cfg = NotifierConfig()
        cfg.max_concurrent_messages = 0
        subscriber = EventsSubscriber(cfg)
        assert subscriber.cfg.max_concurrent_messages == 0
