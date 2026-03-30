"""Unit tests for routing.py"""

import pytest

from app.routing import (
    parse_event_type,
    normalize_event_data,
    should_skip_event,
    extract_program_name,
    is_batch_event,
)


class TestParseEventType:
    """Tests for parse_event_type."""

    def test_removes_events_prefix(self):
        assert parse_event_type("events.assets.subdomain.created") == "assets.subdomain.created"

    def test_assets_subdomain_created(self):
        assert parse_event_type("events.assets.subdomain.created") == "assets.subdomain.created"

    def test_assets_subdomain_resolved(self):
        assert parse_event_type("events.assets.subdomain.resolved") == "assets.subdomain.resolved"

    def test_findings_typosquat_created(self):
        result = parse_event_type("events.findings.typosquat.created")
        assert result == "findings.typosquat.created"

    def test_findings_nuclei_with_severity_from_payload(self):
        payload = {"severity": "critical"}
        result = parse_event_type("events.findings.nuclei.created", payload)
        assert result == "findings.nuclei.critical"

    def test_findings_nuclei_no_severity_fallback(self):
        result = parse_event_type("events.findings.nuclei.created", {})
        assert result == "findings.nuclei.created"

    def test_test_workflow_trigger(self):
        result = parse_event_type("events.test.workflow.trigger")
        assert result == "test.workflow.trigger"

    def test_short_subject_returns_empty(self):
        result = parse_event_type("events")
        assert result == ""

    def test_single_part_returns_empty(self):
        result = parse_event_type("events.only")
        assert result == ""


class TestIsBatchEvent:
    """Tests for is_batch_event."""

    def test_batch_suffix_true(self):
        assert is_batch_event("events.assets.subdomain.batch") is True

    def test_no_batch_suffix_false(self):
        assert is_batch_event("events.assets.subdomain.created") is False


class TestExtractProgramName:
    """Tests for extract_program_name."""

    def test_extracts_program_name(self):
        payload = {"program_name": "my-program"}
        assert extract_program_name(payload) == "my-program"

    def test_missing_returns_unknown(self):
        assert extract_program_name({}) == "unknown"


class TestNormalizeEventData:
    """Tests for normalize_event_data."""

    def test_includes_subject_and_event_type(self):
        result = normalize_event_data("events.assets.subdomain.created", {"program_name": "p1"})
        assert result["subject"] == "events.assets.subdomain.created"
        assert result["event_type"] == "assets.subdomain.created"
        assert result["program_name"] == "p1"

    def test_promotes_payload_fields(self):
        payload = {"program_name": "p1", "name": "test.example.com", "extra": "value"}
        result = normalize_event_data("events.assets.subdomain.created", payload)
        assert result["name"] == "test.example.com"
        assert result["extra"] == "value"

    def test_subdomain_assets_single_creates_domain_vars(self):
        payload = {"program_name": "p1", "name": "api.example.com"}
        result = normalize_event_data("events.assets.subdomain.created", payload)
        assert result["domain_list"] == "api.example.com"
        assert result["domain_list_array"] == ["api.example.com"]
        assert result["domain_count"] == 1

    def test_subdomain_assets_batch_creates_domain_list(self):
        payload = {
            "program_name": "p1",
            "assets": [
                {"name": "a.example.com"},
                {"name": "b.example.com"},
            ],
        }
        result = normalize_event_data("events.assets.subdomain.created", payload)
        assert "a.example.com" in result["domain_list"]
        assert "b.example.com" in result["domain_list"]
        assert result["domain_list_array"] == ["a.example.com", "b.example.com"]
        assert result["domain_count"] == 2

    def test_findings_typosquat_promotes_fields(self):
        payload = {
            "program_name": "p1",
            "typo_domain": "gogle.com",
            "domain_registered": True,
        }
        result = normalize_event_data("events.findings.typosquat.created", payload)
        assert result["typo_domain"] == "gogle.com"
        assert result["domain_registered"] is True


class TestShouldSkipEvent:
    """Tests for should_skip_event."""

    def test_skips_without_program_name(self):
        event = {"event_type": "assets.subdomain.created", "program_name": ""}
        assert should_skip_event(event) is True

    def test_skips_with_none_program_name(self):
        event = {"event_type": "assets.subdomain.created"}
        assert should_skip_event(event) is True

    def test_skips_with_empty_event_type(self):
        event = {"event_type": "", "program_name": "p1"}
        assert should_skip_event(event) is True

    def test_does_not_skip_valid_event(self):
        event = {"event_type": "assets.subdomain.created", "program_name": "p1"}
        assert should_skip_event(event) is False
