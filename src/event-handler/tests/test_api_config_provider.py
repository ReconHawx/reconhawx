"""Unit tests for api_config_provider.ApiConfigProvider."""

import json
from unittest.mock import MagicMock, patch

import requests

from app.api_config_provider import CACHE_KEY_PREFIX, ApiConfigProvider
from app.config import NotifierConfig


def _cfg(**overrides):
    base = NotifierConfig()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_get_handlers_cache_hit_no_api_call():
    redis_client = MagicMock()
    handlers = [{"id": "h1", "event_type": "test.created"}]
    redis_client.get.return_value = json.dumps(handlers).encode("utf-8")
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch("app.api_config_provider.requests.get") as mock_get:
        out = provider.get_handlers("prog-a")

    assert out == handlers
    mock_get.assert_not_called()
    redis_client.get.assert_called_once_with(f"{CACHE_KEY_PREFIX}prog-a")


def test_get_handlers_cache_miss_api_success_sets_redis():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    handlers = [{"id": "x", "event_type": "assets.subdomain.created"}]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"handlers": handlers}

    cfg = _cfg(api_url="http://api:8000", internal_service_api_key="secret", api_config_cache_ttl=120)
    provider = ApiConfigProvider(cfg, redis_client)

    with patch("app.api_config_provider.requests.get", return_value=mock_resp) as mock_get:
        out = provider.get_handlers("my-program")

    assert out == handlers
    expected_key = f"{CACHE_KEY_PREFIX}my-program"
    mock_get.assert_called_once()
    call_kw = mock_get.call_args[1]
    assert call_kw["timeout"] == cfg.api_request_timeout
    assert "Authorization" in call_kw["headers"]
    assert call_kw["headers"]["Authorization"] == "Bearer secret"
    assert "/internal/event-handler-configs?program_name=my-program" in mock_get.call_args[0][0]

    redis_client.setex.assert_called_once()
    setex_args = redis_client.setex.call_args[0]
    assert setex_args[0] == expected_key
    assert setex_args[1] == 120
    assert json.loads(setex_args[2]) == handlers


def test_get_handlers_falsy_program_name_uses_global_cache_key():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    mock_resp = MagicMock(status_code=200, json=lambda: {"handlers": []})
    provider = ApiConfigProvider(
        _cfg(api_url="http://api", internal_service_api_key="k"),
        redis_client,
    )

    with patch("app.api_config_provider.requests.get", return_value=mock_resp):
        provider.get_handlers("")

    redis_client.get.assert_called_with(f"{CACHE_KEY_PREFIX}__global__")


def test_get_handlers_redis_get_raises_falls_through_to_api():
    redis_client = MagicMock()
    redis_client.get.side_effect = OSError("redis read")
    mock_resp = MagicMock(status_code=200, json=lambda: {"handlers": [{"id": "1"}]})

    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch("app.api_config_provider.requests.get", return_value=mock_resp):
        out = provider.get_handlers("p")

    assert len(out) == 1
    assert out[0]["id"] == "1"


def test_get_handlers_api_not_configured_returns_empty_no_setex():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    provider = ApiConfigProvider(_cfg(api_url="", internal_service_api_key="k"), redis_client)

    with patch("app.api_config_provider.requests.get") as mock_get:
        assert provider.get_handlers("p") == []
    mock_get.assert_not_called()
    redis_client.setex.assert_not_called()


def test_get_handlers_missing_internal_key_returns_empty():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key=""), redis_client)

    with patch("app.api_config_provider.requests.get") as mock_get:
        assert provider.get_handlers("p") == []
    mock_get.assert_not_called()


def test_get_handlers_api_non_200_returns_empty():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    mock_resp = MagicMock(status_code=503, text="unavailable")
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch("app.api_config_provider.requests.get", return_value=mock_resp):
        assert provider.get_handlers("p") == []


def test_get_handlers_api_timeout_returns_empty():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch(
        "app.api_config_provider.requests.get",
        side_effect=requests.exceptions.Timeout,
    ):
        assert provider.get_handlers("p") == []


def test_get_handlers_api_connection_error_returns_empty():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch(
        "app.api_config_provider.requests.get",
        side_effect=requests.exceptions.ConnectionError,
    ):
        assert provider.get_handlers("p") == []


def test_get_handlers_setex_raises_still_returns_handlers():
    redis_client = MagicMock()
    redis_client.get.return_value = None
    redis_client.setex.side_effect = OSError("write fail")
    mock_resp = MagicMock(status_code=200, json=lambda: {"handlers": [{"id": "z"}]})
    provider = ApiConfigProvider(_cfg(api_url="http://api", internal_service_api_key="k"), redis_client)

    with patch("app.api_config_provider.requests.get", return_value=mock_resp):
        out = provider.get_handlers("p")

    assert out == [{"id": "z"}]


def test_invalidate_cache_single_program():
    redis_client = MagicMock()
    provider = ApiConfigProvider(_cfg(), redis_client)
    provider.invalidate_cache("prog1")
    redis_client.delete.assert_called_once_with(f"{CACHE_KEY_PREFIX}prog1")


def test_invalidate_cache_all_programs_scan_iter():
    redis_client = MagicMock()
    keys = [f"{CACHE_KEY_PREFIX}a".encode(), f"{CACHE_KEY_PREFIX}b".encode()]
    redis_client.scan_iter.return_value = iter(keys)
    provider = ApiConfigProvider(_cfg(), redis_client)

    provider.invalidate_cache(None)

    redis_client.scan_iter.assert_called_once_with(match=f"{CACHE_KEY_PREFIX}*")
    assert redis_client.delete.call_count == 2


def test_invalidate_cache_redis_error_swallowed():
    redis_client = MagicMock()
    redis_client.delete.side_effect = OSError("boom")
    provider = ApiConfigProvider(_cfg(), redis_client)
    provider.invalidate_cache("x")  # should not raise
