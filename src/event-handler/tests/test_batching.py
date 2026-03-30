"""Unit tests for batching.py (re-exports)."""

import pytest

from app.batching import BatchAggregator, BatchManager, SimpleBatchManager
from app.event_handlers import SimpleBatchManager as EventHandlersBatchManager


class TestBatchingReexports:
    """Tests for batching module re-exports."""

    def test_batch_aggregator_is_simple_batch_manager(self):
        assert BatchAggregator is EventHandlersBatchManager

    def test_batch_manager_alias(self):
        assert BatchManager is SimpleBatchManager
        assert BatchManager is BatchAggregator
