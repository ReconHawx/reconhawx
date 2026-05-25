"""Tests for task_last_executions target_key promotion helpers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

from models.postgres import TaskLastExecution
from repository.task_history_repo import normalize_target_key
from repository.task_last_executions_repo import (
    TaskLastExecutionsRepository,
    build_promotion_entry,
    canonical_keys_for_asset,
)


def test_canonical_keys_for_asset_subdomain():
    keys = canonical_keys_for_asset("subdomain", {"name": "Host.Example."})
    assert keys == ["host.example"]


def test_canonical_keys_for_asset_ip():
    keys = canonical_keys_for_asset("ip", {"ip_address": "8.8.8.8"})
    assert keys == ["8.8.8.8"]


def test_canonical_keys_for_asset_url():
    keys = canonical_keys_for_asset(
        "url",
        {"url": "https://WWW.Example.COM/path"},
    )
    assert len(keys) == 1
    assert "example.com" in keys[0].lower()


def test_canonical_keys_for_asset_skips_service():
    assert canonical_keys_for_asset("service", {"record_id": str(uuid.uuid4())}) == []


def test_build_promotion_entry_from_event():
    aid = uuid.uuid4()
    entry = build_promotion_entry(
        {
            "asset_type": "subdomain",
            "record_id": str(aid),
            "name": "sub.example.com",
        }
    )
    assert entry is not None
    assert entry["asset_id"] == aid
    assert entry["asset_type"] == "subdomain"
    assert entry["target_keys"] == ["sub.example.com"]


def test_promote_target_keys_sync_upserts_and_deletes():
    db = MagicMock()
    program_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    completed = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    target_row = MagicMock(
        spec=TaskLastExecution,
        task_type="nuclei_scan",
        params_fingerprint="fp1",
        last_success_at=completed,
    )
    db.query.return_value.filter.return_value.all.return_value = [target_row]

    with patch.object(
        TaskLastExecutionsRepository,
        "upsert_success_sync",
    ) as mock_upsert:
        count = TaskLastExecutionsRepository.promote_target_keys_sync(
            db,
            program_id,
            asset_type="subdomain",
            asset_id=asset_id,
            target_keys=["sub.example.com"],
        )

    assert count == 1
    mock_upsert.assert_called_once_with(
        db,
        program_id=program_id,
        task_type="nuclei_scan",
        asset_type="subdomain",
        asset_id=asset_id,
        params_fingerprint="fp1",
        last_success_at=completed,
    )
    db.delete.assert_called_once_with(target_row)


def test_promote_target_keys_batch_sync_multiple_fingerprints():
    db = MagicMock()
    program_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    completed = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    row_a = MagicMock(
        task_type="nuclei_scan",
        params_fingerprint="fp_a",
        last_success_at=completed,
    )
    row_b = MagicMock(
        task_type="port_scan",
        params_fingerprint="fp_b",
        last_success_at=completed,
    )
    db.query.return_value.filter.return_value.all.return_value = [row_a, row_b]

    with patch.object(TaskLastExecutionsRepository, "upsert_success_sync") as mock_upsert:
        count = TaskLastExecutionsRepository.promote_target_keys_batch_sync(
            db,
            program_id,
            [
                {
                    "asset_type": "subdomain",
                    "asset_id": asset_id,
                    "target_keys": ["sub.example.com"],
                }
            ],
        )

    assert count == 2
    assert mock_upsert.call_count == 2
    db.delete.assert_has_calls([call(row_a), call(row_b)])


def test_promote_target_keys_sync_no_matching_rows():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    count = TaskLastExecutionsRepository.promote_target_keys_sync(
        db,
        uuid.uuid4(),
        asset_type="subdomain",
        asset_id=uuid.uuid4(),
        target_keys=["missing.example"],
    )
    assert count == 0
    db.delete.assert_not_called()


def test_normalize_target_key_matches_canonical_keys_for_asset():
    raw = "https://test.example:443/"
    assert canonical_keys_for_asset("url", {"url": raw}) == [
        normalize_target_key(raw)
    ]
