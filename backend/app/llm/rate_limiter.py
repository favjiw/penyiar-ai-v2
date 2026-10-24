"""Token-bucket rate limiter per model untuk kuota free tier Gemini.

Kuota Gemini berlaku per model, sedangkan konfigurasi ditulis per peran
(GEMINI_RPM_PERSONA, ...). Bila dua peran memakai model yang sama, batas
yang paling ketat yang dipakai.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, requests_per_minute: int = 15, name: str = "default"):
        self.rate = requests_per_minute
        self.name = name
        self._tokens = float(requests_per_minute)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.rate, self._tokens + (now - self._last_refill) * self.rate / 60.0)
        self._last_refill = now

    async def acquire(self) -> float:
        """Tunggu sampai ada token lalu pakai satu. Kembalikan lama menunggu (detik)."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            wait_sec = (1.0 - self._tokens) * 60.0 / self.rate
            logger.info("Rate limiter '%s': menunggu %.2fs", self.name, wait_sec)
            await asyncio.sleep(wait_sec)
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)
            return wait_sec

    @property
    def available_tokens(self) -> float:
        elapsed = time.monotonic() - self._last_refill
        return min(self.rate, self._tokens + elapsed * self.rate / 60.0)


class RateLimiterRegistry:
    def __init__(self, default_rpm: int = 5):
        self._default_rpm = default_rpm
        self._limits: dict[str, int] = {}
        self._limiters: dict[str, RateLimiter] = {}

    def set_limit(self, model: str, rpm: int) -> None:
        """Atur RPM model; bila sudah diatur peran lain, ambil yang lebih ketat."""
        if not model or rpm <= 0:
            return
        rpm = min(rpm, self._limits.get(model, rpm))
        self._limits[model] = rpm
        self._limiters.pop(model, None)

    def get(self, model: str) -> RateLimiter:
        if model not in self._limiters:
            self._limiters[model] = RateLimiter(self._limits.get(model, self._default_rpm), name=model)
        return self._limiters[model]

    def status(self) -> dict[str, dict[str, float]]:
        """Ringkasan untuk /api/health dan indikator kuota di konsol."""
        return {m: {"rpm": l.rate, "available": round(l.available_tokens, 2)} for m, l in self._limiters.items()}
