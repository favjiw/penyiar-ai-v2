"""Ukur latensi mode A tanpa browser (KT FR-7): ucapan penyiar tertulis → filler → jawaban AI.

Mengirim beberapa ucapan penyiar berurutan ke ModeAEngine headless dan mencatat
waktu dari "lepas tombol" (transkrip final diterima) ke filler dan ke kalimat
pertama jawaban AI. Waktu STT tidak termasuk; tambahkan hasil uji STT Tahap 0.

    cd backend
    python scripts/mode_a_probe.py --blocker blk_20261024_kos-kosan_ca3a --ai salsa
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.blocker import BlockerStore  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data.personas import load_personas  # noqa: E402
from app.llm import create_llm_client  # noqa: E402
from app.show.mode_a import ModeAEngine  # noqa: E402
from app.tts import create_tts  # noqa: E402

LINES = [
    "Halo Sobat Hits, hari ini gue ditemenin {ai}. Halo {ai}, apa kabar?",
    "Oke, kita langsung masuk ya. {ai}, lo pernah punya pengalaman aneh soal ini?",
    "Wah serius? Terus abis itu gimana?",
    "Ada komentar nih dari penonton, katanya mereka juga pernah ngalamin. Menurut lo kenapa ya?",
    "Hmm, tapi gue agak beda pendapat sih. Menurut gue itu tergantung orangnya.",
    "Oke, kalau lo harus kasih satu tips buat penonton, apa?",
    "Haha, bener juga. Ada yang mau lo tambahin sebelum kita lanjut?",
    "Sip. Sobat Hits, tulis pengalaman kalian di kolom komentar ya.",
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocker", required=True)
    ap.add_argument("--ai", default="salsa")
    ap.add_argument("--host", default="Kak Uji")
    args = ap.parse_args()

    settings = get_settings()
    marks: dict[str, float] = {}

    async def emit(type_: str, data: dict) -> None:
        if type_ in ("filler", "turn") and type_ not in marks:
            marks[type_] = time.perf_counter()

    personas = load_personas()
    engine = ModeAEngine(
        settings, create_llm_client(settings), create_tts(settings), BlockerStore(settings.DATA_DIR).get(args.blocker),
        emit=emit, audio_dir=Path(settings.CACHE_DIR) / "audio", personas=personas, ai_persona=args.ai,
        human_name=args.host, time_scale=0.0,
    )
    engine.start()
    await engine._task  # bank filler siap
    await engine.skip()  # masuk topik 1

    filler_ms, answer_ms = [], []
    ai_name = personas[args.ai].name
    for line in LINES:
        marks.clear()
        t0 = time.perf_counter()
        await engine.human_turn(line.format(ai=ai_name))
        await engine._reply
        f = (marks.get("filler", t0) - t0) * 1000
        a = (marks.get("turn", t0) - t0) * 1000
        filler_ms.append(f)
        answer_ms.append(a)
        reply = engine.transcript[-1]["text"]
        print(f"filler {f:5.0f} ms | jawaban {a:6.0f} ms | {reply[:90]}", flush=True)
    await engine.stop()

    def p(v: list[float], q: float) -> float:
        v = sorted(v)
        return v[min(len(v) - 1, round(q * (len(v) - 1)))]

    print(f"\nFiller: p50 {p(filler_ms, .5):.0f} ms, maks {max(filler_ms):.0f} ms (target ≤800 ms + STT)")
    print(f"Jawaban: p50 {statistics.median(answer_ms) / 1000:.2f} s, p95 {p(answer_ms, .95) / 1000:.2f} s (target p50 ≤4 s, p95 ≤7 s, termasuk STT)")
    print(f"Log: {engine.log.path}")


if __name__ == "__main__":
    asyncio.run(main())
