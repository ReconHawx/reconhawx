"""Unit tests for discord.py"""

import pytest
from unittest.mock import patch, MagicMock

from app.discord import DiscordClient
from app.config import NotifierConfig


class TestDiscordClient:
    """Tests for DiscordClient."""

    def test_init_accepts_config(self):
        cfg = NotifierConfig()
        client = DiscordClient(cfg)
        assert client.cfg is cfg

    @patch("app.discord.requests.post")
    def test_send_success_on_200(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        client = DiscordClient(NotifierConfig())
        result = client.send("https://discord.com/api/webhooks/123/test", embeds=[{"title": "Test"}])
        assert result is True
        mock_post.assert_called_once()

    @patch("app.discord.requests.post")
    def test_send_success_on_204(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        client = DiscordClient(NotifierConfig())
        result = client.send("https://discord.com/api/webhooks/123/test", content="Hello")
        assert result is True

    @patch("app.discord.requests.post")
    def test_send_fails_on_4xx(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
        client = DiscordClient(NotifierConfig())
        result = client.send("https://discord.com/api/webhooks/123/test", content="Hello")
        assert result is False

    @patch("app.discord.requests.post")
    def test_send_retries_on_exception(self, mock_post):
        mock_post.side_effect = [ConnectionError("fail"), MagicMock(status_code=200)]
        client = DiscordClient(NotifierConfig())
        result = client.send("https://discord.com/api/webhooks/123/test", content="Hello", max_retries=2)
        assert result is True
        assert mock_post.call_count == 2
