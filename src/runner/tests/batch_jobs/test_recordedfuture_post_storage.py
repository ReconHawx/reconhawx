"""Tests for RecordedFuture post-storage typosquat URL/screenshot ingest."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from batch_jobs.api_vendors.recordedfuture import RecordedFutureAdapter


PROGRAM_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PROGRAM_NAME = "desjardins"
DOMAIN = "www.example-typo.com"


@pytest.fixture
def adapter() -> RecordedFutureAdapter:
    return RecordedFutureAdapter(aiohttp.ClientTimeout(total=30))


@pytest.mark.asyncio
async def test_create_typosquat_url_includes_program_id(
    adapter: RecordedFutureAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://api:8000")

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"url_id": "url-123"})

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_response
    mock_cm.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_cm)

    url_id = await adapter._create_typosquat_url(
        DOMAIN, PROGRAM_NAME, PROGRAM_ID, session=mock_session
    )

    assert url_id == "url-123"
    mock_session.post.assert_called_once()
    _endpoint, kwargs = mock_session.post.call_args
    assert kwargs["json"]["program_id"] == PROGRAM_ID
    assert kwargs["json"]["program_name"] == PROGRAM_NAME
    assert kwargs["json"]["typosquat_domain"] == DOMAIN


@pytest.mark.asyncio
async def test_upload_screenshot_includes_program_id(
    adapter: RecordedFutureAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://api:8000")

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"file_id": "file-456"})

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_response
    mock_cm.__aexit__.return_value = None

    mock_upload_session = MagicMock()
    mock_upload_session.post = MagicMock(return_value=mock_cm)

    mock_client_session = MagicMock()
    mock_client_session.__aenter__ = AsyncMock(return_value=mock_upload_session)
    mock_client_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "batch_jobs.api_vendors.recordedfuture.extract_text_from_image_ocr",
        return_value=None,
    ), patch(
        "batch_jobs.api_vendors.recordedfuture.aiohttp.ClientSession",
        return_value=mock_client_session,
    ):
        await adapter._upload_screenshot(
            b"\x89PNG\r\n",
            DOMAIN,
            PROGRAM_NAME,
            PROGRAM_ID,
            "url-123",
            "image:abc",
        )

    mock_upload_session.post.assert_called_once()
    _endpoint, kwargs = mock_upload_session.post.call_args
    form_data = kwargs["data"]
    field_names = [field[0]["name"] for field in form_data._fields]
    assert "program_id" in field_names
    assert "program_name" in field_names
