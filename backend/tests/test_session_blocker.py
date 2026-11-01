import json

from app.config import Settings
from tests.test_engine import make_engine
from tests.test_mode_a import make, settle


def test_sessions_path_defaults_next_to_log_dir(tmp_path):
    assert Settings(LOG_DIR=str(tmp_path / "logs"), _env_file=None).sessions_path == tmp_path / "sessions"
    assert Settings(SESSIONS_DIR=str(tmp_path / "x"), _env_file=None).sessions_path == tmp_path / "x"


async def test_mode_b_writes_session_blocker(tmp_path):
    engine, _ = make_engine(tmp_path)
    engine.start()
    saved = tmp_path / "sessions" / engine.session_id / "blocker.json"
    assert saved.exists()
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["id"] == engine.blocker.id and data["locked"] is True and len(data["topics"]) == len(engine.blocker.topics)
    await engine.stop()


async def test_mode_a_writes_session_blocker_and_snapshot_has_rundown(tmp_path):
    engine, _ = make(tmp_path)
    engine.start()
    await settle(engine)
    assert (tmp_path / "sessions" / engine.session_id / "blocker.json").exists()
    rundown = engine.snapshot()["rundown"]
    assert rundown["opening"]["hook"] == engine.blocker.opening.hook
    assert [t["judul"] for t in rundown["topics"]] == [t.judul for t in engine.blocker.topics]
    assert rundown["topics"][0]["poin"][0]["id"] == "t1p1" and rundown["topics"][0]["transisi"]
    assert rundown["closing"]["ajakan"] == engine.blocker.closing.ajakan
    await engine.stop()
