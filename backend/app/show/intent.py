"""Deteksi niat pindah topik dari ucapan penyiar mode A (PRD v2.7 FR-2, HANDOFF §2).

Fungsi murni berbasis aturan (tanpa LLM: tanpa kuota dan tanpa latensi tambahan). Hanya sinyal kuat yang
dihitung, karena salah pindah lebih merugikan daripada terlewat (tombol N tetap ada dan pindah bisa dibatalkan):

1. `frasa`: kata kerja pindah + "topik/bahasan/obrolan" + "selanjutnya/berikutnya/lain" (mis. "kita lanjut ke topik
   berikutnya"). Kata lepas seperti "lanjut", "next", "oke" saja TIDAK dihitung ("lanjut cerita dong" itu obrolan biasa).
2. `penutup`: ajakan masuk penutup/closing, hanya bila langkah berikutnya memang Closing.
3. `mulai`: dari Opening, ajakan memulai topik/obrolan pertama.
4. `transisi`: ucapan memuat sebagian besar kata isi kalimat pindah topik yang ditampilkan di prompter.
5. `judul`: ucapan menyebut sebagian besar kata isi judul topik berikutnya bersama kata kerja pindah.
"""

from __future__ import annotations

import re
from typing import Optional

_MOVE = r"(?:lanjut|pindah|masuk|geser|ganti|beralih|loncat|lompat|kita\s+ke)"
_TOPIC_WORD = r"(?:topik|bahasan|pembahasan|obrolan|materi|segmen)"
_NEXT = r"(?:selanjutnya|berikutnya|lain|baru|kedua|ketiga|keempat|kelima|keenam|ketujuh|kedelapan)"

_PHRASE = re.compile(rf"\b{_MOVE}\s+(?:ke\s+|aja\s+ke\s+|dulu\s+ke\s+)?{_TOPIC_WORD}\s+{_NEXT}\b")
_NEXT_TOPIC_EN = re.compile(r"\bnext\s+(?:topik|topic)\b")
_CLOSING = re.compile(
    r"\b(?:(?:masuk|lanjut|pindah|kita)\s+(?:ke\s+)?(?:penutup|closing|penutupan)"
    r"|saatnya\s+(?:kita\s+)?(?:tutup|rangkum|nutup|penutup)"
    r"|(?:kita|yuk)\s+(?:tutup|rangkum)\s+(?:obrolan|siaran|dulu))\b"
)
_START = re.compile(rf"\b(?:mulai|masuk|langsung|lanjut)\s+(?:ke\s+)?{_TOPIC_WORD}\s+(?:pertama|utama)\b|\bkita\s+mulai\s+(?:aja\s+)?(?:ya\s+)?{_TOPIC_WORD}\b")
# Ajakan pindah: harus ada "yuk/ayo/kita" + kata kerja pindah ("lanjut"/"bahas" lepas terlalu sering muncul di obrolan biasa).
_INVITE = re.compile(r"\b(?:yuk|ayo|kita)\b(?:\s+\w+){0,3}?\s+(?:lanjut|pindah|masuk|beralih|ngomongin|bahas|ngebahas|intip|ke)\b")
# Pertanyaan/tawaran ke lawan bicara ("lo mau lanjut ke bahasan lain nggak?") bukan keputusan pindah.
_QUESTION = re.compile(r"\?\s*$|\b(?:nggak|ngga|gak|enggak|kan|ga)\s*$|\b(?:mau|pengen|gimana|apa)\b.*\b(?:nggak|gak|ga|enggak)\b")

_STOP = set(
    "yang dan atau di ke dari untuk dengan ini itu ya yuk kita kamu lo lu gue aku kan sih nih deh dong aja juga udah sudah "
    "kalau kalo gimana apa ada jadi biar buat sama lagi pada tapi terus trus nah oke oh eh hmm soal tentang bareng mereka "
    "sobat hits sekarang abis habis".split()
)
TRANSITION_MIN_OVERLAP = 0.6
TRANSITION_MIN_WORDS = 3
TITLE_MIN_OVERLAP = 0.7
TITLE_MIN_WORDS = 2


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def _content_words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if len(w) >= 3 and w not in _STOP}


def _overlap(needle: set[str], hay: set[str]) -> float:
    return len(needle & hay) / len(needle) if needle else 0.0


def detect_topic_switch(
    text: str,
    *,
    segment: str,
    next_title: Optional[str],
    transition: str = "",
    next_is_closing: bool = False,
) -> Optional[str]:
    """Nama aturan yang cocok bila ucapan berniat pindah ke langkah berikutnya; None bila tidak.

    `segment`: segmen sekarang (opening/topic/closing). `next_title`: judul topik berikutnya (None bila berikutnya
    Closing). `transition`: kalimat pindah topik di materi (topik aktif). Closing tidak punya langkah berikutnya.
    """
    if segment not in ("opening", "topic"):
        return None
    t = _norm(text)
    if not t:
        return None
    words = _content_words(t)

    if _QUESTION.search(text.lower().strip()) or _QUESTION.search(t):
        return None
    if segment == "opening" and _START.search(t):
        return "mulai"
    if _PHRASE.search(t) or _NEXT_TOPIC_EN.search(t):
        return "frasa"
    if next_is_closing and _CLOSING.search(t):
        return "penutup"
    trans = _content_words(transition)
    common = trans & words
    # Kalimat pindah dibacakan hampir utuh (≥80%, ≥4 kata isi), atau sebagian (≥60%) bersama ajakan pindah.
    if len(trans) >= TRANSITION_MIN_WORDS and len(common) >= TRANSITION_MIN_WORDS and (
        (len(common) >= 4 and _overlap(trans, words) >= 0.8) or (_overlap(trans, words) >= TRANSITION_MIN_OVERLAP and _INVITE.search(t))
    ):
        return "transisi"
    title = _content_words(next_title or "")
    if (
        not next_is_closing
        and len(title) >= TITLE_MIN_WORDS
        and _overlap(title, words) >= TITLE_MIN_OVERLAP
        and _INVITE.search(t)
    ):
        return "judul"
    return None
