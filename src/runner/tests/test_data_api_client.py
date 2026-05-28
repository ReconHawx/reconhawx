"""Tests for pure helpers on ``DataAPIClient``.

Async network methods are covered at the integration layer; this file exercises
the serialization / timeout helpers that can be unit-tested without aiohttp.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import pytest

from data_api_client import DataAPIClient


class _FakeEnum(Enum):
    SUBDOMAIN = "subdomain"
    IP = "ip"


@pytest.fixture
def client() -> DataAPIClient:
    return DataAPIClient(base_url="https://api.test/", api_key="k", timeout=30)


def test_base_url_strips_trailing_slash(client: DataAPIClient) -> None:
    assert client.base_url == "https://api.test"
    assert client._headers["Authorization"] == "Bearer k"


def test_convert_asset_keys_handles_enums_and_strings(client: DataAPIClient) -> None:
    out = client._convert_asset_keys_to_strings({_FakeEnum.SUBDOMAIN: [], "ip": [1]})
    assert out == {"subdomain": [], "ip": [1]}


def test_convert_assets_to_dicts_handles_pydantic_and_datetime(client: DataAPIClient) -> None:
    from models.assets import Ip

    now = datetime(2024, 1, 1, 0, 0, 0)
    ip = Ip(ip="1.2.3.4", created_at=now, updated_at=now)
    result = client._convert_assets_to_dicts({"ip": [ip]})
    assert result["ip"][0]["ip"] == "1.2.3.4"
    assert result["ip"][0]["created_at"] == "2024-01-01T00:00:00"


def test_convert_assets_to_dicts_passthrough_dicts(client: DataAPIClient) -> None:
    result = client._convert_assets_to_dicts({"x": [{"a": 1}]})
    assert result == {"x": [{"a": 1}]}


def test_deep_clean_for_json_handles_datetime_and_nested(client: DataAPIClient) -> None:
    payload = {"d": datetime(2024, 1, 2, 3, 4, 5), "nested": [{"x": datetime(2024, 1, 1)}]}
    cleaned = client._deep_clean_for_json(payload)
    assert cleaned["d"] == "2024-01-02T03:04:05"
    assert cleaned["nested"][0]["x"].startswith("2024-01-01")


def test_deep_clean_for_json_primitives(client: DataAPIClient) -> None:
    assert client._deep_clean_for_json(5) == 5
    assert client._deep_clean_for_json(None) is None
    assert client._deep_clean_for_json("x") == "x"


@pytest.mark.parametrize(
    "count,expected_min",
    [
        (10, 30),
        (1000, 30),
        (1500, 45),
        (5000, 105),
        (100000, 300),
    ],
)
def test_calculate_timeout_for_assets_scales(client: DataAPIClient, count: int, expected_min: int) -> None:
    assert client._calculate_timeout_for_assets(count) == expected_min


@pytest.mark.asyncio
async def test_post_typosquat_screenshot_findings_uses_multipart_session_without_json_content_type(
    client: DataAPIClient, monkeypatch
) -> None:
    """Multipart uploads must not inherit Content-Type: application/json from the main session."""
    import base64
    from unittest.mock import AsyncMock, MagicMock

    captured_sessions: list[dict] = []

    class FakeClientSession:
        def __init__(self, *, headers=None, **kwargs):
            captured_sessions.append(headers or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, **kwargs):
            response = MagicMock()
            response.status = 200
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=False)
            response.json = AsyncMock(return_value={"file_id": "abc"})
            response.text = AsyncMock(return_value="")
            return response

    monkeypatch.setattr("data_api_client.aiohttp.ClientSession", FakeClientSession)
    client.session = MagicMock()

    findings = [
        {
            "url": "https://example.com/",
            "image_data": base64.b64encode(b"\x89PNG").decode(),
            "filename": "shot.png",
        }
    ]

    result = await client.post_typosquat_screenshot_findings(findings, "prog-uuid")

    assert result["status"] == "success"
    assert len(captured_sessions) == 1
    assert captured_sessions[0] == {"Authorization": "Bearer k"}
    assert "Content-Type" not in captured_sessions[0]
