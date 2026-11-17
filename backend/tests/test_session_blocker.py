from sqlalchemy import select

from app.db import session_blockers
from tests.test_engine import make_engine
from tests.test_mode_a import make, settle


def saved_blocker(engine):
    with engine.db.engine.connect() as conn:
        return conn.execute(select(session_blockers.c.data).where(session_blockers.c.session_id == engine.session_id)).scalar_one_or_none()


async def test_mode_b_writes_session_blocker(tmp_path):
    engine, _ = make_engine(tmp_path)
    engine.start()
    data = saved_blocker(engine)
    assert data["id"] == engine.blocker.id and data["locked"] is True and len(data["topics"]) == len(engine.blocker.topics)
    await engine.stop()


async def test_mode_a_writes_session_blocker_and_snapshot_has_rundown(tmp_path):
    engine, _ = make(tmp_path)
    engine.start()
    await settle(engine)
    assert saved_blocker(engine)["id"] == engine.blocker.id
    rundown = engine.snapshot()["rundown"]
    assert rundown["opening"]["hook"] == engine.blocker.opening.hook
    assert [t["judul"] for t in rundown["topics"]] == [t.judul for t in engine.blocker.topics]
    assert rundown["topics"][0]["poin"][0]["id"] == "t1p1" and rundown["topics"][0]["transisi"]
    assert rundown["closing"]["ajakan"] == engine.blocker.closing.ajakan
    await engine.stop()
