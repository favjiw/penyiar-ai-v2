"""Jalankan satu sesi mode B tanpa browser (headless), dari blocker terkunci.

Dipakai untuk gerbang Tahap 2 (sesi 20 menit) dan sebagai dasar harness FR-14.
Konfigurasi (model, kebijakan, mode Supervisor, TTS) dari .env/environment.

    cd backend
    python scripts/run_show.py --blocker blk_20261024_kopi_ab12              # real time
    python scripts/run_show.py --blocker ... --time-scale 0 --tts-mock         # offline cepat
    python scripts/run_show.py --tema "Kos-kosan" --topik 3                    # buat + kunci blocker dulu
    python scripts/run_show.py --blocker ... --max-minutes 2                   # berhenti paksa (stop operator)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.blocker import BlockerGenerator, BlockerStore  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data.personas import load_personas  # noqa: E402
from app.llm import create_llm_client  # noqa: E402
from app.schemas import GenerateBlockerRequest, ShowState  # noqa: E402
from app.show.engine import ShowEngine  # noqa: E402
from app.tts import create_tts  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocker")
    ap.add_argument("--tema")
    ap.add_argument("--topik", type=int, default=3)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--time-scale", type=float, default=1.0, help="1 = real time; 0 = tanpa menunggu audio")
    ap.add_argument("--tts-mock", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop paksa setelah N menit (0 = sampai selesai)")
    args = ap.parse_args()

    if args.tts_mock:
        os.environ["TTS_MODE"] = "mock"
    settings = get_settings()
    llm = create_llm_client(settings)
    store = BlockerStore(settings.DATA_DIR)

    if args.blocker:
        blocker = store.get(args.blocker)
    elif args.tema:
        variants, meta = await BlockerGenerator(llm, settings.model_for("blocker"), store).generate(
            GenerateBlockerRequest(tema=args.tema, jumlah_topik=args.topik, jumlah_varian=2)
        )
        blocker = store.lock(variants[0].id)
        print(f"Blocker dibuat dan dikunci: {blocker.id} ({blocker.variant_label}) dalam {meta.latency_ms / 1000:.1f} s")
    else:
        ap.error("isi --blocker atau --tema")

    async def emit(type_: str, data: dict) -> None:
        stamp = time.strftime("%H:%M:%S")
        if type_ == "turn":
            print(f"{stamp} [{data['segment']}:{data['topic_id'] or '-'}] {data['name']}: {data['text']}  ({data['tts_provider']}, jeda {data['gap_ms']} ms)", flush=True)
        elif type_ == "showrunner":
            print(f"{stamp}   ↳ showrunner {data['decision']} jenuh={data['saturation']:.2f} cakup={len(data['points_covered'])} {data['steer_hint']} | {data['reason']}", flush=True)
        elif type_ == "supervisor":
            print(f"{stamp}   ↳ supervisor {data['action']} {data['rule_hits']} {data['evidence'][:100]}", flush=True)
        elif type_ == "topic_change":
            print(f"{stamp} === {data['judul']} ===", flush=True)

    tts = create_tts(settings)
    engine = ShowEngine(
        settings, llm, tts, blocker, load_personas(), emit, Path(settings.CACHE_DIR) / "audio", seed=args.seed, time_scale=args.time_scale
    )
    print(f"Sesi {engine.session_id}: {blocker.tema} · {blocker.variant_label} · log {engine.log.path}", flush=True)
    if settings.TTS_MODE == "live":
        try:
            print("Pemanasan TTS:", await tts.warm_up({p.gender: p.voices for p in load_personas().values()}), flush=True)
        except Exception as e:  # pemanasan gagal bukan alasan membatalkan sesi; failover yang menangani
            print(f"Pemanasan TTS gagal: {type(e).__name__}: {e}", flush=True)
    engine.start()
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    while engine.state != ShowState.ENDED:
        await asyncio.sleep(0.5)
        if deadline and time.monotonic() > deadline:
            await engine.stop()
    print(f"Selesai: {engine.turn_no} giliran, {(time.monotonic() - engine.started_at) / 60:.1f} menit. Log: {engine.log.path}")


if __name__ == "__main__":
    asyncio.run(main())
