"""Sisa kredit ElevenLabs untuk cek kesiapan (PRD v2.7 §6.4).

Endpoint `GET /v1/user/subscription` butuh izin `user_read` pada kunci API. Tanpa izin itu (atau saat galat),
sisa kredit TIDAK diketahui: dikembalikan None dengan catatan, tidak pernah dianggap 0 atau penuh.
"""

from __future__ import annotations

import time
from typing import Optional

SUBSCRIPTION_URL = "https://api.elevenlabs.io/v1/user/subscription"
CACHE_SEC = 60.0

_cache: dict[str, tuple[float, Optional[float], str]] = {}


async def elevenlabs_credits_left(api_key: str, timeout_sec: float = 8.0, fresh: bool = False) -> tuple[Optional[float], str]:
    """(sisa kredit atau None, catatan untuk Detail teknis). Hasil disimpan 60 dtk supaya cek berulang tidak memukul API;
    `fresh=True` (saat Mulai) melewati simpanan supaya perkiraan saat live tidak memakai angka basi."""
    if not api_key:
        return None, "Kunci ElevenLabs belum diisi"
    hit = _cache.get(api_key)
    if hit and not fresh and time.monotonic() - hit[0] < CACHE_SEC:
        return hit[1], hit[2]
    import httpx

    left: Optional[float] = None
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(SUBSCRIPTION_URL, headers={"xi-api-key": api_key})
        if r.status_code == 200:
            data = r.json()
            left = max(0.0, float(data["character_limit"]) - float(data["character_count"]))
            note = f"ElevenLabs: sisa {int(left)} dari {int(data['character_limit'])} kredit"
        elif r.status_code in (401, 403):
            note = "Kunci ElevenLabs tidak punya izin user_read; sisa kredit tidak bisa dibaca"
        else:
            note = f"ElevenLabs menjawab {r.status_code}; sisa kredit tidak diketahui"
    except Exception as e:  # jaringan, JSON, medan hilang
        note = f"Sisa kredit ElevenLabs tidak terbaca ({type(e).__name__})"
    _cache[api_key] = (time.monotonic(), left, note)
    return left, note
