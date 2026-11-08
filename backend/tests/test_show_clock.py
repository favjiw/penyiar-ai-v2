"""Jam siaran untuk prompter (PRD v2.7): waktu aktif tanpa jeda, target durasi, waktu segmen."""

import asyncio

from tests.test_mode_a import make, settle


async def test_show_clock_excludes_pause_and_resets_per_segment(tmp_path):
    engine, events = make(tmp_path)
    engine.start()
    await settle(engine)
    c0 = engine.snapshot()["show_clock"]
    assert c0["running"] is True and c0["segment_target_s"] == 180  # Opening ±3 menit
    plan = 6 + sum(t.menit for t in engine.blocker.topics)
    assert c0["target_s"] == (engine.blocker.durasi_menit or plan) * 60

    await engine.pause()
    paused = engine.snapshot()["show_clock"]
    assert paused["running"] is False
    await asyncio.sleep(0.3)
    assert engine.snapshot()["show_clock"]["elapsed_s"] == paused["elapsed_s"]  # jeda tidak dihitung
    await engine.resume()

    await engine.skip()  # Opening → topik 1
    await settle(engine)
    clocks = [d for t, d in events if t == "show_clock"]
    assert clocks, "topic_change harus diikuti show_clock"
    c1 = engine.snapshot()["show_clock"]
    assert c1["segment_target_s"] == engine.blocker.topics[0].menit * 60
    assert c1["segment_elapsed_s"] < 2.0 and c1["segment_elapsed_s"] <= c1["elapsed_s"]
    await engine.stop()
    end = engine.snapshot()["show_clock"]
    await asyncio.sleep(0.2)
    assert engine.snapshot()["show_clock"]["elapsed_s"] == end["elapsed_s"] and end["running"] is False


async def test_speaking_cleared_after_ai_turn_mode_a(tmp_path):
    """Prompter menyalakan mic lagi saat AI selesai: harus ada kabar speaking=None setelah jawaban AI."""
    engine, events = make(tmp_path)
    engine.start()
    await settle(engine)
    await engine.human_turn("Salsa, lo tim teh atau kopi?", stt_ms=300)
    await settle(engine)
    types = [(t, d.get("persona")) for t, d in events if t in ("turn", "speaking")]
    last_turn = max(i for i, (t, _) in enumerate(types) if t == "turn")
    assert ("speaking", None) in types[last_turn:]
    assert engine.snapshot()["speaking"] is None
    await engine.stop()


async def test_speaking_cleared_after_each_turn_mode_b(tmp_path):
    from tests.test_engine import make_engine, wait_end

    engine, events = make_engine(tmp_path)
    engine.start()
    await wait_end(engine)
    turns = sum(1 for t, _ in events if t == "turn")
    cleared = sum(1 for t, d in events if t == "speaking" and d.get("persona") is None)
    assert turns > 0 and cleared >= turns


async def test_tts_quota_low_alert_fires_once(tmp_path):
    engine, events = make(tmp_path, TTS_QUOTA_ALERT_MIN=5)
    engine.tts_budget = {"credits_left": 900, "per_min": 200, "used_at_start": engine.tts.credits_used}  # ±4,5 menit
    engine.start()
    await settle(engine)
    await engine.human_turn("halo Salsa")
    await settle(engine)
    await engine.human_turn("terus?")
    await settle(engine)
    low = [d for t, d in events if t == "alert" and d["code"] == "tts_quota_low"]
    assert len(low) == 1 and low[0]["level"] == "yellow"
    assert engine.snapshot()["tts_minutes_left"] == 4
    await engine.stop()
