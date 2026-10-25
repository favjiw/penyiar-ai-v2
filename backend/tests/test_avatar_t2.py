from app.avatar.t2_client import RenderResult, T2Client
from app.config import Settings
from tests.test_mode_a import make, settle


class FakeT2:
    enabled = True
    last_error = ""

    def __init__(self):
        self.calls = []

    async def render(self, persona, audio):
        self.calls.append((persona, audio.name))
        out = audio.with_suffix(".mp4")
        out.write_bytes(b"mp4")
        return RenderResult(out, render_ms=250, rtf=0.5)


async def test_mode_a_parts_carry_lipsync_video(tmp_path):
    engine, events = make(tmp_path)
    engine.t2 = FakeT2()
    engine.start()
    await settle(engine)
    await engine.human_turn("Salsa, lo tim teh atau kopi?")
    await settle(engine)
    turn = next(d for t, d in events if t == "turn")
    assert turn["video_url"] == turn["audio_url"].rsplit(".", 1)[0] + ".mp4"
    parts = [d for t, d in events if t == "audio_part"]
    assert all(p["video_url"] for p in parts)
    assert len(engine.t2.calls) == turn["parts"]


def test_t2_disabled_without_worker_url():
    assert not T2Client(Settings(AVATAR_TIER="t2", _env_file=None)).enabled
    assert not T2Client(Settings(AVATAR_TIER="t1", AVATAR_WORKER_URL="http://x", _env_file=None)).enabled


async def test_worker_down_falls_back_to_t1(tmp_path):
    client = T2Client(Settings(AVATAR_TIER="t2", AVATAR_WORKER_URL="http://127.0.0.1:9", _env_file=None))
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    assert await client.render("raka", audio) is None
    assert client.last_error.startswith("health")
