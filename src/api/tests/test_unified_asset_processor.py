"""Tests for unified asset processor event publishing."""

from unittest.mock import AsyncMock, patch

import pytest

from services.unified_asset_processor import (
    AssetBatchResult,
    UnifiedAssetProcessor,
    UnifiedProcessingResult,
)


@pytest.mark.asyncio
async def test_publish_completion_emits_implicit_apex_domain_created():
    """Subdomain batches can carry implicit apex creates; they must publish apex_domain.created."""
    processor = UnifiedAssetProcessor()
    result = UnifiedProcessingResult(
        job_id="job-test",
        program_id="00000000-0000-0000-0000-0000000000aa",
        program_name="prog-a",
    )
    result.asset_results["subdomain"] = AssetBatchResult(
        asset_type="subdomain",
        total_count=1,
        implicit_apex_created_events=[
            {
                "event": "asset.created",
                "asset_type": "apex_domain",
                "record_id": "00000000-0000-0000-0000-000000000001",
                "name": "example.com",
                "program_name": "prog-a",
                "notes": None,
                "whois_status": None,
            }
        ],
    )

    with patch("services.unified_asset_processor.publisher.publish", new_callable=AsyncMock) as mock_publish:
        await processor._publish_completion_events(result)

    apex_calls = [
        call
        for call in mock_publish.call_args_list
        if call.args and call.args[0] == "events.assets.apex_domain.created"
    ]
    assert len(apex_calls) == 1
    payload = apex_calls[0].args[1]
    assert payload["asset_type"] == "apex_domain"
    assert payload["record_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_publish_completion_emits_ct_asset_discovery_for_new_ct_monitor_subdomains():
    """New ct_monitor subdomains publish assets.ct_subdomain.discovered for notifications."""
    processor = UnifiedAssetProcessor()
    result = UnifiedProcessingResult(
        job_id="job-ct",
        program_id="11111111-1111-1111-1111-111111111111",
        program_name="prog-ct",
    )
    result.asset_results["subdomain"] = AssetBatchResult(
        asset_type="subdomain",
        total_count=2,
        created_assets=[
            {
                "event": "asset.created",
                "asset_type": "subdomain",
                "record_id": "00000000-0000-0000-0000-000000000001",
                "name": "new.example.com",
                "program_name": "prog-ct",
                "source": "ct_monitor",
            },
            {
                "event": "asset.created",
                "asset_type": "subdomain",
                "record_id": "00000000-0000-0000-0000-000000000002",
                "name": "other.example.com",
                "program_name": "prog-ct",
                "source": "subdomain_finder",
            },
        ],
    )

    with patch("services.unified_asset_processor.publisher.publish", new_callable=AsyncMock) as mock_publish:
        await processor._publish_completion_events(result)

    ct_calls = [
        call
        for call in mock_publish.call_args_list
        if call.args and call.args[0] == "events.assets.ct_subdomain.discovered"
    ]
    assert len(ct_calls) == 1
    payload = ct_calls[0].args[1]
    assert payload["event"] == "ct_asset_discovered"
    assert payload["name"] == "new.example.com"
    assert payload["program_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["program_name"] == "prog-ct"
    assert payload["source"] == "ct_monitoring"


@pytest.mark.asyncio
async def test_publish_completion_skips_ct_asset_discovery_without_created_assets():
    """Existing subdomains (skipped/updated only) must not emit CT discovery notifications."""
    processor = UnifiedAssetProcessor()
    result = UnifiedProcessingResult(
        job_id="job-skip",
        program_id="11111111-1111-1111-1111-111111111111",
        program_name="prog-ct",
    )
    result.asset_results["subdomain"] = AssetBatchResult(
        asset_type="subdomain",
        total_count=1,
        skipped_assets=[
            {
                "name": "existing.example.com",
                "program_name": "prog-ct",
                "reason": "duplicate",
            }
        ],
    )

    with patch("services.unified_asset_processor.publisher.publish", new_callable=AsyncMock) as mock_publish:
        await processor._publish_completion_events(result)

    ct_calls = [
        call
        for call in mock_publish.call_args_list
        if call.args and call.args[0] == "events.assets.ct_subdomain.discovered"
    ]
    assert ct_calls == []
