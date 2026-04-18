"""Tests for pure helpers in ``task_executor`` (``AssetFilter``).

TaskExecutor itself drives NATS/K8s/Redis; covered at integration level.
The AssetFilter DSL is pure Python and worth pinning down.
"""

from __future__ import annotations

import pytest

from task_executor import AssetFilter


def test_empty_filter_includes_all() -> None:
    f = AssetFilter("")
    assets = [{"name": "a"}, {"name": "b"}]
    assert f.filter_assets(assets) == assets


@pytest.mark.parametrize(
    "expr,asset,expected",
    [
        ("name.contains:admin", {"name": "admin-panel"}, True),
        ("name.contains:admin", {"name": "other"}, False),
        ("name.startswith:api.", {"name": "api.example.com"}, True),
        ("name.endswith:.com", {"name": "api.example.com"}, True),
        ("name.equals:example.com", {"name": "example.com"}, True),
        ("name.equals:example.com", {"name": "EXAMPLE.COM"}, True),
        ("name.not_contains:staging", {"name": "prod.example.com"}, True),
        ("name.not_equals:test", {"name": "prod"}, True),
        ("name.regex:^api-.*-prod$", {"name": "api-v1-prod"}, True),
        ("name.regex:^api-.*-prod$", {"name": "api-dev"}, False),
        ("port.in:80,443,8080", {"port": 443}, True),
        ("port.in:80,443", {"port": 22}, False),
        ("name.contains:admin", {"other": "x"}, False),
    ],
)
def test_single_filter_operations(expr: str, asset: dict, expected: bool) -> None:
    assert AssetFilter(expr).evaluate(asset) is expected


def test_compound_and_requires_both() -> None:
    f = AssetFilter("name.contains:api and name.endswith:.com")
    assert f.evaluate({"name": "api.example.com"}) is True
    assert f.evaluate({"name": "api.example.org"}) is False
    assert f.evaluate({"name": "foo.example.com"}) is False


def test_compound_or_is_permissive() -> None:
    f = AssetFilter("name.equals:a or name.equals:b")
    assert f.evaluate({"name": "a"}) is True
    assert f.evaluate({"name": "b"}) is True
    assert f.evaluate({"name": "c"}) is False


def test_operator_precedence_and_over_or() -> None:
    # A and B or C and D == (A and B) or (C and D)
    f = AssetFilter(
        "name.contains:api and name.endswith:.com or "
        "name.contains:mail and name.endswith:.org"
    )
    assert f.evaluate({"name": "api.example.com"}) is True
    assert f.evaluate({"name": "mail.example.org"}) is True
    assert f.evaluate({"name": "api.example.org"}) is False


def test_invalid_syntax_raises() -> None:
    with pytest.raises(ValueError):
        AssetFilter("no-colon-here")
    with pytest.raises(ValueError):
        AssetFilter("name:value")


def test_filter_assets_logs_and_returns_matches() -> None:
    f = AssetFilter("name.contains:api")
    assets = [{"name": "api.x"}, {"name": "web.x"}, {"name": "api.y"}]
    assert f.filter_assets(assets) == [{"name": "api.x"}, {"name": "api.y"}]
