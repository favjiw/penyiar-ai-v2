import asyncio

import pytest

from app.config import Settings
from app.data.personas import load_personas
from app.llm import MockLLMClient
from app.schemas import ShowState
from app.session_log import read_log
from app.show.engine import ShowEngine
from app.tts import FailoverTTS, MockTTSProvider
from tests.test_persona import make_blocker


def make_engine(tmp_path, time_scale=0.0, **overrides):
    settings = Settings(
        LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"), _env_file=None, **overrides
    )
    events = []

    async def emit(type_, data):
        events.append((type_, data))

    engine = ShowEngine(
        settings,
        MockLLMClient(delay_sec=0),
        FailoverTTS(MockTTSProvider(delay_sec=0)),
        make_blocker(2),
        load_personas(),
        emit,
        tmp_path / "audio",
        seed=7,
        time_scale=time_scale,
    )
    return engine, events


async def wait_end(engine, timeout=10):
    async def _w():
        while engine.state != ShowState.ENDED:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_w(), timeout)


async def test_mode_b_runs_whole_rundown_and_log_reconstructs_it(tmp_path):
    engine, events = make_engine(tmp_path)
    engine.start()
    await wait_end(engine)

    log = list(read_log(engine.log.path))
    types = [l["type"] for l in log]
    assert types[0] == "session_start" and types[-1] == "session_end"
    assert log[0]["blocker"]["id"] == "blk_test" and log[-1]["reason"] == "completed"

    turns = [l for l in log if l["type"] == "turn"]
    segments = [t["segment"] for t in turns]
    assert segments[:2] == ["opening", "opening"] and segments[-2:] == ["closing", "closing"]
    per_topic = {tid: sum(1 for t in turns if t["topic_id"] == tid) for tid in ("t1", "t2")}
    assert all(n >= 6 for n in per_topic.values()), per_topic  # MIN_TURNS_PER_TOPIC dihormati
    assert [l["judul"] for l in log if l["type"] == "topic_change"] == ["Topik 1", "Topik 2", "Closing"]
    assert any(l["type"] == "showrunner" and l["decision"] == "transition" for l in log)

    speakers = [t["persona"] for t in turns]
    assert not any(speakers[i] == speakers[i + 1] == speakers[i + 2] for i in range(len(speakers) - 2))
    assert all(t["audio_url"] and (tmp_path / "audio" / t["audio_url"].split("/")[-1]).exists() for t in turns)
    assert [e for e, _ in events].count("turn") == len(turns)


async def test_skip_jumps_to_next_topic(tmp_path):
    engine, _ = make_engine(tmp_path, time_scale=0.02)
    engine.start()
    while engine.on_air["segment"] != "topic":
        await asyncio.sleep(0.01)
    await engine.skip()
    await wait_end(engine)
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    t1 = [t for t in turns if t["topic_id"] == "t1"]
    assert len(t1) < 6  # topik 1 dipotong operator
    assert any(l["type"] == "operator_action" and l["action"] == "skip" for l in read_log(engine.log.path))


async def test_stop_is_immediate_even_mid_audio(tmp_path):
    engine, _ = make_engine(tmp_path, time_scale=50.0)  # tiap giliran "diputar" sangat lama
    engine.start()
    while engine.turn_no < 1:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    start = asyncio.get_event_loop().time()
    await engine.stop()
    assert asyncio.get_event_loop().time() - start < 1.0
    assert engine.state == ShowState.ENDED
    assert list(read_log(engine.log.path))[-1]["reason"] == "stopped"


async def test_pause_holds_next_turn(tmp_path):
    engine, _ = make_engine(tmp_path, time_scale=0.02)
    engine.start()
    while engine.turn_no < 2:
        await asyncio.sleep(0.01)
    await engine.pause()
    await asyncio.sleep(0.3)
    played = len(engine.transcript)
    await asyncio.sleep(0.3)
    assert len(engine.transcript) == played  # tidak ada giliran baru selama pause
    await engine.resume()
    await wait_end(engine)
    assert engine.transcript[-1]["segment"] == "closing"


async def test_fixed_turns_policy(tmp_path):
    engine, _ = make_engine(tmp_path, SHOWRUNNER_POLICY="fixed_turns", FIXED_TURNS_PER_TOPIC=7)
    engine.start()
    await wait_end(engine)
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    # 7 giliran topik + 1 giliran transisi per topik
    assert sum(1 for t in turns if t["topic_id"] == "t1") == 8


def test_requires_locked_blocker(tmp_path):
    b = make_blocker()
    b.locked = False
    with pytest.raises(ValueError):
        ShowEngine(Settings(_env_file=None), MockLLMClient(), FailoverTTS(MockTTSProvider()), b, load_personas(), None, tmp_path)


async def test_report_summarizes_session(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from report import summarize, transcript_md

    engine, _ = make_engine(tmp_path)
    engine.start()
    await wait_end(engine)
    lines = list(read_log(engine.log.path))
    s = summarize(lines)
    assert s["end_reason"] == "completed" and s["turns"] == len([l for l in lines if l["type"] == "turn"])
    assert set(s["topics"]) == {"t1", "t2"} and s["topics"]["t1"]["coverage"] == "3/3"
    assert s["topics"]["t1"]["ended_by"] == "transition" and s["topics"]["t2"]["ended_by"] == "close"
    md = transcript_md(lines)
    assert "## Topik 1" in md and "**Raka:**" in md
