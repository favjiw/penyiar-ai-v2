"""Tahap 0: bandingkan Gemini TTS dan Edge TTS pada kalimat gaya HITS.

Contoh:
    python tahap0/tts_bench.py                 # kedua provider, suara pria + wanita
    python tahap0/tts_bench.py --provider edge

Output: tahap0/out/tts/<provider>_<gender>_<nn>.{wav,mp3} dan tts_results.csv
(latensi, durasi audio, RTF). Kolom `skor_robot` diisi manual oleh penilai (1-5).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
import time
import wave
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "tts"
SAMPLE_RATE = 24000  # Gemini TTS mengeluarkan PCM 16-bit mono 24 kHz


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_duration(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def edge_mp3_duration(mp3: bytes) -> float:
    """Edge TTS memakai audio-24khz-48kbitrate-mono-mp3 (CBR), jadi durasi = bit / 48 kbps."""
    return len(mp3) * 8 / 48000


async def gemini_tts(text: str, voice: str, model: str, api_key: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    resp = await client.aio.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    for part in resp.candidates[0].content.parts:
        if part.inline_data:
            return pcm_to_wav(part.inline_data.data)
    raise RuntimeError("Respons Gemini TTS tanpa audio")


async def edge_tts_bytes(text: str, voice: str) -> tuple[bytes, float]:
    """Kembalikan (mp3, detik sampai chunk audio pertama)."""
    import aiohttp
    import edge_tts

    # aiodns (bila terpasang) timeout 20 s di laptop ini; pakai resolver sistem (temuan repo lama).
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    start = time.perf_counter()
    first = None
    chunks: list[bytes] = []
    async for chunk in edge_tts.Communicate(text, voice, connector=connector).stream():
        if chunk["type"] == "audio":
            if first is None:
                first = time.perf_counter() - start
            chunks.append(chunk["data"])
    return b"".join(chunks), first or 0.0


async def main() -> None:
    load_dotenv(ROOT.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["gemini", "edge", "both"], default="both")
    ap.add_argument("--timeout", type=float, default=30.0, help="batas waktu per kalimat (detik)")
    ap.add_argument("--sentences", default=str(ROOT / "data" / "tts_sentences.txt"))
    args = ap.parse_args()

    sentences = [s.strip() for s in Path(args.sentences).read_text(encoding="utf-8").splitlines() if s.strip()]
    OUT.mkdir(parents=True, exist_ok=True)

    voices = {
        "gemini": {"male": os.getenv("GEMINI_VOICE_MALE", "Puck"), "female": os.getenv("GEMINI_VOICE_FEMALE", "Kore")},
        "edge": {"male": os.getenv("EDGE_VOICE_MALE", "id-ID-ArdiNeural"), "female": os.getenv("EDGE_VOICE_FEMALE", "id-ID-GadisNeural")},
    }
    providers = ["gemini", "edge"] if args.provider == "both" else [args.provider]
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL_TTS", "")
    if "gemini" in providers and not (api_key and model):
        print("GEMINI_API_KEY / GEMINI_MODEL_TTS kosong di .env; Gemini dilewati.")
        providers.remove("gemini")

    rows = []
    for provider in providers:
        for gender, voice in voices[provider].items():
            for i, text in enumerate(sentences, 1):
                stem = f"{provider}_{gender}_{i:02d}"
                start = time.perf_counter()
                first_chunk = None
                try:
                    if provider == "gemini":
                        audio = await asyncio.wait_for(gemini_tts(text, voice, model, api_key), args.timeout)
                        path = OUT / f"{stem}.wav"
                    else:
                        audio, first_chunk = await asyncio.wait_for(edge_tts_bytes(text, voice), args.timeout)
                        path = OUT / f"{stem}.mp3"
                    latency = time.perf_counter() - start
                    path.write_bytes(audio)
                    dur = wav_duration(audio) if provider == "gemini" else edge_mp3_duration(audio)
                    err = ""
                except Exception as e:  # catat galat (mis. kuota) lalu lanjut
                    latency, dur, path, err = time.perf_counter() - start, None, None, f"{type(e).__name__}: {e}"[:200]
                row = {
                    "provider": provider, "gender": gender, "voice": voice, "no": i, "text": text,
                    "latency_s": round(latency, 3),
                    "first_chunk_s": round(first_chunk, 3) if first_chunk is not None else "",
                    "audio_s": round(dur, 2) if dur else "",
                    "rtf": round(latency / dur, 2) if dur else "",
                    "file": path.name if path else "", "error": err, "skor_robot": "",
                }
                rows.append(row)
                print(f"{stem}: {row['latency_s']}s audio={row['audio_s']} {err}", flush=True)

    if not rows:
        return
    with open(OUT / "tts_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nTersimpan: {OUT / 'tts_results.csv'}")


if __name__ == "__main__":
    asyncio.run(main())
