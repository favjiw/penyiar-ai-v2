"""Penghitung kuota harian per model (PRD v2.7 §8, HANDOFF §2 "Cek kesiapan").

API Gemini tidak memberi sisa kuota harian (RPD), jadi permintaan dihitung sendiri: satu penghitung per MODEL
(kuota Google berlaku per model, bukan per peran; peran yang memakai model sama berbagi satu ember). Reset pukul
00.00 waktu Pasifik (America/Los_Angeles), sama dengan reset kuota Google. Disimpan ke file JSON secara atomik.

Angka ini perkiraan: penghitung baru mulai saat fitur ini dipakai, jadi hari pertama bisa terlalu kecil. Bila Google
menolak dengan kuota harian habis (429), model ditandai habis untuk hari itu.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
COMPAT_PREFIX = "compat:"  # model berbayar lewat endpoint kompatibel OpenAI: tanpa kuota harian


class QuotaCounter:
    def __init__(self, path: str | Path, limit_for: Callable[[str], int], now: Callable[[], datetime] | None = None):
        self._path = Path(path)
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
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._day = data.get("day", "")
            self._used = {k: int(v) for k, v in data.get("used", {}).items()}
            self._exhausted = set(data.get("exhausted", []))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning("Berkas kuota %s tidak terbaca (%s); mulai dari nol", self._path, e)

    def _roll(self) -> None:
        today = self._today()
        if self._day != today:
            self._day, self._used, self._exhausted = today, {}, set()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".quota-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"day": self._day, "used": self._used, "exhausted": sorted(self._exhausted)}, f)
            os.replace(tmp, self._path)
        except OSError as e:
            logger.warning("Gagal menyimpan kuota ke %s: %s", self._path, e)

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
            self._save()

    def mark_exhausted(self, model: str) -> None:
        """Google menolak karena kuota harian habis: anggap sisa 0 sampai reset."""
        if not self.tracked(model):
            return
        with self._lock:
            self._load()
            self._roll()
            self._exhausted.add(model)
            self._save()

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
