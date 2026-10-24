"""Word error rate sederhana (Levenshtein di tingkat kata) untuk uji STT Tahap 0."""

from __future__ import annotations

import re


def normalize(text: str) -> list[str]:
    text = text.lower().replace("-", " ")
    return re.sub(r"[^\w\s]", " ", text).split()


def wer(ref: str, hyp: str) -> float:
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(r)
