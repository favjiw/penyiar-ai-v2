"""Batas waktu satu obrolan = satu poin blocker (R4, arahan pembimbing HITS 30 Okt 2026).

Waktu dihitung dari durasi AUDIO (TTS yang diputar, dan ucapan penyiar manusia di mode A), bukan dari waktu
generate. Dua jam dipisah:

- `committed_s`: audio giliran yang sudah DIBUAT untuk poin ini (diputar atau masih antre karena pipelining).
  Dipakai untuk keputusan (anggaran kata, kapan giliran penutup), supaya giliran yang dibuat lebih dulu ikut dihitung.
- `played_s`: audio yang sudah selesai diputar; hanya untuk tampilan countdown.

Audio tidak pernah dipotong. Anggaran kata ada di prompt; kelebihan dirapikan dengan membuang KALIMAT utuh di
ujung (`trim_to_budget`), tidak pernah memotong di tengah kalimat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
TRIM_FACTOR = 1.3  # teks baru dirapikan bila lebih dari 1,3x anggaran kata


@dataclass
class PointClock:
    limit_s: float
    wrap_s: float = 15.0  # sisa waktu ≤ ini → giliran berikutnya menutup poin
    words_per_s: float = 2.0  # konservatif: Edge terukur 2,3; gTTS 1,9 (sesi 34 menit, 30 Okt 2026)
    min_words: int = 10
    committed_s: float = 0.0
    played_s: float = 0.0
    turns: int = 0

    @property
    def remaining_s(self) -> float:
        return self.limit_s - self.committed_s

    def commit(self, seconds: float, count_turn: bool = True) -> None:
        self.committed_s += max(0.0, seconds)
        if count_turn:
            self.turns += 1

    def should_close(self) -> bool:
        return self.remaining_s <= self.wrap_s

    def max_words(self) -> int:
        """Anggaran kata giliran berikutnya dari sisa waktu; tidak pernah di bawah `min_words`."""
        return max(self.min_words, int(self.remaining_s * self.words_per_s))

    def reset(self) -> None:
        self.committed_s = self.played_s = 0.0
        self.turns = 0


def count_words(text: str) -> int:
    return len(text.split())


def trim_to_budget(text: str, max_words: int, keep_last: bool = False) -> str:
    """Buang kalimat utuh bila teks melewati 1,3x anggaran; sisakan minimal satu kalimat.

    Biasanya dari ujung. `keep_last` (giliran penutup poin): kalimat terakhir adalah jembatan ke poin berikutnya,
    jadi yang dibuang kalimat sebelumnya.
    """
    if max_words <= 0 or count_words(text) <= max_words * TRIM_FACTOR:
        return text
    sentences = [s for s in _SENTENCE_END.split(text.strip()) if s]
    while len(sentences) > 1 and count_words(" ".join(sentences)) > max_words * TRIM_FACTOR:
        sentences.pop(-2 if keep_last else -1)
    return " ".join(sentences)
