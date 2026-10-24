"""Buat klip avatar dummy untuk menguji pemutar stage sebelum klip Google Flow siap (Tahap 3).

Satu klip per kode di Lampiran A PRD, 540x960 H.264 tanpa audio, warna latar per
persona dan label kode di tengah, plus manifest.json dengan format yang sama dengan
klip asli. Klip MP4 tidak di-commit (.gitignore); jalankan ulang bila perlu:

    pip install imageio-ffmpeg
    python assets/make_dummy_clips.py            # semua persona
    python assets/make_dummy_clips.py --force    # timpa klip yang sudah ada

Klip Flow asli cukup diletakkan di folder yang sama dengan nama kode yang sama;
manifest.json tinggal disesuaikan bila jumlah klip berbeda.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "avatar"

# Lampiran A: kode → (state, energi/emosi, durasi detik)
CLIPS = [
    ("idle_1", "idle", None, 6),
    ("idle_2", "idle", None, 6),
    ("idle_3", "idle", None, 6),
    ("listen_1", "listen", None, 5),
    ("listen_2", "listen", None, 5),
    ("listen_3", "listen", None, 5),
    ("talk_calm_1", "talk", "calm", 5),
    ("talk_calm_2", "talk", "calm", 5),
    ("talk_calm_3", "talk", "calm", 5),
    ("talk_hype_1", "talk", "hype", 4),
    ("talk_hype_2", "talk", "hype", 4),
    ("react_laugh", "react", "happy", 2),
    ("react_surprised", "react", "surprised", 2),
    ("react_thinking", "react", "thoughtful", 2),
    ("react_empathetic", "react", "empathetic", 2),
]
COLORS = {"raka": "0x1f3a5f", "salsa": "0x5f1f3a"}
STATE_DOT = {"idle": "gray", "listen": "skyblue", "talk": "lime", "react": "yellow"}


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def make_clip(path: Path, persona: str, code: str, state: str, seconds: int) -> None:
    # Lingkaran yang bergerak memperlihatkan loop dan crossfade; teks memperlihatkan klip mana yang aktif.
    label = f"{persona.upper()}\\n{code}"
    vf = (
        f"drawbox=x='270+120*sin(2*PI*t/{seconds})-40':y=380:w=80:h=80:color={STATE_DOT[state]}@0.9:t=fill,"
        f"drawtext=text='{label}':fontcolor=white:fontsize=44:x=(w-text_w)/2:y=560:line_spacing=12,"
        "drawtext=text='DUMMY':fontcolor=white@0.4:fontsize=28:x=(w-text_w)/2:y=880"
    )
    cmd = [
        ffmpeg(), "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={COLORS[persona]}:s=540x960:r=30:d={seconds}",
        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(path),
    ]
    # ffmpeg Windows dari imageio-ffmpeg mengeluh soal fontconfig untuk setiap klip; tampilkan hanya bila gagal.
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg gagal untuk {path.name}: {res.stderr[-500:]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for persona in COLORS:
        folder = ROOT / persona
        folder.mkdir(parents=True, exist_ok=True)
        manifest = {"persona": persona, "dummy": True, "clips": []}
        for code, state, tag, seconds in CLIPS:
            path = folder / f"{code}.mp4"
            if args.force or not path.exists():
                make_clip(path, persona, code, state, seconds)
            entry = {"code": code, "file": path.name, "state": state}
            if state == "talk":
                entry["energy"] = tag
            elif state == "react":
                entry["emotion"] = tag
            manifest["clips"].append(entry)
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"{persona}: {len(manifest['clips'])} klip di {folder}")


if __name__ == "__main__":
    main()
