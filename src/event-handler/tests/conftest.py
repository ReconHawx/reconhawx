"""Pytest configuration and fixtures for event-handler tests."""

import os
import sys

# Add event-handler app to path for imports
event_handler_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app_dir = os.path.join(event_handler_dir, "app")
if app_dir not in sys.path:
    sys.path.insert(0, event_handler_dir)
