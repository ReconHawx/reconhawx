#!/usr/bin/env python3
"""
Simplified batching system using the new simple components

This replaces the complex batching.py with a lightweight compatibility layer.
"""

# Re-export the simplified batch manager
from .event_handlers import SimpleBatchManager as BatchAggregator

# Legacy compatibility aliases
BatchManager = SimpleBatchManager = BatchAggregator