"""Klien worker avatar T2 (FR-9): kirim audio TTS, terima video lip-sync MuseTalk.

Aktif bila `AVATAR_TIER=t2` dan `AVATAR_WORKER_URL` diisi. Bila worker lambat, mati,
atau persona belum disiapkan di worker, giliran tetap jalan dengan avatar T1
(video_url kosong); kegagalan dicatat, tidak menghentikan siaran.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings


@dataclass
class RenderResult:
    path: Path
    render_ms: int
    rtf: float


class T2Client:
    def __init__(self, settings: Settings):
        self.url = settings.AVATAR_WORKER_URL.rstrip("/")
        self.enabled = settings.AVATAR_TIER == "t2" and bool(self.url)
        self.timeout = settings.AVATAR_RENDER_TIMEOUT_MS / 1000
        self.personas: Optional[set[str]] = None
        self.last_error = ""

    async def available(self, persona: str) -> bool:
        if not self.enabled:
            return False
        if self.personas is None:
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(f"{self.url}/health")
                    r.raise_for_status()
                    self.personas = set(r.json().get("avatars", []))
            except Exception as e:  # worker mati: coba lagi di giliran berikutnya
                self.last_error = f"health: {e}"
                return False
        return persona in self.personas

    async def render(self, persona: str, audio: Path) -> Optional[RenderResult]:
        if not await self.available(persona):
            return None
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.url}/render", params={"persona": persona}, content=audio.read_bytes())
                r.raise_for_status()
        except Exception as e:
            self.last_error = f"render: {type(e).__name__}: {e}"
            return None
        out = audio.with_suffix(".mp4")
        out.write_bytes(r.content)
        return RenderResult(out, int((time.perf_counter() - start) * 1000), float(r.headers.get("X-RTF", 0) or 0))
