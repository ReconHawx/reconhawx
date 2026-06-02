"""Tests for certstream-server Kubernetes scaler (no real cluster)."""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_certstream_scale_enabled_from_env_explicit_off(monkeypatch):
    from certstream_k8s import certstream_scale_enabled_from_env

    monkeypatch.setenv("CT_CERTSTREAM_SCALE_ENABLED", "off")
    assert certstream_scale_enabled_from_env() is False


def test_certstream_scale_enabled_from_env_explicit_on(monkeypatch):
    from certstream_k8s import certstream_scale_enabled_from_env

    monkeypatch.setenv("CT_CERTSTREAM_SCALE_ENABLED", "true")
    assert certstream_scale_enabled_from_env() is True


def test_certstream_scale_enabled_auto_detect_token(monkeypatch):
    from certstream_k8s import _SA_TOKEN_PATH, certstream_scale_enabled_from_env

    monkeypatch.delenv("CT_CERTSTREAM_SCALE_ENABLED", raising=False)
    monkeypatch.setattr("certstream_k8s.os.path.isfile", lambda p: p == _SA_TOKEN_PATH)
    assert certstream_scale_enabled_from_env() is True
    monkeypatch.setattr("certstream_k8s.os.path.isfile", lambda p: False)
    assert certstream_scale_enabled_from_env() is False


def test_certstream_health_url_from_ws():
    from certstream_k8s import certstream_health_url_from_ws

    assert (
        certstream_health_url_from_ws("ws://certstream:4000/")
        == "http://certstream:4000/example.json"
    )
    assert (
        certstream_health_url_from_ws("wss://certstream.example:4000")
        == "https://certstream.example:4000/example.json"
    )


@pytest.mark.asyncio
async def test_scale_disabled_is_noop():
    from certstream_k8s import scale_certstream_deployment

    ok = await scale_certstream_deployment(1, enabled=False)
    assert ok is True


@pytest.mark.asyncio
async def test_scale_missing_api_config_returns_false(monkeypatch):
    from certstream_k8s import scale_certstream_deployment

    monkeypatch.setenv("CT_CERTSTREAM_SCALE_ENABLED", "true")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    ok = await scale_certstream_deployment(1, enabled=True)
    assert ok is False


@pytest.mark.asyncio
async def test_scale_patch_success(monkeypatch):
    from certstream_k8s import scale_certstream_deployment

    monkeypatch.setenv("CT_CERTSTREAM_SCALE_ENABLED", "true")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "kubernetes.default")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "443")

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.patch = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("certstream_k8s._load_token", AsyncMock(return_value="tok")):
        with patch("certstream_k8s._ssl_context", return_value=ssl.create_default_context()):
            with patch("certstream_k8s.aiohttp.ClientSession", return_value=mock_session):
                with patch("certstream_k8s.aiohttp.TCPConnector"):
                    ok = await scale_certstream_deployment(
                        0, deployment_name="certstream-server", namespace="reconhawx"
                    )
    assert ok is True
    mock_session.patch.assert_called_once()
    call_kwargs = mock_session.patch.call_args
    assert "certstream-server/scale" in call_kwargs[0][0]
    assert call_kwargs[1]["json"] == {"spec": {"replicas": 0}}


@pytest.mark.asyncio
async def test_wait_for_certstream_http_ready_success():
    from certstream_k8s import wait_for_certstream_http_ready

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("certstream_k8s.aiohttp.ClientSession", return_value=mock_session):
        ready = await wait_for_certstream_http_ready(
            "http://certstream:4000/example.json",
            timeout_sec=1.0,
            poll_interval_sec=0.01,
        )
    assert ready is True
