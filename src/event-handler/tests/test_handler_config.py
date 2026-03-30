"""Unit tests for handler_config.py"""

import pytest

from app.handler_config import HandlerSet


class TestHandlerSet:
    """Tests for HandlerSet built from in-memory handler dicts (same shape as API)."""

    def test_handlers_from_config_list(self):
        handlers_config = [
            {
                "event_type": "assets.subdomain.created",
                "conditions": [{"type": "field_exists", "field": "name"}],
                "actions": [{"type": "log", "level": "info", "message_template": "Test"}],
            }
        ]
        hs = HandlerSet(handlers_config)
        handlers = hs.registry.get_handlers("assets.subdomain.created")
        assert len(handlers) == 1
        assert handlers[0].event_type == "assets.subdomain.created"

    def test_invalid_config_no_actions_skipped(self):
        handlers_config = [
            {
                "event_type": "assets.subdomain.created",
                "conditions": [],
                # no actions — skipped by create_handlers_from_config
            }
        ]
        hs = HandlerSet(handlers_config)
        assert len(hs.registry.get_handlers("assets.subdomain.created")) == 0
