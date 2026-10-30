"""Bank filler per persona (FR-6, mode A): sahutan pendek yang diputar langsung
setelah penyiar manusia selesai bicara, sambil jawaban utama AI dibuat.

Setiap kalimat di-TTS sekali; FailoverTTS menyimpannya di cache file, jadi
persiapan berikutnya tidak memakai kredit lagi.
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.schemas import PersonaCard
from app.tts.provider import FailoverTTS

FILLER_FILE = Path(__file__).resolve().parents[1] / "data" / "filler.json"


@dataclass
class Filler:
    text: str
    url: str
    duration_s: float
    provider: str


class FillerBank:
    def __init__(self, tts: FailoverTTS, audio_dir: Path, rng: Optional[random.Random] = None):
        self._tts = tts
        self._dir = audio_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._rng = rng or random.Random()
        self._bank: dict[str, list[Filler]] = {}
        self._last: dict[str, str] = {}

    @staticmethod
    def phrases() -> dict[str, list[str]]:
        return json.loads(FILLER_FILE.read_text(encoding="utf-8"))

    async def prepare(self, persona: PersonaCard, concurrency: int = 4) -> int:
        """TTS semua filler persona (kena cache bila sudah pernah); kembalikan jumlah yang siap.

        Berjalan paralel terbatas (Edge butuh 1-4 s per kalimat; berurutan, 36 filler dua persona bisa
        lebih dari semenit) dan filler yang sudah siap langsung bisa dipakai `pick`, tanpa menunggu semuanya.
        """
        ready = self._bank[persona.id] = []
        gate = asyncio.Semaphore(max(1, concurrency))

        async def one(i: int, text: str) -> None:
            async with gate:
                try:
                    result = await self._tts.synthesize(text, persona.id)
                except Exception:
                    return  # satu filler gagal tidak masalah; sisanya tetap dipakai
            path = self._dir / f"filler_{persona.id}_{i:02d}_{result.provider}.{result.ext}"
            if not path.exists() or not result.cached:  # hasil baru menimpa file lama (suara atau prosodi bisa berubah)
                path.write_bytes(result.audio)
            ready.append(Filler(text, f"/audio/{path.name}", result.duration_s, result.provider))

        await asyncio.gather(*(one(i, t) for i, t in enumerate(self.phrases().get(persona.id, []))))
        return len(ready)

    def pick(self, persona_id: str) -> Optional[Filler]:
        options = self._bank.get(persona_id) or []
        if not options:
            return None
        fresh = [f for f in options if f.text != self._last.get(persona_id)] or options
        choice = self._rng.choice(fresh)
        self._last[persona_id] = choice.text
        return choice
