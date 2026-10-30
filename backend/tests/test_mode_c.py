import asyncio
import json

import pytest

from app.agents.persona import HistoryEntry
from app.agents.summary import ConversationSummary
from app.config import Settings
from app.data.personas import load_personas
from app.llm import LLMClient, MockLLMClient
from app.show.engine import ShowEngine
from app.show.mode_a import HumanLedEngine, split_sentences
from app.show.participants import addressed_ais, build_participants
from app.show.turnlog import REQUIRED, TurnLog, topic_index
from app.tts import FailoverTTS, MockTTSProvider
from tests.test_persona import make_blocker


def read_rows(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def make_c(tmp_path, llm=None, **overrides):
    settings = Settings(LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"),
                        SHOWRUNNER_EVERY_K=2, _env_file=None, **overrides)
    events = []

    async def emit(t, d):
        events.append((t, d))

    engine = HumanLedEngine(
        settings, llm or MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), make_blocker(2),
        emit=emit, audio_dir=tmp_path / "audio", personas=load_personas(), ai_personas=["raka", "salsa"],
        human_name="Kak Dimas", seed=3, time_scale=0.0,
    )
    return engine, events


async def settle(engine):
    while engine._task and not engine._task.done():
        await asyncio.sleep(0.01)
    while engine._reply and not engine._reply.done():
        await asyncio.sleep(0.01)


async def talk(engine, text, **kw):
    info = await engine.human_turn(text, **kw)
    await settle(engine)
    return info


def ai_turns(events):
    return [d["persona"] for t, d in events if t == "turn"]


# ── Peserta ──────────────────────────────────────────────────────────────────


def test_participants_per_mode():
    personas = load_personas()
    assert [p.id for p in build_participants("A", personas, ["salsa"], "Dimas")] == ["human", "salsa"]
    assert [p.id for p in build_participants("B", personas)] == ["raka", "salsa"]
    c = build_participants("C", personas, None, "Dimas")
    assert [(p.id, p.kind) for p in c] == [("human", "human"), ("raka", "ai"), ("salsa", "ai")]
    with pytest.raises(ValueError):
        build_participants("A", personas, ["raka", "salsa"], "x")
    with pytest.raises(ValueError):
        build_participants("C", personas, ["raka"], "x")
    with pytest.raises(ValueError):
        build_participants("B", personas, ["raka", "tidak-ada"])


def test_addressed_ais_by_name_and_kalian():
    ais = [p for p in build_participants("C", load_personas(), None, "D") if not p.is_human]
    assert addressed_ais("Salsa, menurut lo gimana?", ais) == ["salsa"]
    assert addressed_ais("Menurut lo, raka, dan salsa juga ya", ais) == ["raka", "salsa"]
    assert addressed_ais("Halo semuanya", ais) == []
    assert addressed_ais("Kalian setuju nggak?", ais) == ["raka", "salsa"]
    assert addressed_ais("Salsa, kalian setuju?", ais) == ["salsa", "raka"]
    assert addressed_ais("rakyat salsabila", ais) == []  # bukan kata utuh


# ── Mode C ───────────────────────────────────────────────────────────────────


async def test_mode_c_snapshot_lists_both_ais_and_human(tmp_path):
    engine, _ = make_c(tmp_path)
    snap = engine.snapshot()
    assert engine.mode == "C" and [p["id"] for p in snap["personas"]] == ["raka", "salsa"]
    assert [(p["id"], p["kind"]) for p in snap["participants"]] == [("human", "human"), ("raka", "ai"), ("salsa", "ai")]
    assert snap["ai_persona"] is None


async def test_addressed_ai_answers_and_streak_returns_to_human(tmp_path):
    engine, events = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=0.0)
    engine.start()
    await settle(engine)
    info = await talk(engine, "Salsa, lo tim teh atau kopi?")
    assert info["responder"] == "salsa" and ai_turns(events) == ["salsa"]  # tanpa peluang menimpali
    assert engine._ai_streak == 1


async def test_unaddressed_turns_alternate_between_ais(tmp_path):
    engine, events = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=0.0)
    engine.start()
    await settle(engine)
    for text in ("Halo semuanya", "Lanjut ya", "Terus gimana"):
        await talk(engine, text)
    assert ai_turns(events) == ["raka", "salsa", "raka"]


async def test_second_ai_chimes_in_but_never_exceeds_streak_limit(tmp_path):
    engine, events = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=1.0)  # selalu menimpali, batas default 2
    engine.start()
    await settle(engine)
    await talk(engine, "Raka, ceritain dong")
    assert ai_turns(events) == ["raka", "salsa"] and engine._ai_streak == 2  # dua AI, lalu kembali ke manusia
    await talk(engine, "Oke lanjut")  # streak direset oleh ucapan manusia
    assert len(ai_turns(events)) == 4 and engine._ai_streak == 2


async def test_streak_limit_is_configurable(tmp_path):
    engine, events = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=1.0, MODE_C_MAX_AI_STREAK=1)
    engine.start()
    await settle(engine)
    await talk(engine, "Raka, ceritain dong")
    assert ai_turns(events) == ["raka"]


async def test_kalian_forces_both_even_with_zero_chime_probability(tmp_path):
    engine, events = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=0.0)
    engine.start()
    await settle(engine)
    await talk(engine, "Kalian berdua setuju nggak?")
    assert ai_turns(events) == ["raka", "salsa"]


async def test_chime_in_prompt_and_roster(tmp_path):
    engine, _ = make_c(tmp_path)
    ctx = engine._context(engine._ai("salsa"), chime_after="Raka")
    prompt = engine.persona_agent.turn_prompt(engine._ai("salsa"), ctx, None, engine.persona_agent._sample_length(ctx), None, None)
    assert "MENIMPALI ucapan Raka" in prompt and "1 sampai 2 kalimat" in prompt
    assert "Peserta siaran lainnya: Kak Dimas (penyiar manusia); Raka (penyiar AI)" in prompt
    assert "komentar" not in prompt.lower()


async def test_thinking_id_is_in_snapshot_while_generating(tmp_path):
    engine, _ = make_c(tmp_path, llm=MockLLMClient(delay_sec=0.3), MODE_C_CHIME_PROBABILITY=0.0)
    engine.start()
    await settle(engine)
    await engine.human_turn("Salsa, halo")
    await asyncio.sleep(0.1)
    assert engine.snapshot()["thinking"] == "salsa" and engine.snapshot()["busy"]
    await settle(engine)
    assert engine.snapshot()["thinking"] is None and not engine.snapshot()["busy"]


async def test_interrupt_cancels_the_chain_and_resets_streak(tmp_path):
    engine, events = make_c(tmp_path, llm=MockLLMClient(delay_sec=0.2), MODE_C_CHIME_PROBABILITY=1.0)
    engine.start()
    await settle(engine)
    await engine.human_turn("Raka, halo")
    await asyncio.sleep(0.05)
    await engine.human_turn("Eh tunggu dulu")  # memotong
    await settle(engine)
    assert any(t == "stop_audio" and d["reason"] == "interrupt" for t, d in events)
    assert engine._ai_streak <= 2


# ── turns.jsonl ──────────────────────────────────────────────────────────────


async def test_turns_jsonl_has_required_fields_for_human_and_ai(tmp_path):
    engine, _ = make_c(tmp_path, MODE_C_CHIME_PROBABILITY=1.0)
    engine.start()
    await settle(engine)
    await engine.skip()  # topik 1
    await talk(engine, "Raka, ceritain dong", stt_ms=420, speech_ms=1800)
    rows = read_rows(tmp_path / "sessions" / engine.session_id / "turns.jsonl")
    assert [r["speaker"] for r in rows] == ["human", "raka", "salsa"] and [r["turn_idx"] for r in rows] == [1, 2, 3]
    for r in rows:
        assert not [k for k in REQUIRED if k not in r]
        assert r["session_id"] == engine.session_id and r["mode"] == "C" and r["t_end"] >= r["t_start"] and r["topic_idx"] == 0
    human, raka, salsa = rows
    assert human["is_human"] and human["latency_asr_ms"] == 420 and human["text"] == "Raka, ceritain dong" and human["model"] == ""
    assert round(human["t_end"] - human["t_start"], 1) == 1.8
    assert not raka["is_human"] and raka["model"] == "mock" and raka["latency_llm_ms"] >= 0 and raka["tts_chars"] == sum(len(x) for x in split_sentences(raka["text"]))
    assert raka["filler_used"] is None or isinstance(raka["filler_used"], str)
    assert salsa["filler_used"] is None  # filler hanya untuk AI yang menjawab langsung
    assert raka["tts_provider"] == "mock" and raka["supervisor_action"] == "forward" and raka["interrupted"] is False


async def test_mode_b_writes_turns_jsonl_too(tmp_path):
    from tests.test_engine import make_engine, wait_end

    engine, _ = make_engine(tmp_path)
    engine.start()
    await wait_end(engine)
    rows = read_rows(tmp_path / "sessions" / engine.session_id / "turns.jsonl")
    assert len(rows) == engine.turn_no and all(not [k for k in REQUIRED if k not in r] for r in rows)
    assert {r["speaker"] for r in rows} == {"raka", "salsa"} and all(not r["is_human"] for r in rows)
    assert rows[0]["topic_idx"] is None and rows[0]["mode"] == "B" and any(r["topic_idx"] == 0 for r in rows)
    assert [r["turn_idx"] for r in rows] == sorted(r["turn_idx"] for r in rows)


def test_turnlog_rejects_incomplete_rows_and_parses_topic_idx(tmp_path):
    log = TurnLog(tmp_path / "s")
    with pytest.raises(ValueError, match="kekurangan medan"):
        log.write(session_id="x")
    assert topic_index("t3") == 2 and topic_index(None) is None and topic_index("closing") is None


# ── Hook Supervisor dan Showrunner ───────────────────────────────────────────


async def test_supervisor_hook_is_off_and_passthrough_by_default(tmp_path):
    assert Settings(_env_file=None).SUPERVISOR_MODE == "off"
    engine, _ = make_c(tmp_path)
    assert engine.supervisor.mode == "off"
    engine.start()
    await settle(engine)
    await talk(engine, "Raka, halo")
    assert engine.supervisor._llm is not None and getattr(engine.supervisor._llm, "calls", 0) == getattr(engine.persona_agent._llm, "calls", 0)


async def test_hook_vocabulary_maps_actions(tmp_path):
    from app.agents.supervisor import Reviewed
    from app.schemas import Emotion, SupervisorVerdict

    r = lambda a: Reviewed("x", Emotion.NEUTRAL, SupervisorVerdict(mode="rules", action=a), None)  # noqa: E731
    assert (r("forward").hook, r("regenerate").hook, r("fallback").hook) == ("teruskan", "koreksi", "ganti")


def test_showrunner_decision_has_indonesian_action():
    from app.schemas import ShowrunnerDecision

    pairs = {"continue": "lanjut", "steer": "lanjut", "transition": "pindah_topik", "close": "tutup"}
    for decision, aksi in pairs.items():
        d = ShowrunnerDecision(turn=1, topic_id="t1", decision=decision)
        assert d.aksi == aksi and d.model_dump()["aksi"] == aksi


# ── Ringkasan obrolan dan peserta N > 2 ──────────────────────────────────────


def history(n):
    return [HistoryEntry("raka" if i % 2 else "salsa", "Raka" if i % 2 else "Salsa", f"giliran nomor {i} soal kos dan teman sebelah") for i in range(n)]


async def test_summary_updates_in_background_once_turns_leave_the_window():
    s = ConversationSummary(MockLLMClient(delay_sec=0), "m", every=5, window=12)
    assert not s.due(history(16)) and s.due(history(17))
    h = history(20)
    s.schedule(h)
    await s._task
    assert s.upto == 8 and "Sudah dibahas" in s.text and s.updates == 1
    assert not s.due(h)  # sudah terkejar, tidak diulang
    s.schedule(h)
    assert s._task.done()


async def test_summary_falls_back_to_excerpts_when_llm_fails():
    class Broken(LLMClient):
        async def generate(self, *a, **k):
            raise RuntimeError("kuota")

    s = ConversationSummary(Broken(), "m", every=3, window=4)
    s.schedule(history(10))
    await s._task
    assert s.failures == 1 and s.upto == 6 and "giliran nomor 0" in s.text


async def test_summary_disabled_when_every_is_zero():
    s = ConversationSummary(MockLLMClient(delay_sec=0), "m", every=0)
    s.schedule(history(100))
    assert s._task is None and s.text == ""


async def test_summary_reaches_persona_prompt_in_long_session(tmp_path):
    from tests.test_engine import make_engine, wait_end

    engine, _ = make_engine(tmp_path, SUMMARY_EVERY_TURNS=2)
    engine.start()
    await wait_end(engine)
    assert engine.turn_no > 14
    await asyncio.sleep(0.05)
    assert engine.summary.updates >= 1
    ctx = engine._context(engine.personas[0])
    prompt = engine.persona_agent.turn_prompt(engine.personas[0], ctx, None, "sedang", None, None)
    assert "Ringkasan obrolan sebelumnya" in prompt


async def test_mode_b_supports_more_than_two_ais(tmp_path):
    personas = {k: v.model_copy(deep=True) for k, v in load_personas().items()}  # load_personas() di-cache: jangan mengubah aslinya
    personas["dina"] = personas["salsa"].model_copy(update={"id": "dina", "name": "Dina"})
    settings = Settings(LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"), _env_file=None)
    engine = ShowEngine(
        settings, MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), make_blocker(2), personas, None, tmp_path / "audio",
        ai_ids=["raka", "salsa", "dina"], time_scale=0.0,
    )
    assert [p.id for p in engine.personas] == ["raka", "salsa", "dina"]
    picks = [engine._pick_speaker().id for _ in range(5)]
    assert picks == ["raka", "salsa", "dina", "raka", "salsa"]
    ctx = engine._context(engine.personas[0])
    assert [n for n, _ in ctx.others] == ["Salsa", "Dina"]
