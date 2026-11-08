"""Batas waktu per poin (R4): satu obrolan = satu poin, waktu dari durasi audio."""

import asyncio

from app.agents.persona import HistoryEntry
from app.session_log import read_log
from app.show.pointclock import PointClock, trim_to_budget
from tests.test_engine import make_engine, wait_end
from tests.test_mode_a import make, settle

TIMER = dict(POINT_TIME_LIMIT_S=20, POINT_WRAP_S=6, SHOWRUNNER_POLICY="fixed_turns", POINT_LIMIT_FROM_TOPIC=False)  # R4 asli (batas tetap); fixed_turns = Showrunner tidak dipanggil per poin


# ── Jam dan anggaran kata ────────────────────────────────────────────────────


def test_clock_closes_when_remaining_time_is_low_and_budget_never_below_floor():
    c = PointClock(60, wrap_s=15, words_per_s=2.0, min_words=10)
    assert not c.should_close() and c.max_words() == 120
    c.commit(40)
    assert not c.should_close() and c.max_words() == 40  # (60-40) * 2
    c.commit(8)
    assert c.should_close() and c.max_words() == 24
    c.commit(30)  # sudah lewat batas: tetap ada anggaran minimum untuk kalimat penutup
    assert c.remaining_s < 0 and c.max_words() == 10
    c.reset()
    assert c.committed_s == 0 and c.turns == 0


def test_trim_drops_whole_sentences_only_and_keeps_at_least_one():
    text = "Ini kalimat pertama yang cukup panjang. Ini kalimat kedua yang juga panjang. Ini ketiga."
    assert trim_to_budget(text, 100) == text  # di bawah anggaran
    trimmed = trim_to_budget(text, 8)
    assert trimmed == "Ini kalimat pertama yang cukup panjang." and trimmed in text
    one = "Satu kalimat panjang sekali tanpa titik di tengah"
    assert trim_to_budget(one, 3) == one  # satu kalimat tidak pernah dipotong


# ── Mode B ───────────────────────────────────────────────────────────────────


async def test_mode_b_walks_through_every_point_and_closes_each_on_time(tmp_path):
    engine, events = make_engine(tmp_path, **TIMER)
    engine.start()
    await wait_end(engine, timeout=20)
    log = list(read_log(engine.log.path))
    ends = [l for l in log if l["type"] == "point_end"]
    starts = [l for l in log if l["type"] == "point_start"]
    assert [e["point_id"] for e in ends] == ["t1p1", "t1p2", "t1p3", "t2p1", "t2p2", "t2p3"] and len(starts) == 6
    assert {e["reason"] for e in ends} == {"timer"}
    for e in ends:  # waktu habis tanpa memotong: kelebihan paling banyak satu giliran penutup
        assert 14 <= e["committed_s"] <= 20 + 6 and e["played_s_at_close"] <= e["committed_s"]  # diputar menyusul giliran yang sudah dibuat
    assert log[-1]["type"] == "session_end" and log[-1]["reason"] == "completed"
    texts = [d["text"] for t, d in events if t == "turn"]
    assert sum("kita lanjut ke bahasan berikutnya" in x for x in texts) == 4  # 2 poin non-terakhir x 2 topik
    assert sum("kita geser ke obrolan berikutnya" in x for x in texts) == 1  # penutup poin terakhir topik 1 → topik 2


async def test_mode_b_timer_off_keeps_topic_level_behaviour(tmp_path):
    engine, _ = make_engine(tmp_path, POINT_TIME_LIMIT_S=0)
    engine.start()
    await wait_end(engine)
    log = list(read_log(engine.log.path))
    assert not [l for l in log if l["type"] in ("point_start", "point_end")]
    assert engine.snapshot()["point_clock"] == {"active": False}


async def test_point_clock_events_show_played_time_and_on_air_point(tmp_path):
    engine, events = make_engine(tmp_path, **TIMER)
    engine.start()
    await wait_end(engine, timeout=20)
    clocks = [d for t, d in events if t == "point_clock" and d.get("active")]
    assert clocks and clocks[0]["limit_s"] == 20 and clocks[0]["total"] == 3
    first = [c for c in clocks if c["point_id"] == "t1p1"]
    assert first[0]["running"] is True and first[-1]["running"] is False
    assert first[-1]["played_s"] > first[0]["played_s"]  # naik hanya setelah audio selesai diputar
    assert [c["idx"] for c in clocks if c["topic_id"] == "t1"][0] == 0


async def test_prompt_has_word_budget_point_focus_and_no_later_points(tmp_path):
    engine, _ = make_engine(tmp_path, **TIMER)
    engine.plan.segment, engine.plan.topic_idx = "topic", 0
    engine._commit_point(8)
    ctx = engine._context(engine.personas[0])
    assert ctx.point == "poin 1.1" and ctx.max_words == int((20 - 8) * 2.0) and not ctx.close_point
    prompt = engine.persona_agent.turn_prompt(engine.personas[0], ctx, None, engine.persona_agent._sample_length(ctx), None, None)
    assert "FOKUS OBROLAN SEKARANG (poin 1 dari 3): poin 1.1" in prompt and "poin 1.2" not in prompt
    assert f"tidak lebih dari {ctx.max_words} kata" in prompt
    engine._commit_point(8)  # sisa 4 s ≤ 6 s → giliran penutup
    ctx = engine._context(engine.personas[0])
    assert ctx.close_point and ctx.next_point == "poin 1.2"
    prompt = engine.persona_agent.turn_prompt(engine.personas[0], ctx, None, engine.persona_agent._sample_length(ctx), None, None)
    assert "mengantar ke poin berikutnya" in prompt and "poin 1.2" in prompt
    engine.plan.point_idx = 2  # poin terakhir topik 1: penutup memakai jalur transisi topik yang sudah ada
    ctx = engine._context(engine.personas[0])
    assert ctx.close_point and ctx.transition_to.id == "t2" and ctx.next_point == ""


async def test_showrunner_may_close_a_point_early_but_timer_is_the_upper_bound(tmp_path):
    engine, _ = make_engine(tmp_path, POINT_TIME_LIMIT_S=600, POINT_WRAP_S=15, POINT_MIN_TURNS=3, SHOWRUNNER_POLICY="llm", SHOWRUNNER_EVERY_K=3)
    engine.start()
    await wait_end(engine, timeout=30)
    ends = [l for l in read_log(engine.log.path) if l["type"] == "point_end"]
    assert ends and {e["reason"] for e in ends} == {"early"}
    assert all(e["turns"] >= 3 and e["committed_s"] < 600 for e in ends)


async def test_advancing_the_segment_ends_the_open_point_with_reason_skip(tmp_path):
    engine, _ = make_engine(tmp_path, POINT_TIME_LIMIT_S=600, SHOWRUNNER_POLICY="fixed_turns", time_scale=0.0)
    engine.plan.segment = "topic"
    engine._commit_point(5)
    engine._advance_segment("skip")
    ends = [l for l in read_log(engine.log.path) if l["type"] == "point_end"]
    assert ends[0]["reason"] == "skip" and engine.plan.point_idx == 0 and engine.point_clock.committed_s == 0


# ── Mode A ───────────────────────────────────────────────────────────────────


async def test_mode_a_next_topic_button_still_works_and_resets_the_point(tmp_path):
    engine, _ = make(tmp_path, POINT_TIME_LIMIT_S=20)
    engine.start()
    await settle(engine)
    await engine.skip()
    engine.plan.point_idx = 2
    await engine.skip()  # next topik
    assert engine.plan.topic_idx == 1 and engine.plan.point_idx == 0 and engine.point_clock.committed_s == 0


# ── Temuan audit R4 ──────────────────────────────────────────────────────────


def test_trim_on_closing_turn_keeps_the_bridge_sentence():
    text = "Ini kalimat pembuka yang panjang sekali. Ini isi tengah yang juga panjang sekali. Oke, kita lanjut ke poin berikutnya ya."
    assert trim_to_budget(text, 8, keep_last=True) == "Oke, kita lanjut ke poin berikutnya ya."
    assert trim_to_budget(text, 8).startswith("Ini kalimat pembuka")  # tanpa keep_last: buang dari ujung


def test_wrap_must_be_smaller_than_limit():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(POINT_TIME_LIMIT_S=10, POINT_WRAP_S=15, _env_file=None)
    Settings(POINT_TIME_LIMIT_S=0, POINT_WRAP_S=15, _env_file=None)  # timer mati: tidak diperiksa


async def test_timed_topic_turns_advance_turn_in_segment(tmp_path):
    engine, _ = make_engine(tmp_path, **TIMER)
    seen = []
    original = engine._context

    def spy(speaker):
        ctx = original(speaker)
        if ctx.segment == "topic":
            seen.append((ctx.topic.id, ctx.turn_in_segment))
        return ctx

    engine._context = spy
    engine.start()
    await wait_end(engine, timeout=20)
    for tid in ("t1", "t2"):  # hanya giliran pertama topik yang berindeks 0 (pemicu OPENING_HINT di hits_style)
        idx = [n for t, n in seen if t == tid]
        assert idx[0] == 0 and all(n > 0 for n in idx[1:])


async def test_pipeline_depth_two_still_walks_all_points(tmp_path):
    engine, _ = make_engine(tmp_path, PIPELINE_DEPTH=2, **TIMER)
    engine.start()
    await wait_end(engine, timeout=30)
    ends = [l for l in read_log(engine.log.path) if l["type"] == "point_end"]
    assert [e["point_id"] for e in ends] == ["t1p1", "t1p2", "t1p3", "t2p1", "t2p2", "t2p3"]


async def test_stop_clears_the_clock(tmp_path):
    engine, events = make_engine(tmp_path, time_scale=1.0, **TIMER)
    engine.start()
    while not any(t == "point_clock" and d.get("active") for t, d in events):
        await asyncio.sleep(0.01)
    await engine.stop()
    assert engine.snapshot()["point_clock"] == {"active": False}
    assert [d for t, d in events if t == "point_clock"][-1] == {"active": False}


async def test_persona_failure_wrap_while_timed_still_plays_closing(tmp_path):
    engine, _ = make_engine(tmp_path, PERSONA_FAILURES_BEFORE_WRAP=1, PERSONA_FAILURE_WRAP_SEC=0, **TIMER)
    engine.plan.segment, engine.plan.topic_idx = "topic", 0
    engine._commit_point(5)
    ctx = engine._context(engine.personas[0])
    await engine._persona_failed(engine.personas[0], ctx, "kuota", permanent=True)
    assert engine.plan.segment == "closing" and engine._point_open is None and engine.point_clock.committed_s == 0
    engine.state = engine.state.__class__.LIVE
    assert not engine.plan.finished  # Closing tetap dimainkan, bukan langsung selesai


async def test_mode_a_never_advances_by_itself_even_far_past_time(tmp_path):
    """PRD v2.7: mode A tanpa pindah poin/topik otomatis; batas per poin R4 hanya untuk mode B."""
    engine, _ = make(tmp_path, POINT_TIME_LIMIT_S=20, POINT_WRAP_S=6)
    engine.start()
    await settle(engine)
    await engine.skip()  # topik 1
    for _ in range(8):  # jauh melewati 20 dtk per poin
        await engine.human_turn("cerita dong, panjang ya " * 10, speech_ms=15000)
        await settle(engine)
    snap = engine.snapshot()
    assert snap["segment"] == "topic" and snap["topic"]["id"] == "t1"
    assert snap["point_clock"] == {"active": False}
    log = list(read_log(engine.log.path))
    assert not [l for l in log if l["type"] in ("point_start", "point_end")]
    start = next(l for l in log if l["type"] == "session_start")
    assert start["effective"]["auto_advance"] is False


async def test_mode_b_point_limit_follows_topic_minutes(tmp_path):
    engine, _ = make_engine(tmp_path, POINT_TIME_LIMIT_S=20, POINT_WRAP_S=6, SHOWRUNNER_POLICY="fixed_turns")
    engine._advance_segment()  # Opening → topik 1
    t = engine.blocker.topics[0]
    assert engine.point_clock.limit_s == max(20, t.menit * 60 / len(t.poin))
