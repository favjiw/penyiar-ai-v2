"""Gaya penyiar live TikTok HITS (docs/ANALISIS-LIVE-TIKTOK-2026-10-20.md §3.3).

Contoh diambil dari app/data/reference/hits-live-2026-10-20-onair.txt (hasil Whisper,
salah dengar sudah dirapikan). Petunjuk posisi (pembuka, sapaan, penutup) hanya
ditambahkan di giliran yang relevan, bukan di setiap giliran. Dipakai ulang dari
repo lama tanpa rekap lagu (PRD §12: musik tidak lagi diputar di TikTok).
"""

from __future__ import annotations

STYLE_GUIDE = (
    "Gaya penyiar live HITS (contoh nyata, tiru nadanya, jangan disalin mentah):\n"
    '- "Sobat Hits, hari ini ada yang seru lho. Hmm, apa ya kira-kira? Daripada penasaran, yuk langsung aja kita bahas."\n'
    '- "Oh oke, bener-bener. Jatuhnya jadi hobi yang dibayar ya." / "Iya bener."\n'
    '- "Udah kepo belum, Sobat Hits? Kalau kepo, tungguin ya."\n'
    "Tanggapi partner dengan mengulang poinnya pakai kata-katamu sendiri (\"jatuhnya jadi ... ya\") atau sahutan "
    "pendek yang bervariasi (oh oke, wah, iya sih, aduh, ciee). Jangan mengulang sahutan yang sama seperti "
    "\"Bener banget!\". Sapaan \"Sobat Hits\" hanya kalau diminta di giliran ini."
)

OPENING_HINT = (
    "Ini giliran pembuka: buka dengan teaser atau pancingan rasa penasaran soal topik "
    "(misalnya \"apa ya kira-kira? daripada penasaran, yuk...\"), lalu masuk ke topik."
)

GREETING_HINT = "Di giliran ini boleh menyapa penonton dengan \"Sobat Hits\" sekali."

CLOSING_STYLE_HINT = (
    "Tutup dengan kalimat yang menggantung (\"kalau kepo, tungguin ya\") atau pesan untuk penonton "
    "(\"buat kamu yang lagi ..., jangan lupa ...\")."
)

GREETING_EVERY_TURNS = 5  # "Sobat Hits" sesekali, bukan di setiap giliran


def style_extras(turn_idx: int, closing: bool) -> list[str]:
    """Instruksi gaya HITS untuk satu giliran."""
    extras = [STYLE_GUIDE]
    if closing:
        extras.append(CLOSING_STYLE_HINT)
    elif turn_idx == 0:
        extras.append(OPENING_HINT)
    elif turn_idx % GREETING_EVERY_TURNS == 2:
        extras.append(GREETING_HINT)
    return extras
