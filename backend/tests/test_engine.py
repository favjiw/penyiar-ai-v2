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
    await asyncio.sleep(0.05)  # biarkan giliran berikutnya sudah disiapkan (pipelining)
    await engine.skip()
    await wait_end(engine)
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    t1 = [t for t in turns if t["topic_id"] == "t1"]
    assert len(t1) < 6  # topik 1 dipotong operator
    assert sum(1 for t in turns if t["topic_id"] == "t2") >= 6  # topik 2 tidak ikut terlewati
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


async def test_skip_while_next_topic_is_prefetched_moves_one_topic(tmp_path):
    engine, _ = make_engine(tmp_path, time_scale=0.05)
    engine.start()
    # Tunggu momen rencana sudah di topik 2 sementara yang terdengar masih topik 1.
    while not (engine.plan.segment == "topic" and engine.plan.topic_idx == 1 and engine._on_air_pos == ("topic", 0)):
        await asyncio.sleep(0.005)
    await engine.skip()
    await wait_end(engine)
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    assert sum(1 for t in turns if t["topic_id"] == "t2") >= 6


async def test_slow_llm_stages_fall_back_instead_of_dead_air(tmp_path):
    from app.llm import LLMClient

    class Hanging(LLMClient):
        async def generate(self, *a, **kw):
            await asyncio.sleep(30)

    engine, _ = make_engine(
        tmp_path, PERSONA_TIMEOUT_MS=50, SHOWRUNNER_TIMEOUT_MS=50, SUPERVISOR_MODE="rules", MIN_TURNS_PER_TOPIC=3, FIXED_TURNS_PER_TOPIC=3,
        PERSONA_FAILURES_BEFORE_WRAP=100,  # uji jalur timeout, bukan wrap-up
    )
    engine.persona_agent._llm = Hanging()
    engine.showrunner._llm = Hanging()
    engine.start()
    await wait_end(engine, timeout=15)
    log = list(read_log(engine.log.path))
    assert log[-1]["reason"] == "completed"
    assert any(l["type"] == "error" and l["stage"] == "persona" for l in log)
    assert any(l["type"] == "showrunner" and "SHOWRUNNER_TIMEOUT_MS" in l["reason"] for l in log)



async def test_topic_budget_keeps_topic_going_with_new_angles(tmp_path, monkeypatch):
    import time as real_time
    from types import SimpleNamespace

    import app.show.engine as engine_mod

    # Jam dinding engine dipercepat 20x: jatah ±60 s per topik selesai dalam ±3 s nyata.
    t0 = real_time.monotonic()
    fast = SimpleNamespace(monotonic=lambda: t0 + (real_time.monotonic() - t0) * 20, perf_counter=real_time.perf_counter, strftime=real_time.strftime)
    monkeypatch.setattr(engine_mod, "time", fast)

    engine, _ = make_engine(tmp_path, time_scale=0.05, SESSION_TARGET_MIN=2, CLOSING_TURNS=1)
    engine.start()
    await wait_end(engine, timeout=60)
    log = list(read_log(engine.log.path))
    budgets = [l for l in log if l["type"] == "quota" and "topic_budget_s" in l]
    assert [b["topic_id"] for b in budgets] == ["t1", "t2"]
    angles = [l for l in log if l["type"] == "showrunner" and l["steer_hint"].startswith("sudut baru")]
    assert angles, "poin habis sebelum jatah, harusnya ada arahan sudut baru"
    t1_end = next(l for l in log if l["type"] == "showrunner" and l["topic_id"] == "t1" and l["decision"] == "transition")
    assert "jatah topik tersisa" not in t1_end["reason"]  # pindah baru setelah jatah habis
    t1 = [l for l in log if l["type"] == "turn" and l["topic_id"] == "t1"]
    assert len(t1) > 7  # tanpa jatah, mock pindah di giliran 6


class _QuotaGone:
    """LLM yang selalu melaporkan kuota harian habis."""

    def __init__(self, model_ok=None, inner=None):
        self.model_ok, self.inner, self.models = model_ok, inner, []

    async def generate(self, prompt, *, model, **kw):
        from app.llm import LLMQuotaExhausted

        self.models.append(model)
        if model == self.model_ok:
            return await self.inner.generate(prompt, model=model, **kw)
        raise LLMQuotaExhausted("GenerateRequestsPerDayPerProjectPerModel-FreeTier")


async def test_persona_switches_to_fallback_model_on_daily_quota(tmp_path):
    engine, events = make_engine(tmp_path, GEMINI_MODEL_PERSONA="utama", GEMINI_MODEL_PERSONA_FALLBACK="cadangan")
    llm = _QuotaGone(model_ok="cadangan", inner=MockLLMClient(delay_sec=0))
    engine.persona_agent._llm = llm
    engine.start()
    await wait_end(engine)
    log = list(read_log(engine.log.path))
    assert log[-1]["reason"] == "completed"
    assert any(l["type"] == "quota" and l.get("model_to") == "cadangan" for l in log)
    assert not any(l["type"] == "error" and l["stage"] == "persona" for l in log)
    assert any(t == "alert" for t, _ in events)


async def test_persona_down_for_good_wraps_up_to_closing(tmp_path):
    engine, events = make_engine(tmp_path, SUPERVISOR_MODE="rules")
    engine.persona_agent._llm = _QuotaGone()
    engine.start()
    await wait_end(engine)
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    assert len(turns) <= 8  # tidak berputar di kalimat aman sampai topik habis
    assert turns[-1]["segment"] == "closing"
    assert any(t == "alert" and "Closing" in d["message"] for t, d in events)


async def test_supervisor_drops_to_rules_on_daily_quota(tmp_path):
    engine, events = make_engine(tmp_path, SUPERVISOR_MODE="full")
    engine.supervisor._llm = _QuotaGone()
    engine.start()
    await wait_end(engine)
    assert engine.supervisor.mode == "rules"
    turns = [l for l in read_log(engine.log.path) if l["type"] == "turn"]
    assert turns[-1]["supervisor"]["mode"] == "rules"
    assert sum(1 for t, d in events if t == "alert" and "Supervisor" in d["message"]) == 1
