"""Tests for task_params_fingerprint."""

from utils.task_params_fingerprint import params_fingerprint


def test_same_fingerprint_when_only_timeout_differs() -> None:
    base = {"template": {"official": ["cves"]}, "timeout": 900, "chunk_size": 2}
    other = {"template": {"official": ["cves"]}, "timeout": 1200, "chunk_size": 5}
    assert params_fingerprint("nuclei_scan", base) == params_fingerprint("nuclei_scan", other)


def test_different_fingerprint_when_template_differs() -> None:
    a = {"template": {"official": ["a"]}, "timeout": 900}
    b = {"template": {"official": ["b"]}, "timeout": 900}
    assert params_fingerprint("nuclei_scan", a) != params_fingerprint("nuclei_scan", b)


def test_port_scan_ignores_all_params() -> None:
    assert params_fingerprint("port_scan", {"timeout": 1}) == params_fingerprint(
        "port_scan", {"timeout": 999, "chunk_size": 50}
    )


def test_fuzz_website_wordlist_matters() -> None:
    a = {"wordlist": "wl-a", "timeout": 300}
    b = {"wordlist": "wl-b", "timeout": 300}
    assert params_fingerprint("fuzz_website", a) != params_fingerprint("fuzz_website", b)


def test_fuzz_website_timeout_ignored() -> None:
    a = {"wordlist": "wl-a", "timeout": 300}
    b = {"wordlist": "wl-a", "timeout": 600}
    assert params_fingerprint("fuzz_website", a) == params_fingerprint("fuzz_website", b)
