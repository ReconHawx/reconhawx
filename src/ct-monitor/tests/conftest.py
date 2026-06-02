"""Pytest setup for ct-monitor: isolate imports from API/runner `models`/`config` name clashes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CT_APP = Path(__file__).resolve().parent.parent / "app"
_CT_APP_STR = str(_CT_APP)

# Top-level module names shared with src/api/app (flat imports in ct-monitor).
_SHADOW_MODULES = (
    "models",
    "config",
    "main",
    "alert_publisher",
    "certstream_consumer",
    "variation_generator",
    "program_ct_settings",
    "protected_domain_similarity",
    "certstream_k8s",
)


def _unload_ct_monitor_modules() -> None:
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None)
        if path and path.startswith(_CT_APP_STR):
            del sys.modules[name]


@pytest.fixture(autouse=True)
def _ct_monitor_path_and_cleanup():
    """Prepend ct-monitor app, drop cached shadow modules, restore after each test."""
    saved = {k: sys.modules.pop(k, None) for k in _SHADOW_MODULES}
    before_path = sys.path.copy()
    sys.path.insert(0, _CT_APP_STR)
    yield
    sys.path[:] = before_path
    _unload_ct_monitor_modules()
    for key, mod in saved.items():
        if mod is not None:
            sys.modules[key] = mod
