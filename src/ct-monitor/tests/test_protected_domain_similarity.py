"""Tests for duplicated API-aligned protected-domain similarity (ct-monitor)."""


def test_dfs_fragment_regression_low_vs_typical_brand_list():
    from protected_domain_similarity import best_match_among_protected

    typo = "35thanniversaryidp-dcs.com"
    protected = [
        "enterprise.com",
        "dcs.ca",
        "disney.com",
    ]
    best_s, _ = best_match_among_protected(typo, protected)
    assert best_s < 0.8


def test_examp1e_regression():
    from protected_domain_similarity import best_similarity_typo_to_protected

    assert best_similarity_typo_to_protected("examp1e.com", "example.com") >= 0.85


def test_collapsed_dot_split_cap():
    from protected_domain_similarity import best_similarity_typo_to_protected

    typo = "dcs-entre.prise.com"
    protected = "dcs-entreprise.com"
    assert best_similarity_typo_to_protected(typo, protected) == 0.99


def test_typo_suffix_hostnames_multi_label():
    from protected_domain_similarity import _typo_suffix_hostnames

    labels = _typo_suffix_hostnames("a.b.c.d.com")
    assert "a.b.c.d.com" in labels
    assert "d.com" in labels
    assert all(len(s.split(".")) >= 2 for s in labels)
