"""Penghitung kuota harian per model (PRD v2.7 §8)."""

from datetime import datetime

from app.llm.quota import PACIFIC, QuotaCounter


class Clock:
    def __init__(self, dt):
        self.dt = dt

    def __call__(self):
        return self.dt


def test_counts_per_model_shared_across_roles_and_persists(tmp_path):
    clock = Clock(datetime(2026, 11, 8, 10, 0, tzinfo=PACIFIC))
    q = QuotaCounter(tmp_path / "quota.json", lambda m: 500, clock)
    for _ in range(3):
        q.record("gemini-3.5-flash-lite")  # persona, supervisor, showrunner memakai model yang sama
    q.record("compat:gemini-3.8-flash")  # model berbayar: tidak dihitung
    st = q.status("gemini-3.5-flash-lite")
    assert st["used"] == 3 and st["remaining"] == 497 and st["percent_left"] == 99
    assert q.status("compat:gemini-3.8-flash")["remaining"] is None
    again = QuotaCounter(tmp_path / "quota.json", lambda m: 500, clock)  # proses baru membaca berkas yang sama
    assert again.status("gemini-3.5-flash-lite")["used"] == 3


def test_resets_at_pacific_midnight_and_exhausted_means_zero(tmp_path):
    clock = Clock(datetime(2026, 11, 8, 23, 59, tzinfo=PACIFIC))
    q = QuotaCounter(tmp_path / "q.json", lambda m: 500, clock)
    q.record("m")
    q.mark_exhausted("m")
    assert q.status("m")["remaining"] == 0 and q.status("m")["exhausted"] is True
    clock.dt = datetime(2026, 11, 9, 0, 1, tzinfo=PACIFIC)
    st = q.status("m")
    assert st["used"] == 0 and st["remaining"] == 500 and st["exhausted"] is False


def test_unknown_limit_is_not_reported_as_full_or_empty(tmp_path):
    q = QuotaCounter(tmp_path / "q.json", lambda m: 0)
    q.record("m")
    st = q.status("m")
    assert st["remaining"] is None and st["percent_left"] is None and st["used"] == 1
