"""Penghitung kuota harian per model (PRD v2.7 §8, HANDOFF §2 "Cek kesiapan").

API Gemini tidak memberi sisa kuota harian (RPD), jadi permintaan dihitung sendiri: satu penghitung per MODEL
(kuota Google berlaku per model, bukan per peran; peran yang memakai model sama berbagi satu ember). Reset pukul
00.00 waktu Pasifik (America/Los_Angeles), sama dengan reset kuota Google. Disimpan di tabel quota_counters (database).

Angka ini perkiraan: penghitung baru mulai saat fitur ini dipakai, jadi hari pertama bisa terlalu kecil. Bila Google
menolak dengan kuota harian habis (429), model ditandai habis untuk hari itu.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select

from app.db import quota_counters

logger = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
COMPAT_PREFIX = "compat:"  # model berbayar lewat endpoint kompatibel OpenAI: tanpa kuota harian


class QuotaCounter:
    def __init__(self, db, limit_for: Callable[[str], int], now: Callable[[], datetime] | None = None):
        self._db = db
        self._limit_for = limit_for
        self._now = now or (lambda: datetime.now(PACIFIC))
        self._lock = threading.Lock()
        self._day = ""
        self._used: dict[str, int] = {}
        self._exhausted: set[str] = set()
        self._loaded = False

    def _today(self) -> str:
        return self._now().astimezone(PACIFIC).date().isoformat()

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        today = self._today()
        try:
            with self._db.engine.connect() as conn:
                rows = conn.execute(select(quota_counters).where(quota_counters.c.day == today)).all()
        except Exception as e:  # noqa: BLE001 - kuota hanya perkiraan; database bermasalah tidak boleh menahan siaran
            logger.warning("Penghitung kuota tidak terbaca dari database (%s); mulai dari nol", e)
            return
        self._day = today
        self._used = {r.model: int(r.used) for r in rows}
        self._exhausted = {r.model for r in rows if r.exhausted}

    def _roll(self) -> None:
        today = self._today()
        if self._day != today:
            self._day, self._used, self._exhausted = today, {}, set()

    def _save(self, model: str) -> None:
        """Tulis satu model (hari ini); baris hari-hari lalu ditimpa karena kuncinya model."""
        try:
            with self._db.engine.begin() as conn:
                conn.execute(delete(quota_counters).where(quota_counters.c.model == model))
                conn.execute(insert(quota_counters).values(model=model, day=self._day, used=self._used.get(model, 0), exhausted=model in self._exhausted))
        except Exception as e:  # noqa: BLE001
            logger.warning("Gagal menyimpan kuota %s ke database: %s", model, e)

    @staticmethod
    def tracked(model: str) -> bool:
        return bool(model) and not model.startswith(COMPAT_PREFIX)

    def record(self, model: str, n: int = 1) -> None:
        """Satu permintaan terkirim ke model ini (dipanggil klien LLM)."""
        if not self.tracked(model):
            return
        with self._lock:
            self._load()
            self._roll()
            self._used[model] = self._used.get(model, 0) + n
            self._save(model)

    def mark_exhausted(self, model: str) -> None:
        """Google menolak karena kuota harian habis: anggap sisa 0 sampai reset."""
        if not self.tracked(model):
            return
        with self._lock:
            self._load()
            self._roll()
            self._exhausted.add(model)
            self._save(model)

    def status(self, model: str) -> dict:
        """{used, limit, remaining, percent_left, exhausted, day}; limit 0 = tidak diketahui/tanpa batas."""
        with self._lock:
            self._load()
            self._roll()
            used = self._used.get(model, 0)
            exhausted = model in self._exhausted
        limit = self._limit_for(model) if self.tracked(model) else 0
        remaining: Optional[int] = None if not limit else (0 if exhausted else max(0, limit - used))
        return {
            "model": model,
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "percent_left": None if remaining is None else round(100 * remaining / limit),
            "exhausted": exhausted,
            "day": self._day,
        }

    def used_today(self) -> dict[str, int]:
        with self._lock:
            self._load()
            self._roll()
            return dict(self._used)
