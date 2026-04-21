"""Unit tests for event handler config normalization (no DB)."""

from repository.event_handler_config_repo import _handler_to_row, _normalize_event_types


def test_normalize_event_types_string():
    assert _normalize_event_types("assets.subdomain.created") == ["assets.subdomain.created"]


def test_normalize_event_types_string_strips():
    assert _normalize_event_types("  x.y  ") == ["x.y"]


def test_normalize_event_types_list():
    assert _normalize_event_types(["a", "", "b", "  c  "]) == ["a", "b", "c"]


def test_normalize_event_types_none():
    assert _normalize_event_types(None) == []


def test_handler_to_row_multi_types():
    row = _handler_to_row(
        {
            "id": "my_handler",
            "event_type": ["assets.subdomain.created", "assets.subdomain.updated"],
            "description": "d",
            "conditions": [],
            "actions": [{"type": "log"}],
        }
    )
    assert row["handler_id"] == "my_handler"
    assert row["event_types"] == ["assets.subdomain.created", "assets.subdomain.updated"]
    assert row["config"]["description"] == "d"
    assert "event_type" not in row["config"]
    assert "id" not in row["config"]


def test_handler_to_row_legacy_string_coerced():
    row = _handler_to_row({"id": "h", "event_type": "findings.nuclei.high", "actions": []})
    assert row["event_types"] == ["findings.nuclei.high"]


def test_handler_to_row_conditions_by_event_type_in_config_jsonb():
    row = _handler_to_row(
        {
            "id": "h1",
            "event_type": ["a.created", "a.updated"],
            "conditions_by_event_type": {
                "a.created": [{"type": "field_exists", "field": "x"}],
            },
            "actions": [{"type": "log"}],
        }
    )
    assert row["handler_id"] == "h1"
    assert row["event_types"] == ["a.created", "a.updated"]
    assert row["config"]["conditions_by_event_type"]["a.created"][0]["type"] == "field_exists"
    assert "event_type" not in row["config"]
