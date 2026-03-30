"""Tests for duplicated API-aligned protected-domain similarity (ct-monitor)."""

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from protected_domain_similarity import (  # noqa: E402
    best_match_among_protected,
    best_similarity_typo_to_protected,
    _typo_suffix_hostnames,
)


def test_dfs_fragment_regression_low_vs_typical_brand_list():
    """Long unrelated label containing '-dcs' should stay below a strict threshold."""
    typo = "35thanniversaryidp-dcs.com"
    protected = [
        "enterprise.com",
        "dcs.ca",
        "disney.com",
    ]
    best_s, _ = best_match_among_protected(typo, protected)
    assert best_s < 0.8


def test_examp1e_regression():
    assert best_similarity_typo_to_protected("examp1e.com", "example.com") >= 0.85


def test_collapsed_dot_split_cap():
    typo = "dcs-entre.prise.com"
    protected = "dcs-entreprise.com"
    assert best_similarity_typo_to_protected(typo, protected) == 0.99


def test_typo_suffix_hostnames_multi_label():
    labels = _typo_suffix_hostnames("a.b.c.d.com")
    assert "a.b.c.d.com" in labels
    assert "d.com" in labels
    assert all(len(s.split(".")) >= 2 for s in labels)
