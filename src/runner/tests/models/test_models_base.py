"""Tests for ``models.base`` helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from models.base import serialize_datetime, utcnow


def test_serialize_datetime_none_returns_none() -> None:
    assert serialize_datetime(None) is None


def test_serialize_datetime_returns_iso() -> None:
    dt = datetime(2024, 1, 2, 3, 4, 5)
    assert serialize_datetime(dt) == "2024-01-02T03:04:05"


def test_utcnow_is_naive_but_near_utc() -> None:
    now = utcnow()
    assert now.tzinfo is None
    aware = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = abs((aware - now).total_seconds())
    assert delta < 5
