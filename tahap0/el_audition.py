"""Tahap 0: audisi suara Indonesia ElevenLabs untuk Raka (pria) dan Salsa (wanita).

Kandidat di data/elevenlabs_candidates.csv diambil dari katalog publik json2video
(https://json2video.com/ai-voices/languages/indonesian/indonesia/), karena API key
uji tidak punya izin voices_read untuk mencari di Voice Library. Setiap kandidat
membaca 2 kalimat gaya HITS; skrip mencatat apakah voice bisa dipakai, latensi,
dan laju bicara (kata per detik).

    python tahap0/el_audition.py        # butuh ELEVENLABS_API_KEY dan ELEVENLABS_MODEL
"""

from __future__ import annotations

import asyncio
import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from tts_bench import cbr_mp3_duration, elevenlabs_tts

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "el_audition"
LINES = {
    "male": [
        "Halo Sobat Hits, balik lagi bareng gue Raka di sini, gimana kabarnya hari ini?",
        "Hahaha, iya iya, gue juga pernah kayak gitu, malu banget sumpah.",
    ],
    "female": [
        "Halo Sobat Hits, Salsa di sini! Eh, lo pernah nggak sih ditanya zodiak pas baru kenalan?",
        "Hmm, bentar-bentar, gue mikir dulu ya, soalnya ini agak tricky.",
    ],
}


async def main() -> None:
    load_dotenv(ROOT.parent / ".env")
    key, model = os.environ["ELEVENLABS_API_KEY"], os.environ["ELEVENLABS_MODEL"]
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = list(csv.DictReader(open(ROOT / "data" / "elevenlabs_candidates.csv", encoding="utf-8")))

    rows = []
    for c in candidates:
        for n, text in enumerate(LINES[c["gender"]], 1):
            row = {**c, "model": model, "line": n, "ok": False, "latency_s": "", "first_byte_s": "", "audio_s": "", "kata_per_s": "", "error": ""}
            try:
                import time

                start = time.perf_counter()
                audio, first = await asyncio.wait_for(elevenlabs_tts(text, c["voice_id"], model, key), 60)
                latency = time.perf_counter() - start
                dur = cbr_mp3_duration(audio)
                (OUT / f"{c['gender']}_{c['name'].replace(' ', '_')}_{n}.mp3").write_bytes(audio)
                row.update(ok=True, latency_s=round(latency, 2), first_byte_s=round(first, 2), audio_s=round(dur, 2),
                           kata_per_s=round(len(text.split()) / dur, 2) if dur else "")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"[:200]
            rows.append(row)
            print(f"{c['gender']:<6} {c['name']:<12} {n} ok={row['ok']} lat={row['latency_s']} first={row['first_byte_s']} dur={row['audio_s']} {row['error'][:90]}", flush=True)
            if row["error"]:
                break  # voice tidak bisa dipakai; lewati kalimat kedua

    with open(OUT / f"audition_{model}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    asyncio.run(main())
