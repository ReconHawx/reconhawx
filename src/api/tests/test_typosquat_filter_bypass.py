"""Tests for ignore_typosquat_filtering on typosquat domain insert."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
@patch("repository.typosquat_findings_repo.ApexDomainAssetsRepository.get_apex_domain_names_for_program", new_callable=AsyncMock)
@patch("repository.typosquat_findings_repo.TyposquatFilteringService.should_insert_domain")
@patch("repository.typosquat_findings_repo.resolve_program_from_payload")
@patch("repository.typosquat_findings_repo.get_db_session")
async def test_create_typosquat_finding_filtered_without_bypass(
    mock_session,
    mock_resolve_program,
    mock_should_insert,
    mock_asset_apex,
):
    from repository.typosquat_findings_repo import TyposquatFindingsRepository

    program = MagicMock()
    program.id = uuid4()
    program.name = "test-program"
    program.protected_domains = ["brand.com"]
    program.protected_subdomain_prefixes = []
    program.typosquat_filtering_settings = {"enabled": True}

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_session.return_value.__aenter__.return_value = mock_db
    mock_resolve_program.return_value = program
    mock_should_insert.return_value = (False, "whitelisted_apex:partner.com")
    mock_asset_apex.return_value = []

    record_id, action, event_data = await TyposquatFindingsRepository.create_or_update_typosquat_finding(
        {
            "typo_domain": "app.partner.com",
            "program_name": "test-program",
        }
    )

    assert record_id is None
    assert action == "filtered"
    assert event_data["filter_reason"] == "whitelisted_apex:partner.com"


@pytest.mark.asyncio
@patch("repository.typosquat_findings_repo.TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session")
@patch("repository.typosquat_findings_repo.ApexDomainAssetsRepository.get_apex_domain_names_for_program", new_callable=AsyncMock)
@patch("repository.typosquat_findings_repo.TyposquatFilteringService.should_insert_domain")
@patch("repository.typosquat_findings_repo.resolve_program_from_payload")
@patch("repository.typosquat_findings_repo.get_db_session")
async def test_create_typosquat_finding_inserts_with_bypass(
    mock_session,
    mock_resolve_program,
    mock_should_insert,
    mock_asset_apex,
    mock_find_or_create_apex,
):
    from repository.typosquat_findings_repo import TyposquatFindingsRepository

    program = MagicMock()
    program.id = uuid4()
    program.name = "test-program"
    program.protected_domains = ["brand.com"]
    program.protected_subdomain_prefixes = []
    program.typosquat_filtering_settings = {"enabled": True}

    apex_row = MagicMock()
    apex_row.id = uuid4()

    new_domain = MagicMock()
    new_domain.id = uuid4()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock(side_effect=lambda row: setattr(row, "id", new_domain.id))
    mock_session.return_value.__aenter__.return_value = mock_db
    mock_resolve_program.return_value = program
    mock_should_insert.return_value = (False, "whitelisted_apex:partner.com")
    mock_asset_apex.return_value = []
    mock_find_or_create_apex.return_value = apex_row

    record_id, action, event_data = await TyposquatFindingsRepository.create_or_update_typosquat_finding(
        {
            "typo_domain": "app.partner.com",
            "program_name": "test-program",
        },
        ignore_typosquat_filtering=True,
    )

    assert action == "created"
    assert record_id is not None
    assert event_data is not None
    mock_db.add.assert_called()
