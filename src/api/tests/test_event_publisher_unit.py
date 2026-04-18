"""Unit tests for RobustEventPublisher (no real NATS)."""

from unittest.mock import AsyncMock, patch

import pytest

from services.event_publisher import RobustEventPublisher


@pytest.mark.asyncio
async def test_publish_immediate_returns_false_when_connection_unavailable():
    pub = RobustEventPublisher()
    with patch.object(pub, "_ensure_connection", AsyncMock(return_value=False)):
        ok = await pub.publish_immediate("events.test.subject", {"x": 1})
    assert ok is False


def test_get_batch_status_no_batch():
    pub = RobustEventPublisher()
    assert pub.get_batch_status() == {"status": "no_batch", "events": 0}
