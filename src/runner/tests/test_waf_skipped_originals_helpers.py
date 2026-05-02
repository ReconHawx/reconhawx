"""Unit tests for WAF skipped-originals cap helpers (runner ``waf_reputation`` isolated import)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_WR_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "waf_reputation.py"
_spec = importlib.util.spec_from_file_location("runner_waf_reputation_isolated", _WR_PATH)
assert _spec and _spec.loader
_wr_mod = importlib.util.module_from_spec(_spec)
sys.modules["runner_waf_reputation_isolated"] = _wr_mod
_spec.loader.exec_module(_wr_mod)
waf_truncated_skip_original_strings = _wr_mod.waf_truncated_skip_original_strings


def test_truncated_originals_no_truncation() -> None:
    full = ["https://a.com/x", "https://b.com/y"]
    capped, total, truncated = waf_truncated_skip_original_strings(full)
    assert total == 2
    assert capped == full
    assert not truncated


def test_truncated_originals_truncates(monkeypatch) -> None:
    monkeypatch.setenv("WAF_MAX_SKIPPED_ORIGINALS", "2")
    capped, total, truncated = waf_truncated_skip_original_strings(["a", "b", "c"])
    assert total == 3
    assert capped == ["a", "b"]
    assert truncated
