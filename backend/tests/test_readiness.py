"""Cek kesiapan berbasis kuota (PRD v2.7 §6.4): menit aman per layanan, laju dari log, model dibagi per peran."""

import json
from datetime import datetime

from app.config import Settings
from app.llm.quota import PACIFIC, QuotaCounter
from app.show.readiness import Rates, build_readiness, llm_requests_per_min, rates_from_logs


def settings(**kw):
    base = dict(
        LLM_MODE="mock", TTS_MODE="mock", _env_file=None,
        GEMINI_MODEL_PERSONA="flash-lite", GEMINI_MODEL_SHOWRUNNER="flash-lite", GEMINI_MODEL_SUPERVISOR="flash-lite",
        GEMINI_MODEL_PERSONA_FALLBACK="compat:gemini-3.8-flash", SHOWRUNNER_EVERY_K=3, SUMMARY_EVERY_TURNS=10, SUPERVISOR_MODE="off",
    )
    base.update(kw)
    return Settings(**base)


def counter(tmp_path, used=0, limit=500):
    q = QuotaCounter(tmp_path / "q.json", lambda m: limit, lambda: datetime(2026, 11, 8, 12, tzinfo=PACIFIC))
    if used:
        q.record("flash-lite", used)
    return q


def test_roles_sharing_one_model_share_one_bucket():
    s = settings(SUPERVISOR_MODE="full")
    rpm = llm_requests_per_min(s, Rates(6.0, 200, "bawaan"))
    # persona 6 + showrunner 6/3 + ringkasan 6/10 + supervisor 6 = 14,6 per menit, semuanya satu model
    assert list(rpm) == ["flash-lite"] and abs(rpm["flash-lite"] - 14.6) < 1e-6


def test_minutes_safe_is_the_tightest_known_service(tmp_path):
    s = settings()
    r = build_readiness(s, counter(tmp_path, used=200), mode="B", target_minutes=60, rates=Rates(6.0, 200, "bawaan"),
                        tts_primary="elevenlabs", tts_fallbacks=["edge"], tts_credits_left=4000)
    llm, tts = r["services"][0], r["services"][1]
    assert llm["percent_left"] == 60 and llm["minutes_left"] == int(300 / 8.6)  # 300 sisa ÷ (6 + 2 + 0,6)/mnt
    assert tts["minutes_left"] == 20  # 4000 kredit ÷ 200/mnt
    assert r["minutes_safe"] == 20 and r["target_minutes"] == 60 and set(r["fallbacks"]) == {"llm", "tts"}


def test_unknown_tts_credits_are_not_counted_and_free_tts_is_unlimited(tmp_path):
    s = settings()
    unknown = build_readiness(s, counter(tmp_path), mode="A", target_minutes=60, rates=Rates(4.0, 200, "bawaan"),
                              tts_primary="elevenlabs", tts_fallbacks=[], tts_credits_left=None)
    assert unknown["services"][1]["minutes_left"] is None and unknown["services"][1]["unlimited"] is False
    assert [x["kind"] for x in unknown["services"]] == ["llm", "tts", "stt"]
    free = build_readiness(s, counter(tmp_path), mode="B", target_minutes=60, rates=Rates(4.0, 200, "bawaan"),
                           tts_primary="edge", tts_fallbacks=[], tts_credits_left=None)
    assert free["services"][1]["unlimited"] is True


def test_rates_come_from_recent_logs_of_the_same_mode(tmp_path):
    def write(name, mode, minutes, turns, credit):
        lines = [{"type": "session_start", "mode": mode}]
        lines += [{"type": "turn", "credit_cost": credit} for _ in range(turns)]
        lines.append({"type": "session_end", "elapsed_s": minutes * 60})
        (tmp_path / name).write_text("\n".join(json.dumps(l) for l in lines))

    write("show_20261108_100000_a.jsonl", "B", 10, 70, 30)
    write("show_20261108_110000_b.jsonl", "A", 10, 40, 0)
    write("show_20261108_120000_c.jsonl", "B", 1, 10, 30)  # terlalu pendek: diabaikan
    r = rates_from_logs(tmp_path, "B", default_turns=5, default_credits=200)
    assert r.source == "log" and r.ai_turns_per_min == 7 and r.tts_credits_per_min == 210
    assert rates_from_logs(tmp_path / "kosong", "B", 5, 200).source == "bawaan"


def test_unknown_service_is_reported_not_treated_as_unlimited(tmp_path):
    r = build_readiness(settings(), counter(tmp_path), mode="B", target_minutes=60, rates=Rates(6.0, 200, "bawaan"),
                        tts_primary="elevenlabs", tts_fallbacks=[], tts_credits_left=None)
    assert r["unknown"] == ["Suara AI"] and r["minutes_safe"] is not None  # otak AI tetap diketahui


def test_paid_compat_model_has_no_daily_quota(tmp_path):
    s = settings(GEMINI_MODEL_PERSONA="compat:gemini-3.8-flash", GEMINI_MODEL_SHOWRUNNER="compat:gemini-3.8-flash")
    r = build_readiness(s, counter(tmp_path), mode="B", target_minutes=60, rates=Rates(6.0, 200, "bawaan"),
                        tts_primary="edge", tts_fallbacks=[], tts_credits_left=None)
    llm = r["services"][0]
    assert llm["unlimited"] is True and llm["paid"] is True and r["unknown"] == [] and r["minutes_safe"] is None


def test_daily_limit_is_the_strictest_role_using_the_model():
    s = settings(GEMINI_RPD_PERSONA=300, GEMINI_RPD_SHOWRUNNER=0, GEMINI_RPD_DEFAULT=500)
    assert s.rpd_for_model("flash-lite") == 300 and s.rpd_for_model("lain") == 500


def test_bad_log_lines_do_not_break_rates(tmp_path):
    (tmp_path / "show_x.jsonl").write_text('123\n{"type": "session_start", "mode": "B"}\nbukan json\n')
    assert rates_from_logs(tmp_path, "B", 5, 200).source == "bawaan"
