"""Unit tests for handler_config.py"""

import logging

import pytest

from app.event_handlers import SimpleHandlerRegistry
from app.handler_config import HandlerSet, create_handlers_from_config


class TestHandlerSet:
    """Tests for HandlerSet built from in-memory handler dicts (same shape as API)."""

    def test_handlers_from_config_list(self):
        handlers_config = [
            {
                "id": "h_sub",
                "event_type": ["assets.subdomain.created"],
                "conditions": [{"type": "field_exists", "field": "name"}],
                "actions": [{"type": "log", "level": "info", "message_template": "Test"}],
            }
        ]
        hs = HandlerSet(handlers_config)
        handlers = hs.registry.get_handlers("assets.subdomain.created")
        assert len(handlers) == 1
        assert handlers[0].event_types == ["assets.subdomain.created"]
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

    def test_multi_event_type_registers_under_each(self):
        handlers_config = [
            {
                "id": "merged",
                "event_type": ["assets.subdomain.created", "assets.subdomain.updated"],
                "conditions": [],
                "actions": [{"type": "log", "level": "info", "message_template": "x"}],
            }
        ]
        hs = HandlerSet(handlers_config)
        h_created = hs.registry.get_handlers("assets.subdomain.created")
        h_updated = hs.registry.get_handlers("assets.subdomain.updated")
        assert len(h_created) == 1
        assert len(h_updated) == 1
        assert h_created[0] is h_updated[0]
        assert hs.registry.get_handler_by_id("merged") is h_created[0]

    @pytest.mark.asyncio
    async def test_conditions_by_event_type_branches_in_registry(self):
        handlers_config = [
            {
                "id": "merged_recon",
                "event_type": ["assets.subdomain.created", "assets.subdomain.updated"],
                "conditions": [],
                "conditions_by_event_type": {
                    "assets.subdomain.created": [
                        {
                            "type": "field_value",
                            "field": "resolution_status",
                            "operator": "equals",
                            "expected_value": "ok",
                        },
                    ],
                    "assets.subdomain.updated": [
                        {"type": "field_value", "field": "new_ip_count", "operator": "greater_than", "expected_value": 0},
                    ],
                },
                "actions": [{"type": "log", "level": "info", "message_template": "hit"}],
            }
        ]
        hs = HandlerSet(handlers_config)
        ok = await hs.handle_event(
            "assets.subdomain.created",
            {"event_type": "assets.subdomain.created", "resolution_status": "ok", "program_name": "p"},
        )
        assert len(ok) == 1
        miss = await hs.handle_event(
            "assets.subdomain.created",
            {"event_type": "assets.subdomain.created", "resolution_status": "bad", "program_name": "p"},
        )
        assert len(miss) == 0
        upd = await hs.handle_event(
            "assets.subdomain.updated",
            {"event_type": "assets.subdomain.updated", "new_ip_count": 2, "program_name": "p"},
        )
        assert len(upd) == 1

    def test_conditions_by_event_type_stale_key_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING)
        reg = SimpleHandlerRegistry()
        create_handlers_from_config(
            [
                {
                    "id": "stale_key_handler",
                    "event_type": ["a.created"],
                    "conditions_by_event_type": {
                        "not.in.event_type.list": [{"type": "field_exists", "field": "x"}],
                    },
                    "actions": [{"type": "log"}],
                }
            ],
            reg,
        )
        joined = " ".join(r.message for r in caplog.records)
        assert "not.in.event_type.list" in joined
        assert "not in event_type list" in joined
