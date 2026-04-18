"""Tests for ``last_execution_threshold``."""

from __future__ import annotations

import pytest

from last_execution_threshold import (
    last_execution_threshold_to_hours,
    try_last_execution_threshold_to_hours,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        (24, 24),
        (1, 1),
        ("24", 24),
        ("1h", 1),
        ("2H", 2),
        ("1d", 24),
        ("2d", 48),
        ("1w", 168),
        (" 3d ", 72),
    ],
)
def test_valid_values(value, expected) -> None:
    assert last_execution_threshold_to_hours(value) == expected


@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, 1.5, "", "bogus", "5m", "0d", "nan"],
)
def test_invalid_uses_default(value) -> None:
    assert last_execution_threshold_to_hours(value, default_hours=99) == 99


def test_custom_default() -> None:
    assert last_execution_threshold_to_hours("bad", default_hours=5) == 5


def test_try_variant_returns_none_for_invalid() -> None:
    assert try_last_execution_threshold_to_hours(None) is None
    assert try_last_execution_threshold_to_hours("bogus") is None
    assert try_last_execution_threshold_to_hours(True) is None
    assert try_last_execution_threshold_to_hours(0) is None
    assert try_last_execution_threshold_to_hours(1.5) is None


def test_try_variant_returns_hours_for_valid() -> None:
    assert try_last_execution_threshold_to_hours("1d") == 24
    assert try_last_execution_threshold_to_hours(48) == 48
    assert try_last_execution_threshold_to_hours("2w") == 336
