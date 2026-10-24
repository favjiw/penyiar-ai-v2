"""Ringkasan satu sesi dari log JSONL (FR-12) dan ekspor transkrip (§5.4).

    cd backend
    python scripts/report.py logs/show_20261024_101500_ab12.jsonl
    python scripts/report.py logs/show_....jsonl --transcript ../docs/transkrip.md --json ringkasan.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.session_log import read_log  # noqa: E402


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def summarize(lines: list[dict]) -> dict:
    start = next((l for l in lines if l["type"] == "session_start"), {})
    end = next((l for l in lines if l["type"] == "session_end"), {})
    turns = [l for l in lines if l["type"] == "turn"]
    decisions = [l for l in lines if l["type"] == "showrunner"]
    gaps = [t["latency_ms"]["gap_before_play"] for t in turns[1:]]
    stage = {k: [t["latency_ms"][k] for t in turns] for k in ("persona", "supervisor", "tts")}
    topics = {}
    for t in turns:
        if t["topic_id"]:
            d = topics.setdefault(t["topic_id"], {"turns": 0, "audio_s": 0.0})
            d["turns"] += 1
            d["audio_s"] = round(d["audio_s"] + t["duration_s"], 1)
    last_cov = {}
    for d in decisions:
        last_cov[d["topic_id"]] = d["points_covered"]
    blocker_topics = {t["id"]: len(t["poin"]) for t in start.get("blocker", {}).get("topics", [])}
    for tid, d in topics.items():
        d["coverage"] = f"{len(last_cov.get(tid, []))}/{blocker_topics.get(tid, '?')}"
        d["ended_by"] = next((x["decision"] + (" (forced)" if x["forced"] else "") for x in reversed(decisions)
                              if x["topic_id"] == tid and x["decision"] in ("transition", "close")), "operator/skip")
    return {
        "session_id": start.get("session_id"),
        "tema": start.get("blocker", {}).get("tema"),
        "config": start.get("config"),
        "end_reason": end.get("reason"),
        "elapsed_min": round(end.get("elapsed_s", 0) / 60, 1),
        "turns": len(turns),
        "audio_min": round(sum(t["duration_s"] for t in turns) / 60, 1),
        "gap_ms": {"p50": pct(gaps, 0.5), "p95": pct(gaps, 0.95), "max": max(gaps, default=0)},
        "stage_ms_p50": {k: pct(v, 0.5) for k, v in stage.items()},
        "supervisor_actions": dict(Counter(t["supervisor"]["action"] for t in turns)),
        "supervisor_rule_hits": dict(Counter(h for t in turns for h in t["supervisor"]["rule_hits"])),
        "supervisor_timeouts": sum(1 for t in turns if t["supervisor"]["timed_out"]),
        "showrunner_decisions": dict(Counter(d["decision"] for d in decisions)),
        "forced": sum(1 for d in decisions if d["forced"]),
        "tts_providers": dict(Counter(t["tts_provider"] or "none" for t in turns)),
        "credits_used": end.get("credits_used", 0),
        "errors": [{"stage": l.get("stage"), "message": l.get("message", "")[:120]} for l in lines if l["type"] == "error"],
        "topics": topics,
        "operator_actions": [l["action"] for l in lines if l["type"] == "operator_action"],
    }


def transcript_md(lines: list[dict]) -> str:
    start = next((l for l in lines if l["type"] == "session_start"), {})
    names = {"raka": "Raka", "salsa": "Salsa"}
    out = [f"# Transkrip {start.get('session_id', '')}", "", f"Tema: {start.get('blocker', {}).get('tema', '')}", ""]
    for l in lines:
        if l["type"] == "topic_change":
            out += ["", f"## {l['judul']}", ""]
        elif l["type"] == "turn":
            mark = "" if l["supervisor"]["action"] == "forward" else f" _[supervisor: {l['supervisor']['action']}]_"
            out.append(f"**{names.get(l['persona'], l['persona'])}:** {l['final_text']}{mark}")
            out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--transcript")
    ap.add_argument("--json")
    args = ap.parse_args()
    lines = list(read_log(args.log))
    summary = summarize(lines)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.transcript:
        Path(args.transcript).write_text(transcript_md(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
