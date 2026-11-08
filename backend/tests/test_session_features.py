import asyncio
import json

import pytest

from app.agents.persona import HistoryEntry
from app.agents.summary import ConversationSummary
from app.config import Settings
from app.data.personas import load_personas
from app.llm import LLMClient, MockLLMClient
from app.show.engine import ShowEngine
from app.session_log import read_log
from app.show.mode_a import HumanLedEngine, split_sentences
from app.show.participants import build_participants
from app.show.turnlog import REQUIRED, TurnLog, topic_index
from app.tts import FailoverTTS, MockTTSProvider
from tests.test_persona import make_blocker


def read_rows(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def make_a(tmp_path, llm=None, **overrides):
    overrides.setdefault("POINT_TIME_LIMIT_S", 0)  # tes lama menguji perilaku Showrunner per topik; timer poin diuji di test_point_timer.py
    settings = Settings(LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"),
                        SHOWRUNNER_EVERY_K=2, _env_file=None, **overrides)
    events = []

    async def emit(t, d):
        events.append((t, d))

    engine = HumanLedEngine(
        settings, llm or MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), make_blocker(2),
        emit=emit, audio_dir=tmp_path / "audio", personas=load_personas(), ai_persona="raka",
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
    with pytest.raises(ValueError):
        build_participants("A", personas, ["raka", "salsa"], "x")
    with pytest.raises(ValueError):
        build_participants("B", personas, ["raka"], "x")
    with pytest.raises(ValueError):
        build_participants("C", personas, None, "x")
    with pytest.raises(ValueError):
        build_participants("B", personas, ["raka", "tidak-ada"])


# ── Mode A ───────────────────────────────────────────────────────────────────


async def test_mode_a_snapshot_lists_human_and_one_ai(tmp_path):
    engine, _ = make_a(tmp_path)
    snap = engine.snapshot()
    assert engine.mode == "A" and [p["id"] for p in snap["personas"]] == ["raka"]
    assert [(p["id"], p["kind"]) for p in snap["participants"]] == [("human", "human"), ("raka", "ai")]
    assert snap["ai_persona"] == "raka"


async def test_thinking_id_is_in_snapshot_while_generating(tmp_path):
    engine, _ = make_a(tmp_path, llm=MockLLMClient(delay_sec=0.3))
    engine.start()
    await settle(engine)
    await engine.human_turn("Raka, halo")
    await asyncio.sleep(0.1)
    assert engine.snapshot()["thinking"] == "raka" and engine.snapshot()["busy"]
    await settle(engine)
    assert engine.snapshot()["thinking"] is None and not engine.snapshot()["busy"]


async def test_queued_human_turn_does_not_interrupt_running_answer(tmp_path):
    engine, events = make_a(tmp_path, llm=MockLLMClient(delay_sec=0.2))
    engine.start()
    await settle(engine)
    await engine.human_turn("Raka, halo")
    await asyncio.sleep(0.05)
    await engine.human_turn("Eh tunggu dulu")  # dulu memotong; sejak v2.7 diantrekan
    await settle(engine)
    assert not any(t == "stop_audio" for t, _ in events)
    rows = read_rows(tmp_path / "sessions" / engine.session_id / "turns.jsonl")
    assert not any(r["interrupted"] for r in rows)


# ── turns.jsonl ──────────────────────────────────────────────────────────────


async def test_turns_jsonl_has_required_fields_for_human_and_ai(tmp_path):
    engine, _ = make_a(tmp_path)
    engine.start()
    await settle(engine)
    await engine.skip()  # topik 1
    await talk(engine, "Raka, ceritain dong", stt_ms=420, speech_ms=1800)
    rows = read_rows(tmp_path / "sessions" / engine.session_id / "turns.jsonl")
    assert [r["speaker"] for r in rows] == ["human", "raka"] and [r["turn_idx"] for r in rows] == [1, 2]
    for r in rows:
        assert not [k for k in REQUIRED if k not in r]
        assert r["session_id"] == engine.session_id and r["mode"] == "A" and r["t_end"] >= r["t_start"] and r["topic_idx"] == 0
    human, raka = rows
    assert human["is_human"] and human["latency_asr_ms"] == 420 and human["text"] == "Raka, ceritain dong" and human["model"] == ""
    assert round(human["t_end"] - human["t_start"], 1) == 1.8
    assert not raka["is_human"] and raka["model"] == "mock" and raka["latency_llm_ms"] >= 0 and raka["tts_chars"] == sum(len(x) for x in split_sentences(raka["text"]))
    assert raka["filler_used"] is None or isinstance(raka["filler_used"], str)
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
    engine, _ = make_a(tmp_path)
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


# ── Kode halus mode A (PRD v2.7 FR-4) ────────────────────────────────────────


async def test_nudge_once_per_topic_after_overrun_and_not_on_questions(tmp_path):
    engine, events = make_a(tmp_path, MODE_A_NUDGE_AFTER_S=60)
    engine.start()
    await settle(engine)
    await engine.skip()  # topik 1 (±9 menit)
    target = engine.show_clock()["segment_target_s"]
    engine._segment_started_active -= target + 61  # topik sudah lewat >60 dtk
    await talk(engine, "Raka, lo pernah ngalamin nggak?")  # pertanyaan → kode halus ditunda
    assert not any(t == "nudge" for t, _ in events)
    await talk(engine, "Iya gue juga pernah gitu sih")
    await talk(engine, "Seru banget emang")
    nudges = [d for t, d in events if t == "nudge"]
    assert len(nudges) == 1 and nudges[0]["topic_id"] == "t1" and nudges[0]["to"] == engine.blocker.topics[1].judul
    rows = read_rows(tmp_path / "sessions" / engine.session_id / "turns.jsonl")
    assert [r["nudge"] for r in rows if r["speaker"] != "human"] == [False, True, False]
    log = list(read_log(engine.log.path))
    assert any(l["type"] == "nudge" for l in log)
    await engine.skip()
    exits = [l for l in read_log(engine.log.path) if l["type"] == "topic_time"]
    assert exits and exits[-1]["topic_id"] == "t1" and exits[-1]["nudged"] is True and exits[-1]["overrun_s"] > 60


# ── Pindah topik lewat ucapan (PRD v2.7 FR-2) ────────────────────────────────


async def test_voice_switch_moves_topic_before_ai_answers_and_can_be_undone(tmp_path):
    engine, events = make_a(tmp_path)
    engine.start()
    await settle(engine)
    await engine.skip()  # topik 1
    engine._segment_started_active -= 200  # topik 1 sudah berjalan 200 dtk
    await talk(engine, "oke kita lanjut ke topik berikutnya ya")
    assert engine.snapshot()["topic"]["id"] == "t2"
    change = [d for t, d in events if t == "topic_change"][-1]
    assert change["reason"] == "voice" and change["from"] == "Topik 1" and change["rule"] == "frasa"
    ai_turn = [d for t, d in events if t == "turn"][-1]
    assert ai_turn["topic_id"] == "t2"  # AI menjawab di topik baru

    assert await engine.undo_topic() is True
    snap = engine.snapshot()
    assert snap["topic"]["id"] == "t1" and snap["show_clock"]["segment_elapsed_s"] >= 200  # cincin tidak penuh lagi
    assert [d for t, d in events if t == "topic_change"][-1]["reason"] == "undo"
    assert await engine.undo_topic() is False  # hanya sekali
    log = [l for l in read_log(engine.log.path) if l["type"] == "voice_switch"]
    assert [l["action"] for l in log] == ["switch", "undo"]


async def test_ordinary_talk_does_not_switch_and_undo_expires(tmp_path):
    engine, _ = make_a(tmp_path, VOICE_SWITCH_UNDO_S=0)
    engine.start()
    await settle(engine)
    await engine.skip()
    await talk(engine, "lanjut cerita dong Raka")
    assert engine.snapshot()["topic"]["id"] == "t1"
    await talk(engine, "yuk pindah ke topik selanjutnya")
    assert engine.snapshot()["topic"]["id"] == "t2"
    await asyncio.sleep(0.01)
    assert await engine.undo_topic() is False  # jendela batal sudah lewat


async def test_voice_switch_to_closing_undo_to_opening_and_no_double_jump(tmp_path):
    engine, events = make_a(tmp_path)
    engine.start()
    await settle(engine)
    await talk(engine, "yuk kita mulai topik pertama")  # Opening → topik 1
    assert engine.snapshot()["topic"]["id"] == "t1"
    await talk(engine, "oke kita lanjut ke topik berikutnya ya")  # masih dalam jendela batal: diabaikan
    assert engine.snapshot()["topic"]["id"] == "t1"
    assert await engine.undo_topic() is True
    assert engine.snapshot()["segment"] == "opening"
    await engine.skip()  # topik 1
    await engine.skip()  # topik 2 = topik terakhir (make_blocker 2 topik)
    await talk(engine, "oke saatnya kita rangkum obrolan hari ini")
    assert engine.snapshot()["segment"] == "closing"


async def test_voice_switch_while_ai_busy_is_applied_and_answer_queued(tmp_path):
    engine, events = make_a(tmp_path)
    engine._time_scale = 50.0
    engine.start()
    await settle(engine)
    await engine.skip()
    await engine.human_turn("Raka, cerita dong")
    while not any(t == "turn" for t, _ in events):
        await asyncio.sleep(0.01)
    info = await engine.human_turn("oke kita lanjut ke topik berikutnya ya")
    assert info["queued"] is True and engine.snapshot()["topic"]["id"] == "t2"
    engine._time_scale = 0.0
    engine._playback_done.set()
    await settle(engine)
    assert [d for t, d in events if t == "turn"][-1]["topic_id"] == "t2"  # jawaban antrean di topik baru
