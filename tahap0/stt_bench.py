"""Tahap 0: uji faster-whisper lokal (jalankan di PC lab GTX 1080).

Rekaman diambil dari stt_webspeech.html (tombol "Unduh rekaman") atau direkam
manual, dinamai 01.webm .. 20.webm (atau .wav) sesuai urutan stt_sentences.txt.

    python tahap0/stt_bench.py --audio-dir tahap0/out/stt_audio --model large-v3 --device cuda
    python tahap0/stt_bench.py --audio-dir ... --model small --device cpu --compute-type int8

Output: tahap0/out/stt/whisper_<model>.csv (WER, latensi, RTF) + ringkasan akurasi kata.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from wer import wer

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16", help="GTX 1080 (Pascal): coba float16, lalu int8_float32 bila lambat/galat")
    ap.add_argument("--beam-size", type=int, default=1, help="1 = greedy, paling cepat untuk live")
    ap.add_argument("--sentences", default=str(ROOT / "data" / "stt_sentences.txt"))
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    refs = [s.strip() for s in Path(args.sentences).read_text(encoding="utf-8").splitlines() if s.strip()]
    audio_dir = Path(args.audio_dir)

    t0 = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print(f"Model dimuat dalam {time.perf_counter() - t0:.1f}s")

    rows = []
    for i, ref in enumerate(refs, 1):
        files = [p for p in audio_dir.glob(f"{i:02d}.*")]
        if not files:
            print(f"{i:02d}: rekaman tidak ada, dilewati")
            continue
        start = time.perf_counter()
        segments, info = model.transcribe(str(files[0]), language="id", beam_size=args.beam_size, vad_filter=True)
        hyp = " ".join(s.text.strip() for s in segments)  # generator: transkripsi terjadi di sini
        latency = time.perf_counter() - start
        e = wer(ref, hyp)
        rows.append({
            "no": i, "ref": ref, "hyp": hyp, "wer": round(e, 3),
            "latency_s": round(latency, 3), "audio_s": round(info.duration, 2),
            "rtf": round(latency / info.duration, 3) if info.duration else "",
        })
        print(f"{i:02d}: WER={e:.2f} {latency:.2f}s | {hyp}")

    if not rows:
        return
    out = ROOT / "out" / "stt"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"whisper_{args.model}_{args.device}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    total_ref = sum(len(r["ref"].split()) for r in rows)
    weighted = sum(r["wer"] * len(r["ref"].split()) for r in rows) / total_ref
    lat = sorted(r["latency_s"] for r in rows)
    print(f"\nAkurasi kata ~ {(1 - weighted) * 100:.1f}% (target >=90%)")
    print(f"Latensi p50 {lat[len(lat) // 2]:.2f}s, maks {lat[-1]:.2f}s")
    print(f"Tersimpan: {path}")


if __name__ == "__main__":
    main()
