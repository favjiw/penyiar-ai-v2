import asyncio

from app.config import Settings
from app.data.personas import load_personas
from app.llm import MockLLMClient
from app.schemas import ShowState
from app.session_log import read_log
from app.show.mode_a import ModeAEngine, split_sentences
from app.tts import FailoverTTS, MockTTSProvider
from tests.test_persona import make_blocker


def make(tmp_path, **overrides):
    settings = Settings(LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"),
                        SHOWRUNNER_EVERY_K=2, _env_file=None, **overrides)
    events = []

    async def emit(t, d):
        events.append((t, d))

    engine = ModeAEngine(settings, MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), make_blocker(2),
                         emit=emit, audio_dir=tmp_path / "audio", personas=load_personas(), ai_persona="salsa",
                         human_name="Kak Dimas", seed=3, time_scale=0.0)
    return engine, events


async def settle(engine):
    while engine._task and not engine._task.done():
        await asyncio.sleep(0.01)
    while engine._reply and not engine._reply.done():
        await asyncio.sleep(0.01)


def test_split_sentences_merges_short_ones():
    assert split_sentences("Wah! Iya bener banget itu, gue setuju. Terus gimana lagi nih?") == [
        "Wah! Iya bener banget itu, gue setuju.", "Terus gimana lagi nih?"]
    assert split_sentences("Satu kalimat saja") == ["Satu kalimat saja"]


async def test_human_turn_gets_filler_then_sentence_parts(tmp_path):
    engine, events = make(tmp_path)
    engine.start()
    await settle(engine)
    info = await engine.human_turn("Salsa, lo tim teh atau kopi?", stt_ms=420)
    assert info["filler"]
    await settle(engine)
    types = [t for t, _ in events]
    assert types.index("human_turn") < types.index("filler") < types.index("turn")
    turn = next(d for t, d in events if t == "turn")
    assert turn["persona"] == "salsa" and turn["parts"] >= 1 and turn["audio_url"]
    assert sum(1 for t, _ in events if t == "audio_part") == turn["parts"] - 1
    log = list(read_log(engine.log.path))
    rec = next(l for l in log if l["type"] == "turn")
    assert rec["mode"] == "A" and rec["filler"] == info["filler"] and rec["latency_ms"]["stt"] == 420
    assert any(l["type"] == "stt" and "teh atau kopi" in l["text"] for l in log)
    assert [e["persona"] for e in engine.transcript] == ["human", "salsa"]


async def test_prompt_names_human_and_stays_short(tmp_path):
    engine, _ = make(tmp_path)
    ctx = engine._context(engine.ai)
    prompt = engine.persona_agent.turn_prompt(engine.ai, ctx, None, engine.persona_agent._sample_length(ctx), None, None)
    assert "penyiar manusia bernama Kak Dimas" in prompt and "1 sampai 3 kalimat" in prompt


async def test_next_topic_is_manual_and_showrunner_only_advises(tmp_path):
    engine, events = make(tmp_path)
    engine.start()
    await settle(engine)
    await engine.skip()  # opening → topik 1
    assert engine.plan.segment == "topic" and engine.snapshot()["topic_points"][0]["id"] == "t1p1"
    for i in range(6):
        await engine.human_turn(f"pertanyaan ke-{i} soal kopi")
        await settle(engine)
    advice = [d for t, d in events if t == "showrunner"]
    assert advice and all(d["advisory"] for d in advice)
    assert engine.plan.segment == "topic" and engine.plan.topic_idx == 0  # tidak pindah sendiri
    await engine.skip(); await engine.skip(); await engine.skip()  # t2 → closing → selesai
    assert engine.state == ShowState.ENDED
    assert [d["judul"] for t, d in events if t == "topic_change"] == ["Topik 1", "Topik 2", "Closing"]


async def test_new_human_turn_interrupts_ai(tmp_path):
    engine, events = make(tmp_path)
    engine._time_scale = 50.0  # jawaban AI "diputar" lama
    engine.start()
    await settle(engine)
    await engine.human_turn("halo Salsa")
    while not any(t == "turn" for t, _ in events):
        await asyncio.sleep(0.01)
    await engine.human_turn("eh bentar, gue potong ya")
    assert any(t == "stop_audio" and d["reason"] == "interrupt" for t, d in events)
    engine._time_scale = 0.0
    engine._playback_done.set()
    await settle(engine)
    assert [e["persona"] for e in engine.transcript].count("human") == 2
