import pytest


class _FakeResponse:
    status = 500

    async def text(self):
        return "failed"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse()


@pytest.mark.asyncio
async def test_ct_log_submitter_counts_failed_posts(monkeypatch):
    import ct_log_submitter as mod
    from ct_log_submitter import CTLogSubmitter

    _FakeSession.calls = []
    monkeypatch.setattr(mod.aiohttp, "ClientSession", _FakeSession)

    submitter = CTLogSubmitter("http://api:8000", "secret", batch_max=10)
    submitter.enqueue(
        {
            "program_id": "11111111-1111-1111-1111-111111111111",
            "event_type": "typosquat_alert",
            "outcome": "published",
            "domain": "examp1e.com",
            "details": {},
        }
    )
    await submitter.flush_now()

    assert submitter.failures == 1
    assert submitter.submitted == 0
    assert _FakeSession.calls[0]["url"] == "http://api:8000/internal/ct-monitor/logs"
    assert _FakeSession.calls[0]["headers"]["Authorization"] == "Bearer secret"
