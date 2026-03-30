"""Tests for per-program CT settings parsing."""

import sys
from pathlib import Path

# app/ is the Python package root for ct-monitor
_APP = Path(__file__).resolve().parent.parent / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

import program_ct_settings  # noqa: E402


def test_default_tld_set_non_empty():
    assert "com" in program_ct_settings.default_tld_set()


def test_program_custom_tld_and_similarity():
    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "io,app", "similarity_threshold": 0.82}}
    )
    assert tlds == {"io", "app"}
    assert abs(sim - 0.82) < 1e-9


def test_program_empty_uses_defaults():
    tlds, sim = program_ct_settings.program_tlds_and_similarity(
        {"ct_monitor_program_settings": {"tld_filter": "", "similarity_threshold": None}}
    )
    assert tlds == program_ct_settings.default_tld_set()
    assert sim == program_ct_settings.DEFAULT_SIMILARITY_THRESHOLD
