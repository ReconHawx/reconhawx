"""Tests for asset discovery source helpers and ingest stamping."""

import pytest

from utils.asset_source import apply_lazy_source, normalize_asset_source


def test_normalize_asset_source():
    assert normalize_asset_source(None) is None
    assert normalize_asset_source("") is None
    assert normalize_asset_source("  subdomain_finder  ") == "subdomain_finder"
    assert normalize_asset_source("x" * 300) == ("x" * 255)


def test_apply_lazy_source_write_once():
    assert apply_lazy_source("subdomain_finder", "test_http") == "subdomain_finder"
    assert apply_lazy_source(None, "test_http") == "test_http"
    assert apply_lazy_source("", "ct_monitor") == "ct_monitor"


@pytest.mark.asyncio
async def test_extract_asset_data_stamps_request_source():
    from routes.assets import _extract_asset_data

    data = {
        "program_id": "00000000-0000-0000-0000-000000000001",
        "source": "subdomain_finder",
        "assets": {
            "subdomain": [{"name": "api.example.com"}],
            "ip": [{"ip": "1.2.3.4"}],
        },
    }
    extracted = await _extract_asset_data(data)
    assert extracted["subdomain"][0]["source"] == "subdomain_finder"
    assert extracted["ip"][0]["source"] == "subdomain_finder"


@pytest.mark.asyncio
async def test_extract_asset_data_task_name_alias():
    from routes.assets import _extract_asset_data

    data = {
        "program_id": "00000000-0000-0000-0000-000000000001",
        "task_name": "test_http",
        "assets": {"url": [{"url": "https://example.com/"}]},
    }
    extracted = await _extract_asset_data(data)
    assert extracted["url"][0]["source"] == "test_http"


@pytest.mark.asyncio
async def test_extract_asset_data_per_asset_override():
    from routes.assets import _extract_asset_data

    data = {
        "program_id": "00000000-0000-0000-0000-000000000001",
        "source": "subdomain_finder",
        "assets": {
            "subdomain": [{"name": "api.example.com", "source": "manual_import"}],
        },
    }
    extracted = await _extract_asset_data(data)
    assert extracted["subdomain"][0]["source"] == "manual_import"
