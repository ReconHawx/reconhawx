"""Tests for last_execution_threshold parsing and coercion."""
import pytest

from last_execution_threshold import (
    LastExecutionThresholdError,
    coerce_stored_last_execution_threshold,
    last_execution_threshold_to_hours,
    normalize_recon_parameters_dict,
)


def test_hours_numeric():
    assert last_execution_threshold_to_hours(24) == 24
    assert last_execution_threshold_to_hours(1) == 1


def test_hours_string():
    assert last_execution_threshold_to_hours("24") == 24
    assert last_execution_threshold_to_hours("  24  ") == 24
    assert last_execution_threshold_to_hours("24h") == 24
    assert last_execution_threshold_to_hours("1H") == 1


def test_days_weeks():
    assert last_execution_threshold_to_hours("1d") == 24
    assert last_execution_threshold_to_hours("2d") == 48
    assert last_execution_threshold_to_hours("1w") == 168
    assert last_execution_threshold_to_hours("2W") == 336


def test_invalid():
    with pytest.raises(LastExecutionThresholdError):
        last_execution_threshold_to_hours("1m")
    with pytest.raises(LastExecutionThresholdError):
        last_execution_threshold_to_hours("1y")
    with pytest.raises(LastExecutionThresholdError):
        last_execution_threshold_to_hours(0)
    with pytest.raises(LastExecutionThresholdError):
        last_execution_threshold_to_hours(True)
    with pytest.raises(LastExecutionThresholdError):
        last_execution_threshold_to_hours(1.5)


def test_coerce_storage():
    assert coerce_stored_last_execution_threshold(24) == 24
    assert coerce_stored_last_execution_threshold("24") == 24
    assert coerce_stored_last_execution_threshold("24h") == 24
    assert coerce_stored_last_execution_threshold("1d") == "1d"
    assert coerce_stored_last_execution_threshold("2W") == "2w"


def test_normalize_dict():
    o = normalize_recon_parameters_dict({"last_execution_threshold": "1w", "chunk_size": 5})
    assert o["last_execution_threshold"] == "1w"
    assert o["chunk_size"] == 5
    assert normalize_recon_parameters_dict({"chunk_size": 5}) == {"chunk_size": 5}
