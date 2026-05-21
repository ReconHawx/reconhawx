"""Tests for canonical URL asset ingest normalization."""

from utils.url_utils import normalize_url_asset_payload, normalize_url_for_storage


def test_normalize_url_asset_payload_root_https():
    data = {"url": "https://EXAMPLE.com"}
    assert normalize_url_asset_payload(data) == "https://example.com:443/"
    assert data["hostname"] == "example.com"
    assert data["port"] == 443
    assert data["scheme"] == "https"
    assert data["path"] == "/"


def test_normalize_url_asset_payload_with_path():
    data = {"url": "http://test.org:8080/path/"}
    assert normalize_url_asset_payload(data) == "http://test.org:8080/path"
    assert data["port"] == 8080


def test_normalize_url_asset_payload_invalid():
    data = {"url": "not-a-url"}
    assert normalize_url_asset_payload(data) is None


def test_normalize_url_for_storage_matches_payload():
    raw = "https://Aa.Com/p"
    data = {"url": raw}
    canonical = normalize_url_asset_payload(data)
    assert canonical == normalize_url_for_storage(raw) == "https://aa.com:443/p"
