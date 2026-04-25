"""Add ``src/worker/app`` to path so tests can import ``command_wrapper`` etc."""

from __future__ import annotations

import os
import sys

_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
