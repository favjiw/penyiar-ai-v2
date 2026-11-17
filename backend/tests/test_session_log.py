import pytest

from app.schemas import ShowrunnerDecision
from app.session_log import SessionLogger, list_sessions
from tests.dbutil import make_db


def test_events_are_typed_and_appended(tmp_path):
    log = SessionLogger("show_test", make_db(tmp_path))
    log.event("session_start", {"mode": "B"}, blocker={"id": "blk_x"})
    log.event("showrunner", ShowrunnerDecision(turn=3, topic_id="t1", decision="steer"))
    lines = log.events()
    assert [l["type"] for l in lines] == ["session_start", "showrunner"]
    assert lines[0]["blocker"]["id"] == "blk_x" and lines[0]["session_id"] == "show_test"
    assert lines[1]["decision"] == "steer" and "ts" in lines[1]


def test_unknown_event_type_rejected(tmp_path):
    with pytest.raises(ValueError):
        SessionLogger("s", make_db(tmp_path)).event("lagu_diputar")


def test_logs_are_per_session_and_listed_newest_first(tmp_path):
    db = make_db(tmp_path)
    SessionLogger("show_20261101_a", db).event("session_start", mode="B")
    SessionLogger("show_20261102_b", db).event("session_start", mode="A")
    SessionLogger("show_20261102_b", db).event("session_end", reason="stopped")
    assert [s["session_id"] for s in list_sessions(db)] == ["show_20261102_b", "show_20261101_a"]
    assert [s["events"] for s in list_sessions(db)] == [2, 1]
    assert [e["type"] for e in SessionLogger("show_20261102_b", db).events()] == ["session_start", "session_end"]
    assert SessionLogger("tidak_ada", db).events() == []
