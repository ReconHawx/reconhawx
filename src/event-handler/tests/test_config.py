"""Unit tests for config.py"""

import os
import pytest

from app.config import NotifierConfig


class TestNotifierConfig:
    """Tests for NotifierConfig dataclass."""

    def test_default_nats_url(self):
        cfg = NotifierConfig()
        assert "nats" in cfg.nats_url
        assert "4222" in cfg.nats_url

    def test_default_redis_url(self):
        cfg = NotifierConfig()
        assert "redis" in cfg.redis_url

    def test_default_log_level(self):
        cfg = NotifierConfig()
        assert cfg.log_level in ("INFO", "DEBUG", "WARNING", "ERROR")

    def test_default_api_url(self):
        cfg = NotifierConfig()
        assert "api" in cfg.api_url or "8000" in cfg.api_url

    def test_default_max_items_is_int(self):
        cfg = NotifierConfig()
        assert isinstance(cfg.default_max_items, int)
        assert cfg.default_max_items > 0

    def test_default_max_delay_seconds_is_int(self):
        cfg = NotifierConfig()
        assert isinstance(cfg.default_max_delay_seconds, int)

    def test_enable_batch_processing_default(self):
        cfg = NotifierConfig()
        assert isinstance(cfg.enable_batch_processing, bool)

    def test_enable_event_handlers_default(self):
        cfg = NotifierConfig()
        assert isinstance(cfg.enable_event_handlers, bool)

    def test_http_listen_defaults(self):
        cfg = NotifierConfig()
        assert cfg.http_host == "0.0.0.0"
        assert cfg.http_port == 8000
