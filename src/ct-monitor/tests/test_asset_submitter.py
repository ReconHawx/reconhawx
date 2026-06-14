"""CTAssetSubmitter: batching, Redis dedup, POST /assets payloads."""

import pytest

PROGRAM_ID = "11111111-1111-1111-1111-111111111111"


class _FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def setex(self, key, ttl, value):
        self._ops.append((key, ttl, value))

    def execute(self):
        for key, _ttl, value in self._ops:
            self._store[key] = value
        self._ops = []


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def pipeline(self):
        return _FakePipeline(self.store)


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    async def text(self):
        return "body"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    """Records POST calls; status configurable via class attribute."""

    status = 202
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        _FakeSession.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(_FakeSession.status)


@pytest.fixture
def fake_http(monkeypatch):
    import asset_submitter as mod

    _FakeSession.calls = []
    _FakeSession.status = 202
    monkeypatch.setattr(mod.aiohttp, "ClientSession", _FakeSession)
    return _FakeSession


def _submitter(redis_client=None, **kwargs):
    from asset_submitter import CTAssetSubmitter

    return CTAssetSubmitter(
        api_url="http://api:8000",
        api_key="secret",
        redis_client=redis_client,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_flush_posts_batched_subdomains(fake_http):
    sub = _submitter()
    await sub.add("b.example.com", "prog1", PROGRAM_ID)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()

    assert len(fake_http.calls) == 1
    call = fake_http.calls[0]
    assert call["url"] == "http://api:8000/assets"
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert call["json"] == {
        "program_id": PROGRAM_ID,
        "assets": {
            "subdomain": [{"name": "a.example.com"}, {"name": "b.example.com"}]
        },
    }
    assert sub.assets_submitted == 2
    assert sub.batches_posted == 1


@pytest.mark.asyncio
async def test_buffer_dedups_and_batch_max_forces_flush(fake_http):
    sub = _submitter(batch_max=2)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)  # set dedup, no flush yet
    assert fake_http.calls == []
    await sub.add("b.example.com", "prog1", PROGRAM_ID)  # hits batch_max → flush
    assert len(fake_http.calls) == 1
    names = [d["name"] for d in fake_http.calls[0]["json"]["assets"]["subdomain"]]
    assert names == ["a.example.com", "b.example.com"]


@pytest.mark.asyncio
async def test_redis_dedup_skips_recently_submitted(fake_http):
    redis = _FakeRedis()
    sub = _submitter(redis_client=redis)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    assert len(fake_http.calls) == 1
    assert redis.store[f"ct_monitor:asset_seen:{PROGRAM_ID}:a.example.com"] == "1"

    # Second sighting is deduped before buffering.
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    assert len(fake_http.calls) == 1
    assert sub.asset_dedup_hits == 1


@pytest.mark.asyncio
async def test_failed_post_does_not_mark_seen(fake_http):
    redis = _FakeRedis()
    sub = _submitter(redis_client=redis)
    fake_http.status = 500
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    assert sub.post_failures == 1
    assert sub.assets_submitted == 0
    assert redis.store == {}

    # Next sighting retries the POST.
    fake_http.status = 202
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    assert sub.assets_submitted == 1
    assert f"ct_monitor:asset_seen:{PROGRAM_ID}:a.example.com" in redis.store


@pytest.mark.asyncio
async def test_separate_programs_post_separately(fake_http):
    other_id = "22222222-2222-2222-2222-222222222222"
    sub = _submitter()
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.add("b.other.io", "prog2", other_id)
    await sub.flush_now()
    assert len(fake_http.calls) == 2
    by_program = {c["json"]["program_id"]: c["json"] for c in fake_http.calls}
    assert set(by_program) == {PROGRAM_ID, other_id}


@pytest.mark.asyncio
async def test_stop_flushes_pending(fake_http):
    sub = _submitter(flush_interval=3600)
    await sub.start()
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.stop()
    assert len(fake_http.calls) == 1


class _FakePublisher:
    calls = []

    async def publish_asset_discovered(self, program_name, program_id, subdomain):
        _FakePublisher.calls.append(
            {"program_name": program_name, "program_id": program_id, "subdomain": subdomain}
        )
        return True


class _FakeLogSubmitter:
    def __init__(self):
        self.logs = []

    def enqueue(self, log):
        self.logs.append(log)


@pytest.mark.asyncio
async def test_successful_post_publishes_nats_events(fake_http):
    pub = _FakePublisher()
    _FakePublisher.calls = []
    sub = _submitter(event_publisher=pub)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.add("b.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()

    assert len(_FakePublisher.calls) == 2
    assert {c["subdomain"] for c in _FakePublisher.calls} == {"a.example.com", "b.example.com"}
    assert sub.asset_events_published == 2


@pytest.mark.asyncio
async def test_failed_post_does_not_publish_events(fake_http):
    pub = _FakePublisher()
    _FakePublisher.calls = []
    sub = _submitter(event_publisher=pub)
    fake_http.status = 500
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    assert _FakePublisher.calls == []
    assert sub.asset_events_published == 0


@pytest.mark.asyncio
async def test_asset_submitter_emits_ct_monitor_logs(fake_http):
    log_submitter = _FakeLogSubmitter()
    sub = _submitter(log_submitter=log_submitter)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()

    assert [log["outcome"] for log in log_submitter.logs] == ["queued", "submitted"]
    assert all(log["event_type"] == "asset_submission" for log in log_submitter.logs)
    assert all(log["program_id"] == PROGRAM_ID for log in log_submitter.logs)


@pytest.mark.asyncio
async def test_asset_submitter_logs_dedup_skips(fake_http):
    redis = _FakeRedis()
    log_submitter = _FakeLogSubmitter()
    sub = _submitter(redis_client=redis, log_submitter=log_submitter)
    await sub.add("a.example.com", "prog1", PROGRAM_ID)
    await sub.flush_now()
    await sub.add("a.example.com", "prog1", PROGRAM_ID)

    assert "dedup_skipped" in [log["outcome"] for log in log_submitter.logs]
