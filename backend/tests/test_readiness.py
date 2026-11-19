"""Cek kesiapan berbasis kuota (PRD v2.7 §6.4): menit aman per layanan, laju dari log, model dibagi per peran."""

from datetime import datetime

from app.config import Settings
from app.llm.quota import PACIFIC, QuotaCounter
from app.session_log import SessionLogger
from app.show.readiness import Rates, build_readiness, llm_requests_per_min, rates_from_logs
from tests.dbutil import make_db


def settings(**kw):
    base = dict(
        LLM_MODE="mock", TTS_MODE="mock", _env_file=None,
        GEMINI_MODEL_PERSONA="flash-lite", GEMINI_MODEL_SHOWRUNNER="flash-lite", GEMINI_MODEL_SUPERVISOR="flash-lite",
        GEMINI_MODEL_PERSONA_FALLBACK="", SHOWRUNNER_EVERY_K=3, SUMMARY_EVERY_TURNS=10, SUPERVISOR_MODE="off",
    )
    base.update(kw)
    return Settings(**base)


def counter(tmp_path, used=0, limit=500):
    q = QuotaCounter(make_db(tmp_path), lambda m: limit, lambda: datetime(2026, 11, 8, 12, tzinfo=PACIFIC))
    if used:
        q.record("flash-lite", used)
    return q


def test_roles_sharing_one_model_share_one_bucket():
    s = settings(SUPERVISOR_MODE="full")
    rpm = llm_requests_per_min(s, Rates(6.0, 0, "bawaan"))
    # persona 6 + showrunner 6/3 + ringkasan 6/10 + supervisor 6 = 14,6 per menit, semuanya satu model
    assert list(rpm) == ["flash-lite"] and abs(rpm["flash-lite"] - 14.6) < 1e-6


def test_minutes_safe_follows_gemini_quota_and_free_tts_is_unlimited(tmp_path):
    s = settings(GEMINI_MODEL_PERSONA_FALLBACK="gemini-2.5-flash")
    r = build_readiness(s, counter(tmp_path, used=200), mode="B", target_minutes=60, rates=Rates(6.0, 0, "bawaan"),
                        tts_primary="edge", tts_fallbacks=["gtts"], tts_credits_left=None)
    llm, tts = r["services"][0], r["services"][1]
    assert llm["percent_left"] == 60 and llm["minutes_left"] == int(300 / 8.6)  # 300 sisa ÷ (6 + 2 + 0,6)/mnt
    assert tts["unlimited"] is True and tts["minutes_left"] is None
    assert r["minutes_safe"] == int(300 / 8.6) and r["target_minutes"] == 60 and set(r["fallbacks"]) == {"llm", "tts"}


def test_mode_a_includes_free_stt_and_ignores_paid_compat_fallback(tmp_path):
    s = settings(GEMINI_MODEL_PERSONA_FALLBACK="compat:gemini-3.8-flash")
    r = build_readiness(s, counter(tmp_path), mode="A", target_minutes=60, rates=Rates(4.0, 0, "bawaan"),
                        tts_primary="edge", tts_fallbacks=[], tts_credits_left=None)
    assert [x["kind"] for x in r["services"]] == ["llm", "tts", "stt"]
    assert r["services"][1]["unlimited"] is True
    assert "llm" not in r["fallbacks"]


def test_rates_come_from_recent_logs_of_the_same_mode(tmp_path):
    db = make_db(tmp_path)

    def write(session_id, mode, minutes, turns, credit):
        log = SessionLogger(session_id, db)
        log.event("session_start", mode=mode)
        for _ in range(turns):
            log.event("turn", credit_cost=credit)
        log.event("session_end", elapsed_s=minutes * 60)

    write("show_20261108_100000_a", "B", 10, 70, 0)
    write("show_20261108_110000_b", "A", 10, 40, 0)
    write("show_20261108_120000_c", "B", 1, 10, 0)  # terlalu pendek: diabaikan
    r = rates_from_logs(db, "B", default_turns=5, default_credits=0)
    assert r.source == "log" and r.ai_turns_per_min == 7
    assert rates_from_logs(make_db(tmp_path, "kosong.db"), "B", 5, 0).source == "bawaan"


def test_daily_limit_is_the_strictest_role_using_the_model():
    s = settings(GEMINI_RPD_PERSONA=300, GEMINI_RPD_SHOWRUNNER=0, GEMINI_RPD_DEFAULT=500)
    assert s.rpd_for_model("flash-lite") == 300 and s.rpd_for_model("lain") == 500
