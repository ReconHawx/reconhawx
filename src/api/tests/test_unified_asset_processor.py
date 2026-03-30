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
    result = UnifiedProcessingResult(job_id="job-test", program_name="prog-a")
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
