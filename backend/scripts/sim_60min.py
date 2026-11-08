"""Simulasi siaran 60 menit mode A dan B tanpa kuota (HANDOFF §3 langkah 10, PRD v2.7 Tahap 9).

LLM dan TTS mock, waktu dipercepat:
- Mode B: engine berjalan tanpa jeda putar; "waktu siaran" = jumlah durasi audio giliran (TTS mock ±60 ms/karakter).
- Mode A: jam engine diganti jam tiruan yang maju sebesar ucapan penyiar + audio AI tiap pertukaran. Penyiar skrip
  menjawab sampai menit topik lewat (dengan lewat waktu acak 0–3 menit), lalu memindah topik lewat ucapan.

Yang diperiksa: tidak crash, semua topik + Closing tercapai, durasi total dekat target, mode A tanpa pindah otomatis,
kode halus sekali per topik yang lewat ≥ MODE_A_NUDGE_AFTER_S, pindah lewat ucapan terdeteksi.

Pakai:  cd backend && LLM_MODE=mock TTS_MODE=mock .venv/bin/python scripts/sim_60min.py [--seed 7] [--json hasil.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import tempfile
import time as real_time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.blocker import BlockerGenerator, BlockerStore  # noqa: E402
from app.config import Settings  # noqa: E402
from app.data.personas import load_personas  # noqa: E402
from app.llm import MockLLMClient  # noqa: E402
from app.schemas import GenerateBlockerRequest  # noqa: E402
from app.session_log import read_log  # noqa: E402
from app.show import engine as engine_mod  # noqa: E402
from app.show import mode_a as mode_a_mod  # noqa: E402
from app.show.engine import ShowEngine  # noqa: E402
from app.show.mode_a import HumanLedEngine  # noqa: E402
from app.tts.base import TTSError  # noqa: F401,E402
from app.tts.provider import FailoverTTS, MockTTSProvider  # noqa: E402

HOST_LINES = [
    "Gue jadi inget pengalaman pas awal kuliah dulu, seru banget sih",
    "Menurut lo kenapa banyak anak muda percaya soal ini",
    "Sobat Hits, tulis di komentar ya pengalaman kalian",
    "Tapi ada juga yang bilang itu cuma kebetulan doang",
    "Terus kalau dari sisi lo sendiri gimana",
    "Wah iya bener juga, gue setuju banget sama itu",
]


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t


def patch_clock(clock: FakeClock) -> None:
    """Hanya engine yang memakai jam tiruan; event loop asyncio tetap memakai jam asli."""
    proxy = SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time) if not k.startswith("_")})
    proxy.monotonic = clock.monotonic
    engine_mod.time = proxy
    mode_a_mod.time = proxy


async def make_blocker(tmp: Path, durasi: int):
    store = BlockerStore(tmp / "data")
    gen = BlockerGenerator(MockLLMClient(delay_sec=0), "mock", store)
    blockers, _ = await gen.generate(GenerateBlockerRequest(tema="Zodiak", durasi_menit=durasi, jumlah_varian=2))
    return store.lock(blockers[0].id)


def settings(tmp: Path, **kw) -> Settings:
    return Settings(LLM_MODE="mock", TTS_MODE="mock", LOG_DIR=str(tmp / "logs"), CACHE_DIR=str(tmp / "cache"),
                    SESSIONS_DIR=str(tmp / "sessions"), _env_file=None, **kw)


async def sim_mode_b(tmp: Path, seed: int, durasi: int, policy: str = "fixed_turns") -> dict:
    """`policy`: fixed_turns = hanya batas waktu per poin (jalur waktu); llm = Showrunner mock, yang SELALU menilai
    obrolan jenuh sehingga poin ditutup dini setelah POINT_MIN_TURNS (artefak mock, bukan perilaku LLM nyata)."""
    blocker = await make_blocker(tmp, durasi)
    events: list = []

    async def emit(t, d):
        events.append((t, d))

    s = settings(tmp, POINT_TIME_LIMIT_S=60, SHOWRUNNER_POLICY=policy)
    eng = ShowEngine(s, MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), blocker, load_personas(), emit,
                     tmp / "audio_b", seed=seed, time_scale=0.0)
    started = real_time.perf_counter()
    eng.start()
    while eng.state.value != "ended":
        await asyncio.sleep(0.01)
        if real_time.perf_counter() - started > 600:
            raise RuntimeError("mode B tidak selesai dalam 10 menit waktu nyata")
    log = list(read_log(eng.log.path))
    turns = [l for l in log if l["type"] == "turn"]
    per_topic: dict[str, float] = {}
    for t in turns:
        per_topic[t.get("topic_id") or t["segment"]] = per_topic.get(t.get("topic_id") or t["segment"], 0.0) + t["duration_s"]
    end = next(l for l in log if l["type"] == "session_end")
    return {
        "mode": "B",
        "showrunner": policy,
        "penutupan_poin": dict(__import__("collections").Counter(l["reason"] for l in log if l["type"] == "point_end")),
        "durasi_target_menit": durasi,
        "topik": len(blocker.topics),
        "menit_per_topik": [t.menit for t in blocker.topics],
        "giliran": len(turns),
        "menit_audio_total": round(sum(t["duration_s"] for t in turns) / 60, 1),
        "menit_audio_per_segmen": {k: round(v / 60, 1) for k, v in per_topic.items()},
        "topik_tercapai": sorted({t["topic_id"] for t in turns if t.get("topic_id")}),
        "closing_tercapai": any(t["segment"] == "closing" for t in turns),
        "selesai": end["reason"],
        "galat": [l for l in log if l["type"] == "error"][:5],
        "detik_nyata": round(real_time.perf_counter() - started, 1),
    }


async def sim_mode_a(tmp: Path, seed: int, durasi: int) -> dict:
    rng = random.Random(seed)
    clock = FakeClock()
    patch_clock(clock)
    blocker = await make_blocker(tmp, durasi)
    events: list = []

    async def emit(t, d):
        events.append((t, d))

    s = settings(tmp, POINT_TIME_LIMIT_S=60, MODE_A_NUDGE_AFTER_S=120, VOICE_SWITCH_UNDO_S=10)
    eng = HumanLedEngine(s, MockLLMClient(delay_sec=0), FailoverTTS(MockTTSProvider(delay_sec=0)), blocker,
                         emit=emit, audio_dir=tmp / "audio_a", personas=load_personas(), ai_persona="salsa",
                         human_name="Favian", seed=seed, time_scale=0.0)
    started = real_time.perf_counter()
    eng.start()

    async def settle():
        while (eng._task and not eng._task.done()) or (eng._reply and not eng._reply.done()):
            await asyncio.sleep(0.005)

    async def say(text: str) -> None:
        speech_s = max(2.0, len(text.split()) / 2.5)
        clock.t += speech_s
        n_turns = sum(1 for t, _ in events if t == "turn")
        await eng.human_turn(text, stt_ms=300, speech_ms=int(speech_s * 1000))
        await settle()
        new = [d for t, d in events if t == "turn"][n_turns:]
        clock.t += sum(d.get("duration_s", 0) for d in new) + 0.8 * len(new)  # audio AI + jeda

    await settle()
    overruns = {}
    # Opening ±3 menit
    while eng.show_clock()["segment_elapsed_s"] < 180:
        await say(rng.choice(HOST_LINES))
    await say("yuk kita mulai topik pertama")
    for i, topic in enumerate(blocker.topics):
        target = topic.menit * 60
        over = rng.choice([0, 30, 90, 150, 200])  # sebagian topik sengaja lewat >120 dtk supaya kode halus muncul
        while eng.show_clock()["segment_elapsed_s"] < target + over:
            await say(rng.choice(HOST_LINES))
        overruns[topic.id] = over
        assert eng.snapshot()["topic"]["id"] == topic.id, "mode A tidak boleh pindah sendiri"
        if i + 1 < len(blocker.topics):
            await say(topic.transisi)  # kalimat pindah topik dari materi, dibaca penyiar
            if eng.snapshot()["topic"]["id"] == topic.id:  # pengenal suara gagal menangkap: penyiar pakai frasa eksplisit
                await say("oke kita lanjut ke topik berikutnya ya")
        else:
            await say("oke saatnya kita rangkum obrolan hari ini")
    while eng.show_clock()["segment_elapsed_s"] < 180:
        await say(rng.choice(HOST_LINES))
    clock_end = eng.show_clock()
    await eng.stop()
    log = list(read_log(eng.log.path))
    nudges = [l for l in log if l["type"] == "nudge"]
    switches = [l for l in log if l["type"] == "voice_switch" and l["action"] == "switch"]
    topic_times = [l for l in log if l["type"] == "topic_time"]
    return {
        "mode": "A",
        "durasi_target_menit": durasi,
        "topik": len(blocker.topics),
        "menit_siaran_total": round(clock_end["elapsed_s"] / 60, 1),
        "target_s": clock_end["target_s"],
        "pertukaran": sum(1 for t, _ in events if t == "turn"),
        "pindah_lewat_ucapan": [(l["rule"], l["from_segment"], l["to_segment"]) for l in switches],
        "kode_halus": [(l["topic_id"], round(l["overrun_s"])) for l in nudges],
        "topik_lewat_dtk_rencana": overruns,
        "lama_topik": [(l["topic_id"], l["reason"], round(l["elapsed_s"]), l["nudged"]) for l in topic_times],
        "closing_tercapai": any(d.get("segment") == "closing" for t, d in events if t == "turn"),
        "galat": [l for l in log if l["type"] == "error"][:5],
        "detik_nyata": round(real_time.perf_counter() - started, 1),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--durasi", type=int, default=60)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        b = await sim_mode_b(tmp / "b", args.seed, args.durasi, "fixed_turns")
        b_llm = await sim_mode_b(tmp / "b_llm", args.seed, args.durasi, "llm")
        a = await sim_mode_a(tmp / "a", args.seed, args.durasi)
    out = {"B": b, "B_showrunner_mock": b_llm, "A": a}
    text = json.dumps(out, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
