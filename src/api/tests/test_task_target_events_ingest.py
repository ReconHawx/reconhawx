"""Unit tests for task target resolution helpers (ingest path)."""

from repository.task_history_repo import (
    collect_input_strings,
    hostnames_referenced_by_url_strings,
    url_match_variants,
)


def test_collect_input_strings_from_list():
    assert collect_input_strings(["a.com", "b.com"]) == ["a.com", "b.com"]


def test_collect_input_strings_from_dict_name():
    assert collect_input_strings({"name": "host.example"}) == ["host.example"]


def test_collect_input_strings_nested():
    assert collect_input_strings([{"url": "https://x.test:443"}]) == ["https://x.test:443"]


def test_url_match_variants_https_root():
    v = url_match_variants("https://WWW.Example.COM")
    assert "https://www.example.com:443/" in v
    assert "https://www.example.com:443" in v


def test_url_match_variants_includes_lowered_original():
    v = url_match_variants("https://a.example:8443/path")
    assert any("8443" in x for x in v)


def test_collect_url_dict_omits_hostname():
    """Runner-serialized Url dicts must not also emit hostname as a separate target."""
    inp = {
        "url": "https://dummysite.h3x.it:443/",
        "hostname": "dummysite.h3x.it",
    }
    assert collect_input_strings(inp) == ["https://dummysite.h3x.it:443/"]


def test_collect_url_dict_includes_distinct_final_url():
    inp = {
        "url": "https://a.example:443/",
        "final_url": "https://b.example:443/",
        "hostname": "a.example",
    }
    out = collect_input_strings(inp)
    assert "https://a.example:443/" in out
    assert "https://b.example:443/" in out
    assert "a.example" not in out
    assert "b.example" not in out


def test_hostnames_referenced_by_url_strings():
    h = hostnames_referenced_by_url_strings(
        ["https://a.example:443", "b.example", "not a url"]
    )
    assert "a.example" in h
    assert "b.example" not in h
