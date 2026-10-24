"""Tahap 0: LLM-judge audio untuk menyaring kandidat suara (pendamping, bukan pengganti, penilai manusia).

Model Gemini multimodal mendengar setiap klip, mentranskripsi, lalu memberi skor 1-5 untuk:
kealamian (tidak seperti robot), logat Indonesia native, kecocokan gaya penyiar radio anak muda,
dan ekspresi. Kejelasan diukur dari WER transkripsi terhadap teks asli.

    python tahap0/audio_judge.py --dir tahap0/out/el_audition --texts-from el_audition
    # butuh GEMINI_API_KEY dan GEMINI_MODEL_JUDGE
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from wer import wer

ROOT = Path(__file__).resolve().parent
PROMPT = """Kamu juri casting suara untuk penyiar radio anak muda Bandung (gaya santai, "gue/lu").
Dengarkan klip audio ini. Balas JSON saja:
{"transkrip": "...", "alami": 1-5, "logat_indonesia": 1-5, "cocok_penyiar_muda": 1-5, "ekspresif": 1-5, "catatan": "<=15 kata"}
alami: 5 = terdengar seperti manusia, 1 = jelas robot/TTS. logat_indonesia: 5 = penutur asli Indonesia, 1 = logat asing kental."""


def main() -> None:
    load_dotenv(ROOT.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--texts-from", choices=["el_audition"], default="el_audition")
    ap.add_argument("--rpm", type=float, default=8)
    args = ap.parse_args()

    from google import genai
    from google.genai import types

    from el_audition import LINES

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ["GEMINI_MODEL_JUDGE"]
    rows = []
    for path in sorted(Path(args.dir).glob("*.mp3")):
        gender, *name, line = path.stem.split("_")
        ref = LINES[gender][int(line) - 1]
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/mp3"), PROMPT],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
                )
                j = json.loads(resp.text)
                break
            except Exception as e:
                j = {"catatan": f"galat: {e}"[:120]}
                time.sleep(30)
        row = {"file": path.name, "gender": gender, "name": " ".join(name), "line": line,
               "wer": round(wer(ref, j.get("transkrip", "")), 3) if "transkrip" in j else "",
               **{k: j.get(k, "") for k in ("alami", "logat_indonesia", "cocok_penyiar_muda", "ekspresif", "catatan", "transkrip")}}
        rows.append(row)
        print(f"{row['gender']:<6} {row['name']:<12} {line} wer={row['wer']} alami={row['alami']} logat={row['logat_indonesia']} cocok={row['cocok_penyiar_muda']} ekspr={row['ekspresif']}", flush=True)
        time.sleep(60 / args.rpm)

    out = Path(args.dir) / f"judge_{model}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Tersimpan: {out}")


if __name__ == "__main__":
    main()
