"""Sisa kredit ElevenLabs: tidak diketahui ≠ 0 ≠ penuh (PRD v2.7 §6.4)."""

import httpx
import pytest

from app.tts import credits


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, 0

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.response


@pytest.fixture(autouse=True)
def clear_cache():
    credits._cache.clear()


async def run(monkeypatch, fake, **kw):
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return await credits.elevenlabs_credits_left("key", **kw)


async def test_reads_remaining_and_caches(monkeypatch):
    fake = FakeClient(httpx.Response(200, json={"character_count": 1000, "character_limit": 5000}))
    left, note = await run(monkeypatch, fake)
    assert left == 4000 and "4000" in note
    await run(monkeypatch, fake)
    assert fake.calls == 1  # disimpan 60 dtk
    await run(monkeypatch, fake, fresh=True)
    assert fake.calls == 2  # Mulai melewati simpanan


@pytest.mark.parametrize(
    "fake",
    [
        FakeClient(httpx.Response(401, json={"detail": "missing_permissions"})),
        FakeClient(httpx.Response(200, json={"tier": "free"})),  # medan hilang
        FakeClient(exc=httpx.ConnectTimeout("lambat")),
    ],
)
async def test_unknown_is_none_never_zero(monkeypatch, fake):
    left, note = await run(monkeypatch, fake)
    assert left is None and note


async def test_no_key_is_unknown():
    assert (await credits.elevenlabs_credits_left(""))[0] is None
