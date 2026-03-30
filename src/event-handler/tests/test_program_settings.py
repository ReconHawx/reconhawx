"""Unit tests for program_settings.py"""

import pytest
from unittest.mock import MagicMock, patch

from app.program_settings import ProgramSettingsProvider
from app.config import NotifierConfig


class TestProgramSettingsProvider:
    """Tests for ProgramSettingsProvider."""

    def test_get_default_settings_when_api_unavailable(self):
        redis = MagicMock()
        redis.get.return_value = None
        cfg = NotifierConfig()
        cfg.api_url = "http://api:8000"
        provider = ProgramSettingsProvider(cfg, redis)

        with patch("app.program_settings.requests.get") as mock_get:
            mock_get.side_effect = ConnectionError("Connection refused")
            settings = provider.get_program_settings("test-program")
        assert settings["enabled"] is False
        assert settings.get("discord_webhook_url") is None
        assert "events" in settings

    def test_get_program_settings_uses_cache(self):
        redis = MagicMock()
        cached = '{"enabled": true, "discord_webhook_url": "https://webhook.test", "events": {}}'
        redis.get.return_value = cached.encode("utf-8")
        cfg = NotifierConfig()
        provider = ProgramSettingsProvider(cfg, redis)
        settings = provider.get_program_settings("test-program")
        assert settings["enabled"] is True
        assert settings["discord_webhook_url"] == "https://webhook.test"

    def test_get_program_settings_from_api_200(self):
        redis = MagicMock()
        redis.get.return_value = None
        cfg = NotifierConfig()
        cfg.api_url = "http://api:8000"
        provider = ProgramSettingsProvider(cfg, redis)

        with patch("app.program_settings.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "notification_settings": {
                        "enabled": True,
                        "discord_webhook_url": "https://discord.test",
                        "events": {"assets": {"created": {"subdomain": True}}},
                    }
                },
            )
            settings = provider.get_program_settings("test-program")
        assert settings["enabled"] is True
        assert settings["discord_webhook_url"] == "https://discord.test"

    def test_get_program_settings_404_returns_default(self):
        redis = MagicMock()
        redis.get.return_value = None
        cfg = NotifierConfig()
        cfg.api_url = "http://api:8000"
        provider = ProgramSettingsProvider(cfg, redis)

        with patch("app.program_settings.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404)
            settings = provider.get_program_settings("nonexistent")
        assert settings["enabled"] is False
