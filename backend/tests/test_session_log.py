import pytest

from app.schemas import ShowrunnerDecision
from app.session_log import SessionLogger, read_log


def test_events_are_typed_and_appended(tmp_path):
    log = SessionLogger("show_test", tmp_path)
    log.event("session_start", {"mode": "B"}, blocker={"id": "blk_x"})
    log.event("showrunner", ShowrunnerDecision(turn=3, topic_id="t1", decision="steer"))
    lines = list(read_log(log.path))
    assert [l["type"] for l in lines] == ["session_start", "showrunner"]
    assert lines[0]["blocker"]["id"] == "blk_x" and lines[0]["session_id"] == "show_test"
    assert lines[1]["decision"] == "steer" and "ts" in lines[1]


def test_unknown_event_type_rejected(tmp_path):
    with pytest.raises(ValueError):
        SessionLogger("s", tmp_path).event("lagu_diputar")
