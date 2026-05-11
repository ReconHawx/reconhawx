"""Unified ``Finding`` model shape invariants (scanner-prefixed columns live in ``details`` JSONB)."""

from __future__ import annotations

from sqlalchemy import inspect

from models.postgres import Finding


def test_finding_table_has_no_scanner_prefixed_columns():
    forbidden_prefixes = ("nuclei_", "wpscan_", "broken_link_")
    for col in inspect(Finding).c:
        assert not col.name.startswith(forbidden_prefixes), col.name


def test_finding_table_has_no_assignment_column():
    names = {col.name for col in inspect(Finding).c}
    assert "assigned_to" not in names


def test_finding_has_expected_common_columns():
    names = {col.name for col in inspect(Finding).c}
    for required in (
        "id",
        "program_id",
        "source",
        "fingerprint",
        "title",
        "details",
        "severity",
        "observed_at",
    ):
        assert required in names


def test_finding_has_no_removed_scanner_level_columns():
    names = {col.name for col in inspect(Finding).c}
    for removed in ("status", "tags", "external_ids", "references"):
        assert removed not in names
