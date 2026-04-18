"""Route tests for /wordlists (upload validation, dynamic create, list permissions)."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from models.wordlist import DynamicWordlistType


@pytest.mark.asyncio
async def test_upload_rejects_non_plain_content_type(
    client: httpx.AsyncClient, mock_user_superuser
):
    files = {"file": ("w.txt", BytesIO(b"line1"), "application/octet-stream")}
    data = {"name": "badmime"}
    r = await client.post("/wordlists", files=files, data=data)
    assert r.status_code == 400
    assert "text" in r.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(client: httpx.AsyncClient, mock_user_superuser):
    files = {"file": ("empty.txt", BytesIO(b""), "text/plain")}
    data = {"name": "emptywl"}
    r = await client.post("/wordlists", files=files, data=data)
    assert r.status_code == 400
    assert "empty" in r.json().get("detail", "").lower()


@pytest.mark.asyncio
@patch("routes.wordlists.wordlist_repository.create_wordlist", new_callable=AsyncMock)
async def test_upload_success(mock_create, client: httpx.AsyncClient, mock_user_superuser):
    mock_create.return_value = {
        "id": "wl-1",
        "name": "mywl",
        "filename": "words.txt",
        "file_size": 5,
        "word_count": 2,
    }
    files = {"file": ("words.txt", BytesIO(b"a\nb\n"), "text/plain")}
    data = {"name": "mywl", "description": "d"}
    r = await client.post("/wordlists", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["id"] == "wl-1"
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_forbidden_wrong_program(
    client: httpx.AsyncClient, mock_user_manager
):
    """program_name must be a key in program_permissions for non-superusers."""
    files = {"file": ("w.txt", BytesIO(b"x"), "text/plain")}
    data = {"name": "n", "program_name": "not-my-program"}
    r = await client.post("/wordlists", files=files, data=data)
    assert r.status_code == 403


@pytest.mark.asyncio
@patch("routes.wordlists.wordlist_repository.create_dynamic_wordlist", new_callable=AsyncMock)
async def test_dynamic_create_success(mock_dyn, client: httpx.AsyncClient, mock_user_manager):
    mock_dyn.return_value = {
        "id": "dyn-1",
        "name": "dynwl",
        "dynamic_type": "subdomain_prefixes",
        "program_name": "program-a",
        "word_count": 42,
    }
    payload = {
        "name": "dynwl",
        "description": "d",
        "dynamic_type": DynamicWordlistType.SUBDOMAIN_PREFIXES.value,
        "program_name": "program-a",
        "tags": [],
    }
    r = await client.post("/wordlists/dynamic", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["word_count"] == 42
    mock_dyn.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_create_forbidden_program(client: httpx.AsyncClient, mock_user_manager):
    payload = {
        "name": "x",
        "dynamic_type": DynamicWordlistType.SUBDOMAIN_PREFIXES.value,
        "program_name": "forbidden-program",
    }
    r = await client.post("/wordlists/dynamic", json=payload)
    assert r.status_code == 403


@pytest.mark.asyncio
@patch("routes.wordlists.wordlist_repository.list_wordlists", new_callable=AsyncMock)
async def test_list_respects_program_query_filter(mock_list, client: httpx.AsyncClient, mock_user_manager):
    mock_list.return_value = {"wordlists": [], "total": 0}
    r = await client.get("/wordlists", params={"program_name": "program-a"})
    assert r.status_code == 200
    mock_list.assert_awaited()


@pytest.mark.asyncio
async def test_list_forbidden_program_filter(client: httpx.AsyncClient, mock_user_manager):
    r = await client.get("/wordlists", params={"program_name": "other-program"})
    assert r.status_code == 403
