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


def test_examp1e_co_uk_apex_via_tldextract():
    from protected_domain_similarity import best_similarity_typo_to_protected

    assert best_similarity_typo_to_protected("examp1e.co.uk", "example.co.uk") >= 0.85


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


def test_similarity_impossible_by_length_unrelated():
    from protected_domain_similarity import similarity_impossible_by_length

    assert similarity_impossible_by_length(
        "completely-unrelated-label.net",
        [len("examplecom")],
        0.85,
    ) is True


def test_similarity_impossible_by_length_does_not_skip_examp1e():
    from protected_domain_similarity import (
        _collapse_hostname_alphanumeric,
        similarity_impossible_by_length,
    )

    protected_len = len(_collapse_hostname_alphanumeric("example.com"))
    assert similarity_impossible_by_length(
        "examp1e.com",
        [protected_len],
        0.85,
    ) is False


def test_similarity_impossible_disabled_at_threshold_one():
    from protected_domain_similarity import similarity_impossible_by_length

    assert similarity_impossible_by_length("x.com", [3], 1.0) is False


def test_rapidfuzz_similarity_parity_with_pure_python():
    from protected_domain_similarity import (
        _levenshtein_distance_py,
        _levenshtein_similarity,
    )

    pairs = [
        ("example.com", "examp1e.com"),
        ("examplecom", "exarnplecom"),
        ("", ""),
        ("a", ""),
        ("kitten", "sitting"),
        ("domain", "domian"),
        ("short", "averylongdomainnamestring"),
        ("dcsentreprisecom", "dcsentreprisecom"),
    ]
    for s1, s2 in pairs:
        max_len = max(len(s1), len(s2))
        expected = (
            1.0 if max_len == 0 else 1.0 - _levenshtein_distance_py(s1, s2) / max_len
        )
        assert abs(_levenshtein_similarity(s1, s2) - expected) < 1e-9, (s1, s2)


def test_best_match_among_prepared_matches_unprepared_path():
    from protected_domain_similarity import (
        best_match_among_prepared,
        best_match_among_protected,
        prepare_protected,
        prepare_typo,
    )

    protected = ["example.com", "dcs-entreprise.com", "enterprise.com"]
    prepared = [prepare_protected(p) for p in protected]
    typos = [
        "examp1e.com",
        "dcs-entre.prise.com",
        "www.exarnple.co.uk",
        "unrelated-zzz.net",
        "login.examp1e.com",
    ]
    for typo in typos:
        s1, p1 = best_match_among_protected(typo, protected)
        s2, p2 = best_match_among_prepared(prepare_typo(typo), prepared)
        assert abs(s1 - s2) < 1e-9, typo
        assert p1 == p2, typo


def test_best_match_among_prepared_score_cutoff():
    from protected_domain_similarity import (
        best_match_among_prepared,
        best_match_among_protected,
        prepare_protected,
        prepare_typo,
    )

    prepared = [prepare_protected("example.com")]

    # Above cutoff: same score as the uncapped path.
    s_full, _ = best_match_among_protected("examp1e.com", ["example.com"])
    s_cut, p_cut = best_match_among_prepared(
        prepare_typo("examp1e.com"), prepared, score_cutoff=0.85
    )
    assert abs(s_cut - s_full) < 1e-9
    assert p_cut == "example.com"
    assert s_cut >= 0.85

    # Below cutoff: rapidfuzz returns 0.0 — never selected by threshold callers.
    s_low, p_low = best_match_among_prepared(
        prepare_typo("totally-unrelated-zzz.net"), prepared, score_cutoff=0.85
    )
    assert s_low == 0.0
    assert p_low is None


def test_similarity_impossible_prepared_matches_unprepared():
    from protected_domain_similarity import (
        prepare_typo,
        similarity_impossible_by_length,
        similarity_impossible_by_length_prepared,
    )

    cases = [
        ("completely-unrelated-label.net", [10], 0.85),
        ("examp1e.com", [10], 0.85),
        ("x.com", [3], 1.0),
        ("a.b.c.example.com", [10, 25], 0.9),
    ]
    for typo, lengths, thr in cases:
        assert similarity_impossible_by_length_prepared(
            prepare_typo(typo), lengths, thr
        ) == similarity_impossible_by_length(typo, lengths, thr), (typo, lengths, thr)
