"""Gaya penyiar live TikTok HITS (docs/ANALISIS-LIVE-TIKTOK-2026-10-20.md §3.3).

Contoh diambil dari research/reference/hits-live-2026-10-20-onair.txt (hasil Whisper,
salah dengar sudah dirapikan). Petunjuk posisi (pembuka, sapaan, penutup) hanya
ditambahkan di giliran yang relevan, bukan di setiap giliran. Teksnya ada di database (snippet.*), bukan di kode. Dipakai ulang dari
repo lama tanpa rekap lagu (PRD §12: musik tidak lagi diputar di TikTok).
"""

from __future__ import annotations

from app.tuning import tuning

from app.content import content



def style_extras(turn_idx: int, closing: bool) -> list[str]:
    """Instruksi gaya HITS untuk satu giliran."""
    extras = [content.snippet("style_guide")]
    if closing:
        extras.append(content.snippet("closing_style_hint"))
    elif turn_idx == 0:
        extras.append(content.snippet("opening_hint"))
    elif turn_idx % tuning.GREETING_EVERY_TURNS == 2:
        extras.append(content.snippet("greeting_hint"))
    return extras
