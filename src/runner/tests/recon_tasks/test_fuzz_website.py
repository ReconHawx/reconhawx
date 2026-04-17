"""Tests for ``recon_tasks.fuzz_website.FuzzWebsite`` (dual-purpose task)."""

from __future__ import annotations

import base64

import pytest

from recon_tasks.base import AssetType, FindingType
from recon_tasks.fuzz_website import FuzzWebsite


DEFAULT_WL = "/workspace/files/webcontent_test.txt"
UUID_WL = "deadbeef-dead-beef-dead-beefdeadbeef"


@pytest.fixture
def task() -> FuzzWebsite:
    return FuzzWebsite()


def test_get_timestamp_hash_uses_original_wordlist(task: FuzzWebsite) -> None:
    digest = task.get_timestamp_hash("https://example.com", params={"wordlist": UUID_WL})
    decoded = base64.b64decode(digest).decode()
    assert UUID_WL in decoded
    assert "fuzz_website" in decoded


def test_get_command_default_wordlist_when_param_missing(task: FuzzWebsite) -> None:
    cmds = task.get_command(["https://example.com"], params={})
    assert len(cmds) == 1
    assert DEFAULT_WL in cmds[0]


def test_get_command_default_wordlist_when_params_none(task: FuzzWebsite) -> None:
    cmds = task.get_command(["https://example.com"])
    assert len(cmds) == 1
    assert DEFAULT_WL in cmds[0]


def test_get_command_uuid_wordlist_converted_to_api_url(
    task: FuzzWebsite, monkeypatch
) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    cmds = task.get_command(["https://example.com"], params={"wordlist": UUID_WL})
    assert f"http://api:8000/wordlists/{UUID_WL}/download" in cmds[0]


def test_get_command_absolute_path_wordlist_passes_through(task: FuzzWebsite) -> None:
    cmds = task.get_command(
        ["https://example.com"], params={"wordlist": "/custom/list.txt"}
    )
    assert "/custom/list.txt" in cmds[0]


def test_get_command_http_url_wordlist_passes_through(task: FuzzWebsite) -> None:
    cmds = task.get_command(
        ["https://example.com"], params={"wordlist": "https://lists.test/w.txt"}
    )
    assert "https://lists.test/w.txt" in cmds[0]


def test_get_command_invalid_wordlist_falls_back_to_default(task: FuzzWebsite) -> None:
    cmds = task.get_command(
        ["https://example.com"], params={"wordlist": "relative-name.txt"}
    )
    assert DEFAULT_WL in cmds[0]


def test_get_command_strips_trailing_slash_and_sets_host_header(task: FuzzWebsite) -> None:
    cmds = task.get_command(["https://example.com/"], params={})
    # URL used in -u must not end with //FUZZ.
    assert "-u https://example.com:443/FUZZ" in cmds[0]
    assert "-H 'Host: example.com'" in cmds[0]


def test_get_command_empty_input_returns_empty(task: FuzzWebsite) -> None:
    assert task.get_command([], params={}) == ""
    assert task.get_command(["not a url"], params={}) == ""


def test_get_command_one_command_per_url(task: FuzzWebsite) -> None:
    cmds = task.get_command(
        ["https://a.test", "https://b.test"], params={}
    )
    assert len(cmds) == 2
    assert any("a.test" in c for c in cmds)
    assert any("b.test" in c for c in cmds)


def test_parse_output_builds_url_assets(task: FuzzWebsite, load_fixture) -> None:
    raw = load_fixture("fuzz_website/ffuf_success.json")
    result = task.parse_output(raw)

    urls = result[AssetType.URL]
    by_path = {u.path: u for u in urls}
    assert set(by_path) == {"/admin", "/login", "/moved"}

    assert by_path["/admin"].http_status_code == 200
    assert by_path["/login"].http_status_code == 401
    assert by_path["/moved"].http_status_code == 301
    assert by_path["/moved"].final_url == "https://example.com/new"
    # Rows without redirect_location fall back to the request URL.
    assert by_path["/admin"].final_url == "https://example.com/admin"


def test_parse_output_empty_returns_empty(task: FuzzWebsite) -> None:
    assert task.parse_output("") == {AssetType.URL: []}


def test_parse_output_skips_malformed_lines(task: FuzzWebsite) -> None:
    raw = '{"url": "https://ok.test/a", "status": 200}\n{not json}\n{"url": "https://ok.test/b", "status": 204}'
    result = task.parse_output(raw)
    paths = {u.path for u in result[AssetType.URL]}
    assert paths == {"/a", "/b"}


def test_transform_to_findings_infers_typo_domain_from_hostname(
    task: FuzzWebsite, load_fixture
) -> None:
    raw = load_fixture("fuzz_website/ffuf_success.json")
    assets = task.parse_output(raw)

    findings_map = task.transform_to_findings(assets, context={})
    findings = findings_map[FindingType.TYPOSQUAT_URL]
    assert len(findings) == 3
    # typo_domain is inferred from the first URL's hostname.
    assert all(f.typo_domain == "example.com" for f in findings)


def test_transform_to_findings_uses_explicit_context(
    task: FuzzWebsite, load_fixture
) -> None:
    raw = load_fixture("fuzz_website/ffuf_success.json")
    assets = task.parse_output(raw)

    findings_map = task.transform_to_findings(
        assets,
        context={
            "typo_domain": "attacker.example.com",
            "fuzzer_wordlist": "wl-id",
            "program_name": "Prog",
            "risk_factors": {"total_score": 80},
        },
    )
    findings = findings_map[FindingType.TYPOSQUAT_URL]
    assert all(f.typo_domain == "attacker.example.com" for f in findings)
    assert all(f.program_name == "Prog" for f in findings)
    assert all(f.fuzzer_wordlist == "wl-id" for f in findings)
    # Risk factor wiring: login path + auth status + domain score => strictly > 0.
    assert all(f.risk_score > 0 for f in findings)


def test_transform_to_findings_empty_when_no_urls(task: FuzzWebsite) -> None:
    assert task.transform_to_findings({AssetType.URL: []}, context={}) == {}


def test_calculate_url_risk_score_monotonicity(task: FuzzWebsite) -> None:
    from models.assets import Url

    neutral = Url(url="https://x.test/", hostname="x.test", http_status_code=404, path="/")
    active = Url(url="https://x.test/", hostname="x.test", http_status_code=200, path="/")
    login = Url(
        url="https://x.test/login",
        hostname="x.test",
        http_status_code=401,
        path="/login",
        content_type="text/html",
    )

    assert task._calculate_url_risk_score(neutral, {}) < task._calculate_url_risk_score(
        active, {}
    )
    assert task._calculate_url_risk_score(active, {}) < task._calculate_url_risk_score(
        login, {}
    )
    # Score is capped at 100.
    assert task._calculate_url_risk_score(login, {"total_score": 1000}) <= 100
