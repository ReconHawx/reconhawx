"""Tests for pure helpers in ``task_components``."""

from __future__ import annotations

from datetime import datetime

import pytest

from models.workflow import AssetStore
from task_components import (
    AssetProcessor,
    MemoryOptimizationConfig,
    ProgressiveStreamingConfig,
    StreamingAssetProcessor,
    TaskResult,
)


class _FakeDomain:
    def __init__(self, name: str, ip=None, cname=None, is_wildcard=None):
        self.name = name
        self.ip = ip
        self.cname = cname
        self.is_wildcard = is_wildcard


class _FakeIp:
    def __init__(self, ip: str, ptr=None):
        self.ip = ip
        self.ptr = ptr


class _FakeUrl:
    def __init__(self, url: str, techs=None, favicon_hash=None, favicon_url=None):
        self.url = url
        self.techs = techs or []
        self.favicon_hash = favicon_hash
        self.favicon_url = favicon_url


def test_memory_config_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ASSET_BATCH_SIZE", "250")
    cfg = MemoryOptimizationConfig.from_environment()
    assert cfg.asset_batch_size == 250


@pytest.mark.parametrize(
    "count,expected",
    [
        (100, 30.0),
        (1500, 40.0),
        (5000, 80.0),
        (100000, 180),
    ],
)
def test_progressive_calculate_timeout(count: int, expected: float) -> None:
    cfg = ProgressiveStreamingConfig()
    assert cfg.calculate_timeout_for_assets(count) == expected


def test_streaming_asset_processor_merge_efficient_dedupes() -> None:
    sap = StreamingAssetProcessor()
    existing: dict = {"subdomain": [_FakeDomain("a.example.com")]}
    new = {"subdomain": [_FakeDomain("a.example.com"), _FakeDomain("b.example.com")]}
    merged = sap._merge_assets_efficient(existing, new)
    names = {d.name for d in merged["subdomain"]}
    assert names == {"a.example.com", "b.example.com"}


def test_streaming_asset_processor_estimate_memory_usage() -> None:
    sap = StreamingAssetProcessor()
    assets = {"subdomain": [1, 2, 3], "ip": [1]}
    assert sap._estimate_memory_usage(assets) == 4 * 500


def test_asset_processor_merge_domain_dedup_and_merge_fields() -> None:
    ap = AssetProcessor(asset_store=AssetStore(), enable_streaming=False)
    existing = [_FakeDomain("a.com", ip=["1.1.1.1"])]
    new = [_FakeDomain("a.com", ip=["2.2.2.2"], cname="cname.example"), _FakeDomain("b.com")]
    merged = ap._merge_domain_assets(existing, new)
    names = sorted(d.name for d in merged)
    assert names == ["a.com", "b.com"]
    a = next(d for d in merged if d.name == "a.com")
    assert set(a.ip) == {"1.1.1.1", "2.2.2.2"}
    assert a.cname == "cname.example"


def test_asset_processor_merge_ip_dedup() -> None:
    ap = AssetProcessor(asset_store=AssetStore(), enable_streaming=False)
    existing = [_FakeIp("1.1.1.1", ptr=["a.com"])]
    new = [_FakeIp("1.1.1.1", ptr=["b.com"]), _FakeIp("2.2.2.2")]
    merged = ap._merge_ip_assets(existing, new)
    ips = sorted(x.ip for x in merged)
    assert ips == ["1.1.1.1", "2.2.2.2"]
    first = next(x for x in merged if x.ip == "1.1.1.1")
    assert set(first.ptr) == {"a.com", "b.com"}


def test_asset_processor_merge_url_dedup_and_techs() -> None:
    ap = AssetProcessor(asset_store=AssetStore(), enable_streaming=False)
    existing = [_FakeUrl("https://a.com", techs=["react"])]
    new = [_FakeUrl("https://a.com", techs=["node"], favicon_hash="h")]
    merged = ap._merge_url_assets(existing, new)
    assert len(merged) == 1
    assert set(merged[0].techs) == {"react", "node"}
    assert merged[0].favicon_hash == "h"


def test_merge_list_field_accepts_strings_and_lists() -> None:
    ap = AssetProcessor(asset_store=AssetStore(), enable_streaming=False)
    assert set(ap._merge_list_field(None, "a")) == {"a"}
    assert set(ap._merge_list_field("a", ["b", "a"])) == {"a", "b"}


def test_recursively_serialize_datetime() -> None:
    ap = AssetProcessor(asset_store=AssetStore(), enable_streaming=False)
    payload = {"a": datetime(2024, 1, 2), "list": [datetime(2024, 1, 3), "x"]}
    out = ap._recursively_serialize_datetime(payload)
    assert out["a"] == "2024-01-02T00:00:00"
    assert out["list"][0] == "2024-01-03T00:00:00"
    assert out["list"][1] == "x"


def test_asset_store_add_and_merge() -> None:
    store = AssetStore()
    store.add_step_assets("step1", "subdomain", [_FakeDomain("a.com")])
    store.add_step_assets("step1", "subdomain", [_FakeDomain("b.com")])
    assets = store.get_step_assets("step1", "subdomain")
    assert [d.name for d in assets] == ["a.com", "b.com"]


def test_store_assets_skips_non_assettype_keys() -> None:
    store = AssetStore()
    ap = AssetProcessor(asset_store=store, enable_streaming=False)
    ap.store_assets("step1", {"_typosquat_urls": [1, 2, 3]})
    assert store.get_step_assets("step1") == {}


def test_task_result_dataclass_defaults() -> None:
    tr = TaskResult(
        task_id="t",
        success=True,
        output="out",
        parsed_assets={"subdomain": []},
        execution_time=1.5,
    )
    assert tr.success is True
    assert tr.parsed_assets == {"subdomain": []}
