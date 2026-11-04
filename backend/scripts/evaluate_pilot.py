"""Evaluasi pilot Question Evasion dari sessions/<session_id>/turns.jsonl.

Contoh:
    cd backend
    python3 scripts/evaluate_pilot.py ../sessions/show_xxx/turns.jsonl --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.persona import detect_interrogative  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm import create_llm_client  # noqa: E402


JUDGE_SYSTEM = """
Kamu evaluator percakapan radio AI. Beri label respons atas pertanyaan manusia:
- clarity_level: CR | AMB | CNR
- level2: T1..T7 dengan peta:
  T1 Direct Answer
  T2 Reasoned Refusal
  T3 Deflection to Rundown
  T4 Dodging via Audience Hook
  T5 Rhetorical Counter-Questioning
  T6 Generalized Truism
  T7 Unreasoned Refusal
Balas JSON saja: {"clarity_level":"...","level2":"T?","reason":"..."}
""".strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def judge_pair(llm, model: str, question: str, answer: str) -> dict[str, str]:
    prompt = f"PERTANYAAN: {question}\n\nJAWABAN AI: {answer}"
    try:
        resp = await llm.generate(prompt, model=model, system_instruction=JUDGE_SYSTEM, temperature=0.0)
        parsed = resp.parsed if isinstance(resp.parsed, dict) else json.loads(resp.raw)
        return {
            "clarity_level": str(parsed.get("clarity_level", "AMB")),
            "level2": str(parsed.get("level2", "T6")),
            "reason": str(parsed.get("reason", "")),
        }
    except Exception:
        return {"clarity_level": "AMB", "level2": "T6", "reason": "judge_failed"}


def extract_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    pending_q: dict[str, Any] | None = None
    for r in rows:
        if r.get("is_human") and detect_interrogative(r.get("text", "")):
            pending_q = r
            continue
        if pending_q and not r.get("is_human"):
            pairs.append({"question": pending_q.get("text", ""), "answer": r.get("text", ""), "turn_q": pending_q.get("turn_idx"), "turn_a": r.get("turn_idx")})
            pending_q = None
    return pairs


def crr(labels: list[dict[str, str]]) -> float:
    if not labels:
        return 0.0
    good = 0
    for x in labels:
        if x["clarity_level"] == "CR" or x["level2"] == "T2":
            good += 1
    return round(100.0 * good / len(labels), 2)


def rar(rows: list[dict[str, Any]]) -> float:
    ai = [r for r in rows if not r.get("is_human")]
    if not ai:
        return 0.0
    ok = 0
    for r in ai:
        sv = r.get("supervisor_verdict") or {}
        checks = sv.get("checks") or {}
        if checks.get("blocker", "ok") == "ok":
            ok += 1
    return round(100.0 * ok / len(ai), 2)


def avg_latency(rows: list[dict[str, Any]]) -> float:
    vals = [float((r.get("timing_breakdown") or {}).get("persona_llm_ms", r.get("latency_llm_ms", 0))) for r in rows if not r.get("is_human")]
    return round(statistics.mean(vals), 2) if vals else 0.0


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("turns_jsonl")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    rows = read_jsonl(Path(args.turns_jsonl))
    pairs = extract_pairs(rows)

    settings = Settings(_env_file=None)
    llm = create_llm_client(settings)
    model = settings.GEMINI_MODEL_JUDGE or settings.GEMINI_MODEL_PERSONA or ""

    labels = []
    for p in pairs:
        labels.append({**p, **(await judge_pair(llm, model, p["question"], p["answer"]))})

    summary = {
        "file": args.turns_jsonl,
        "questions": len(pairs),
        "CRR": crr(labels),
        "RAR": rar(rows),
        "avg_persona_latency_ms": avg_latency(rows),
        "labels": labels,
    }

    print("=== Pilot Evaluation ===")
    print(f"Questions: {summary['questions']}")
    print(f"CRR: {summary['CRR']}%")
    print(f"RAR: {summary['RAR']}%")
    print(f"Avg Persona Latency: {summary['avg_persona_latency_ms']} ms")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {args.json_out}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
