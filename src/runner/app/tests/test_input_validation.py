"""Tests for runtime input validation (utils.input_validation)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tasks.base import AssetType
from utils.input_validation import (
    ValidationResult,
    validate_inputs_for_task,
    validate_value,
)


# -- validate_value: per-AssetType branches -------------------------------------------------


@pytest.mark.parametrize(
    "value,ok",
    [
        ("example.com", True),
        ("sub.example.co.uk", True),
        ("not a domain", False),
        ("invalid..com", False),
        ("", False),
    ],
)
def test_validate_value_subdomain(value, ok):
    assert validate_value(value, AssetType.SUBDOMAIN) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("1.2.3.4", True),
        ("255.255.255.255", True),
        ("2001:db8::1", True),
        ("::1", True),
        ("999.1.1.1", False),
        ("not-an-ip", False),
        ("", False),
    ],
)
def test_validate_value_ip_v4_and_v6(value, ok):
    assert validate_value(value, AssetType.IP) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("10.0.0.0/24", True),
        ("192.168.1.0/16", True),
        ("2001:db8::/32", True),
        ("10.0.0.1/33", False),
        ("not/a/cidr", False),
        ("", False),
    ],
)
def test_validate_value_cidr_v4_and_v6(value, ok):
    assert validate_value(value, AssetType.CIDR) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("https://example.com", True),
        ("http://sub.example.com:8080/path", True),
        ("ftp://example.com", False),
        ("not a url", False),
        ("example.com", False),
        ("", False),
    ],
)
def test_validate_value_url(value, ok):
    assert validate_value(value, AssetType.URL) is ok


def test_validate_value_apex_domain_uses_domain_check():
    assert validate_value("example.com", AssetType.APEX_DOMAIN) is True
    assert validate_value("not a domain", AssetType.APEX_DOMAIN) is False


@pytest.mark.parametrize(
    "asset_type",
    [AssetType.STRING, AssetType.SERVICE, AssetType.CERTIFICATE, AssetType.SCREENSHOT],
)
def test_validate_value_accept_all_types(asset_type):
    assert validate_value("literally anything", asset_type) is True
    assert validate_value("", asset_type) is True


def test_validate_value_non_string_is_accepted():
    # Upstream steps may pass pre-typed model objects; validator must not reject them.
    class FakeAsset:
        name = "example.com"

    assert validate_value(FakeAsset(), AssetType.SUBDOMAIN) is True


# -- validate_inputs_for_task --------------------------------------------------------------


def test_validate_inputs_for_task_empty_list():
    result = validate_inputs_for_task([], [AssetType.URL])
    assert isinstance(result, ValidationResult)
    assert result.kept == []
    assert result.dropped == 0
    assert result.by_type == {}
    assert result.samples == []


def test_validate_inputs_single_type_drops_invalid():
    values = ["https://a.example.com", "not a url", "http://b.example.com", "bad://x"]
    result = validate_inputs_for_task(values, [AssetType.URL])
    assert result.kept == ["https://a.example.com", "http://b.example.com"]
    assert result.dropped == 2
    assert result.by_type == {"invalid_url": 2}
    assert result.samples == ["not a url", "bad://x"]


def test_validate_inputs_multi_type_accepts_any_match():
    # test_http declares [SUBDOMAIN, URL]. A URL is valid even though it isn't a bare domain.
    values = ["example.com", "https://other.com", "not-valid-anything"]
    result = validate_inputs_for_task(values, [AssetType.SUBDOMAIN, AssetType.URL])
    assert result.kept == ["example.com", "https://other.com"]
    assert result.dropped == 1
    # Primary (first-declared) type is SUBDOMAIN, so that's the bucket key.
    assert result.by_type == {"invalid_subdomain": 1}
    assert result.samples == ["not-valid-anything"]


def test_validate_inputs_sample_cap():
    values = [f"not-url-{i}" for i in range(20)]
    result = validate_inputs_for_task(values, [AssetType.URL])
    assert result.dropped == 20
    assert len(result.samples) == 5
    assert result.samples == [f"not-url-{i}" for i in range(5)]


def test_validate_inputs_accept_all_short_circuit():
    values = ["a", "b", "c", "anything"]
    result = validate_inputs_for_task(values, [AssetType.STRING])
    assert result.kept == values
    assert result.dropped == 0
    assert result.by_type == {}
    assert result.samples == []


def test_validate_inputs_env_escape_hatch_disables_filtering():
    values = ["https://ok.com", "not a url at all"]
    with patch.dict(os.environ, {"RUNNER_INPUT_VALIDATION": "off"}):
        result = validate_inputs_for_task(values, [AssetType.URL])
    assert result.kept == values
    assert result.dropped == 0


def test_validate_inputs_no_allowed_types_is_accept_all():
    # Defensive: if a task somehow declares no input_type, validator must not block it.
    values = ["anything", "goes"]
    result = validate_inputs_for_task(values, [])
    assert result.kept == values
    assert result.dropped == 0
