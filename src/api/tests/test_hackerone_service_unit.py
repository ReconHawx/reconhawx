"""Unit tests for HackerOneService HTTP error mapping (no real API)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.hackerone_service import HackerOneService


def test_convert_scope_to_structured_includes_out_of_scope_without_bounty():
    """OOS URL/WILDCARD rows are often not bounty-eligible; they must still import."""
    svc = HackerOneService("user", "token")
    scopes = [
        {
            "type": "structured-scope",
            "attributes": {
                "asset_type": "URL",
                "asset_identifier": "vercel.com",
                "eligible_for_bounty": True,
                "eligible_for_submission": True,
            },
        },
        {
            "type": "structured-scope",
            "attributes": {
                "asset_type": "WILDCARD",
                "asset_identifier": "*.vercel.app",
                "eligible_for_bounty": False,
                "eligible_for_submission": False,
            },
        },
    ]
    in_scope, out_scope, summary = svc.convert_scope_to_structured(scopes)
    assert summary == {"in_scope": 1, "out_of_scope": 1}
    assert in_scope == [{"pattern": "vercel.com", "wildcard": False}]
    assert out_scope == [{"pattern": "*.vercel.app", "wildcard": True}]


def test_convert_scope_to_structured_skips_non_bounty_in_scope_only():
    """In-scope rows still require bounty eligibility."""
    svc = HackerOneService("user", "token")
    scopes = [
        {
            "attributes": {
                "asset_type": "URL",
                "asset_identifier": "example.com",
                "eligible_for_bounty": False,
                "eligible_for_submission": True,
            },
        },
    ]
    in_scope, out_scope, summary = svc.convert_scope_to_structured(scopes)
    assert in_scope == []
    assert out_scope == []
    assert summary == {"in_scope": 0, "out_of_scope": 0}


def test_convert_scope_to_regex_includes_out_of_scope_without_bounty():
    svc = HackerOneService("user", "token")
    scopes = [
        {
            "attributes": {
                "asset_type": "WILDCARD",
                "asset_identifier": "*.vercel.app",
                "eligible_for_bounty": False,
                "eligible_for_submission": False,
            },
        },
    ]
    in_re, out_re, summary = svc.convert_scope_to_regex(scopes)
    assert in_re == []
    assert len(out_re) == 1
    assert "vercel" in out_re[0]
    assert summary == {"in_scope": 0, "out_of_scope": 1}


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
