"""Tahap 0: ukur RTF model lip-sync (mis. MuseTalk) di PC lab GTX 1080.

Skrip ini tidak memasang model; ia menjalankan perintah inferensi model per audio uji,
mengukur waktu render, dan mencatat VRAM puncak lewat nvidia-smi.

    python tahap0/t2_rtf.py --video talk_calm_1.mp4 \
        --audio a05.wav a10.wav a20.wav \
        --cmd "python -m scripts.inference --video {video} --audio {audio} --out {out}" \
        --cwd D:/MuseTalk

Placeholder {video}, {audio}, {out} diganti per percobaan. Audio uji 5/10/20 s bisa dibuat
dari tts_bench.py (keluaran Gemini berupa WAV). RTF = waktu render / durasi audio;
gerbang adopsi T2: RTF ≤ 0,8 (mode B) dan ≤ 0,3 (mode A).
"""

from __future__ import annotations

import argparse
import csv
import shlex
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def audio_seconds(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    if shutil.which("ffprobe"):
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True,
        )
        return float(res.stdout.strip())
    raise SystemExit(f"{path.name}: pakai WAV atau pasang ffprobe untuk membaca durasi")


class VramSampler(threading.Thread):
    """Ambil memory.used GPU 0 tiap 0,5 s selama render."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak_mib = 0
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                self.peak_mib = max(self.peak_mib, int(out.splitlines()[0]))
            except Exception:
                pass
            self._halt.wait(0.5)

    def stop(self) -> int:
        self._halt.set()
        self.join()
        return self.peak_mib


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--audio", nargs="+", required=True)
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--repeat", type=int, default=1, help="ulangi tiap audio; percobaan pertama memuat model (cold)")
    ap.add_argument("--label", default="musetalk")
    args = ap.parse_args()

    out_dir = ROOT / "out" / "t2"
    out_dir.mkdir(parents=True, exist_ok=True)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    print(f"GPU: {gpu or 'tidak terdeteksi'}")

    rows = []
    for audio in map(Path, args.audio):
        dur = audio_seconds(audio)
        for r in range(1, args.repeat + 1):
            out = out_dir / f"{args.label}_{audio.stem}_{r}.mp4"
            cmd = args.cmd.format(video=Path(args.video).resolve(), audio=audio.resolve(), out=out)
            sampler = VramSampler()
            sampler.start()
            start = time.perf_counter()
            proc = subprocess.run(shlex.split(cmd, posix=False), cwd=args.cwd, capture_output=True, text=True)
            elapsed = time.perf_counter() - start
            peak = sampler.stop()
            row = {
                "label": args.label, "gpu": gpu, "audio": audio.name, "audio_s": round(dur, 2), "run": r,
                "render_s": round(elapsed, 2), "rtf": round(elapsed / dur, 3), "vram_peak_mib": peak,
                "ok": proc.returncode == 0, "stderr_tail": proc.stderr.strip()[-200:] if proc.returncode else "",
            }
            rows.append(row)
            print(f"{audio.name} run {r}: {elapsed:.1f}s / {dur:.1f}s audio -> RTF {row['rtf']} | VRAM puncak {peak} MiB {'' if row['ok'] else 'GAGAL'}")

    path = out_dir / f"rtf_{args.label}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Tersimpan: {path}")


if __name__ == "__main__":
    main()
