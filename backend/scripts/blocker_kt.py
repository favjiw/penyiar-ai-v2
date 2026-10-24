"""Uji kriteria terima FR-1: 10 tema uji → varian valid ≤20 s, lalu dinilai Favian.

Menulis laporan Markdown berisi tabel latensi dan semua varian lengkap, dengan
kolom "Layak siar?" untuk diisi manual (target ≥8 dari 10 tema).

    cd backend
    python scripts/blocker_kt.py --out ../docs/kt/FR-1-blocker.md
    # LLM_MODE=live, GEMINI_API_KEY, dan GEMINI_MODEL_BLOCKER diambil dari .env
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.blocker import BlockerGenerationError, BlockerGenerator, BlockerStore  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import create_llm_client  # noqa: E402
from app.schemas import Blocker, GenerateBlockerRequest  # noqa: E402

TEMA_UJI = ["Ospek", "Zodiak", "Kos-kosan", "Skripsi", "Jajanan Bandung", "Mudik", "Cinta Lokasi", "Magang", "Hujan", "Kopi"]
BATAS_DETIK = 20


def render_blocker(b: Blocker) -> list[str]:
    lines = [f"**{b.variant_label}**", "", f"- Opening: *{b.opening.hook}* ({'; '.join(b.opening.poin)})"]
    for t in b.topics:
        lines.append(f"- **{t.judul}** — {t.sudut_pandang}")
        lines += [f"  - {p.text}{' ⚠️ perlu cek' if p.perlu_cek else ''}" for p in t.poin]
        lines.append(f"  - ❓ {t.pertanyaan_penonton}")
        lines.append(f"  - ↪ {t.transisi}")
    lines += [f"- Closing: {b.closing.rangkuman} · {b.closing.ajakan}", ""]
    return lines


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tema", nargs="*", default=TEMA_UJI)
    args = ap.parse_args()

    settings = get_settings()
    model = settings.model_for("blocker")
    gen = BlockerGenerator(create_llm_client(settings), model, BlockerStore(tempfile.mkdtemp()))

    rows, details = [], []
    for tema in args.tema:
        start = time.perf_counter()
        try:
            blockers, meta = await gen.generate(GenerateBlockerRequest(tema=tema))
            secs = time.perf_counter() - start
            rows.append((tema, f"{secs:.1f}", meta.attempts, "ya" if secs <= BATAS_DETIK else "TIDAK", ""))
            details += [f"### {tema}", ""] + [l for b in blockers for l in render_blocker(b)]
        except BlockerGenerationError as e:
            rows.append((tema, f"{time.perf_counter() - start:.1f}", "-", "GAGAL", f"{e} {e.issues}"[:150]))
        print(rows[-1], flush=True)

    ok = sum(1 for r in rows if r[3] == "ya")
    out = [
        f"# KT FR-1 Generator Blocker ({date.today():%d %b %Y})",
        "",
        f"Model `{model}` · LLM_MODE `{settings.LLM_MODE}` · prompt `{gen.prompt.version}`. "
        f"{ok}/{len(rows)} tema valid dalam ≤{BATAS_DETIK} s.",
        "",
        "Isi kolom **Layak siar?** (ya/tidak, tanpa edit besar). Target: ≥8 dari 10.",
        "",
        "| Tema | Waktu (s) | Percobaan | Valid ≤20 s | Layak siar? | Catatan |",
        "|---|---|---|---|---|---|",
    ]
    out += [f"| {t} | {s} | {a} | {v} | | {n} |" for t, s, a, v, n in rows]
    out += ["", "## Varian", ""] + details
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Tersimpan: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
