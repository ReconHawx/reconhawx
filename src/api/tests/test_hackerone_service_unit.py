"""Unit tests for HackerOneService HTTP error mapping (no real API)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.hackerone_service import HackerOneService


def _client_that_returns(response: MagicMock):
    inner = MagicMock()
    inner.get = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_fetch_program_scope_maps_401_to_value_error():
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )

    with patch("services.hackerone_service.httpx.AsyncClient", return_value=_client_that_returns(mock_response)):
        svc = HackerOneService("user", "token")
        with pytest.raises(ValueError, match="Invalid HackerOne API credentials"):
            await svc.fetch_program_scope("acme")


@pytest.mark.asyncio
async def test_fetch_program_scope_maps_404_to_value_error():
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )

    with patch("services.hackerone_service.httpx.AsyncClient", return_value=_client_that_returns(mock_response)):
        svc = HackerOneService("user", "token")
        with pytest.raises(ValueError, match="not found on HackerOne"):
            await svc.fetch_program_scope("missing")


@pytest.mark.asyncio
async def test_fetch_program_scope_maps_timeout_to_value_error():
    inner = MagicMock()
    inner.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=None)

    with patch("services.hackerone_service.httpx.AsyncClient", return_value=cm):
        svc = HackerOneService("user", "token")
        with pytest.raises(ValueError, match="timed out"):
            await svc.fetch_program_scope("acme")
