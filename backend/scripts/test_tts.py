"""Uji nyata lapisan TTS: satu kalimat per persona per provider yang tersedia.

Memastikan audio tidak kosong, durasinya lebih dari 0 detik, dan suara Raka dan Salsa berbeda.
Hasil disimpan ke `backend/cache/test_tts/` supaya bisa didengar langsung.

    cd backend
    python scripts/test_tts.py                      # semua provider yang tersedia
    python scripts/test_tts.py --providers edge,gtts  # tanpa menyentuh kredit ElevenLabs

Provider yang tidak tersedia (gTTS belum terpasang, key ElevenLabs kosong) dilewati dan
dilaporkan; skrip gagal bila ada provider tersedia yang gagal, atau bila tidak ada yang lulus.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.data.personas import load_personas  # noqa: E402
from app.tts import EdgeTTSProvider, ElevenLabsTTSProvider, GTTSProvider, VoiceBook  # noqa: E402
from app.tts.base import mp3_duration  # noqa: E402

SENTENCE = "Halo Sobat Hits, kita ngobrol santai dulu ya soal kos-kosan hari ini."


def build(name: str, settings, book: VoiceBook):
    """(provider, alasan_dilewati)."""
    if name == "edge":
        return EdgeTTSProvider(book), ""
    if name == "gtts":
        try:
            import gtts  # noqa: F401
        except ImportError:
            return None, "pustaka gTTS belum terpasang (pip install gTTS)"
        return GTTSProvider(), ""
    if name == "elevenlabs":
        if not (settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_MODEL):
            return None, "ELEVENLABS_API_KEY atau ELEVENLABS_MODEL kosong"
        return ElevenLabsTTSProvider(settings.ELEVENLABS_API_KEY, settings.ELEVENLABS_MODEL, book), ""
    raise SystemExit(f"Provider tidak dikenal: {name}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="edge,gtts,elevenlabs")
    ap.add_argument("--text", default=SENTENCE)
    args = ap.parse_args()

    settings = get_settings()
    personas = load_personas()
    book = VoiceBook(settings, personas)
    out = Path(settings.CACHE_DIR) / "test_tts"
    out.mkdir(parents=True, exist_ok=True)

    failures, passed, audio_by_persona = 0, 0, {}
    for name in [n.strip() for n in args.providers.split(",") if n.strip()]:
        provider, skip = build(name, settings, book)
        if provider is None:
            print(f"[lewati] {name}: {skip}")
            continue
        for persona in personas:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(provider.synthesize(args.text, persona), 30)
                problems = []
                if not result.audio:
                    problems.append("audio kosong")
                if result.duration_s <= 0:
                    problems.append("durasi 0")
                if result.mime == "audio/mpeg" and mp3_duration(result.audio) <= 0:
                    problems.append("MP3 tidak valid")
            except Exception as e:  # noqa: BLE001 - laporan uji, bukan kode produksi
                result, problems = None, [f"{type(e).__name__}: {e}"[:200]]
            if problems:
                failures += 1
                print(f"[GAGAL]  {name:10s} {persona:6s} {'; '.join(problems)}")
                continue
            passed += 1
            path = out / f"{name}_{persona}.{result.ext}"
            path.write_bytes(result.audio)
            audio_by_persona[(name, persona)] = result.audio
            real = mp3_duration(result.audio) if result.mime == "audio/mpeg" else result.duration_s
            print(
                f"[ok]     {name:10s} {persona:6s} {result.duration_s:5.2f} s (frame {real:5.2f} s)  "
                f"{(time.perf_counter() - started) * 1000:5.0f} ms  voice={result.voice}  -> {path.name}"
            )

    # Suara Raka dan Salsa harus berbeda untuk provider yang punya suara per persona.
    for name in ("edge", "elevenlabs"):
        a, b = audio_by_persona.get((name, "raka")), audio_by_persona.get((name, "salsa"))
        if a is not None and b is not None:
            same = a == b
            failures += same
            print(f"[{'GAGAL' if same else 'ok'}]  {name}: suara Raka dan Salsa {'IDENTIK' if same else 'berbeda'}")

    print(f"\n{passed} sintesis lulus, {failures} gagal. Berkas audio: {out}")
    return 0 if passed > 0 and failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
