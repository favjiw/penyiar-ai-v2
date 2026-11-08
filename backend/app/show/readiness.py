"""Cek kesiapan siaran berbasis kuota (PRD v2.7 §6.4, HANDOFF §2, mockup KonsolCekKesiapan).

Menjawab "siaran aman sampai berapa menit?" per layanan: otak AI (kuota harian per model, dihitung sendiri),
suara AI (sisa kredit ElevenLabs bila bisa dibaca; Edge/gTTS tanpa batas), dan pendengar suara penyiar (mode A,
Web Speech di browser: tanpa kuota). Laju pemakaian per menit diukur dari log sesi sebelumnya; bila belum ada,
dipakai nilai bawaan dari .env. Semua angka adalah PERKIRAAN.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

MIN_SESSION_S = 180  # sesi lebih pendek dari ini tidak dipakai untuk mengukur laju
RECENT_SESSIONS = 5
MAX_FILES_SCANNED = 20  # batas berkas log yang dibaca (dibaca sinkron saat cek kesiapan)
COMPAT_PREFIX = "compat:"


@dataclass
class Rates:
    ai_turns_per_min: float
    tts_credits_per_min: float
    source: str  # "log" atau "bawaan"


def rates_from_logs(log_dir: str | Path, mode: str, default_turns: float, default_credits: float) -> Rates:
    """Rata-rata giliran AI dan kredit suara per menit dari sesi terakhir mode yang sama."""
    files = sorted(Path(log_dir).glob("show_*.jsonl"), reverse=True)
    turns_pm, credits_pm = [], []
    for f in files[:MAX_FILES_SCANNED]:
        if len(turns_pm) >= RECENT_SESSIONS:
            break
        start = end = None
        turns, credits = 0, 0.0
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                ev = json.loads(line)
                if not isinstance(ev, dict):
                    continue
                t = ev.get("type")
                if t == "session_start":
                    start = ev
                elif t == "session_end":
                    end = ev
                elif t == "turn":
                    turns += 1
                    credits += float(ev.get("credit_cost") or 0)
        except Exception:  # berkas log rusak tidak boleh menggagalkan cek kesiapan atau Mulai
            continue
        if not start or not end or start.get("mode") != mode:
            continue
        minutes = float(end.get("elapsed_s") or 0) / 60
        if minutes * 60 < MIN_SESSION_S or turns == 0:
            continue
        turns_pm.append(turns / minutes)
        if credits > 0:
            credits_pm.append(credits / minutes)
    if not turns_pm:
        return Rates(default_turns, default_credits, "bawaan")
    return Rates(
        sum(turns_pm) / len(turns_pm),
        sum(credits_pm) / len(credits_pm) if credits_pm else default_credits,
        "log",
    )


def llm_requests_per_min(settings, rates: Rates) -> dict[str, float]:
    """Permintaan per menit per MODEL: persona tiap giliran, Showrunner tiap k giliran, ringkasan tiap n giliran
    (memakai model Showrunner), Supervisor tiap giliran bila mode `full`. Model `compat:` tidak dihitung."""
    t = rates.ai_turns_per_min
    per_role = {
        "persona": t,
        "showrunner": t / max(1, settings.SHOWRUNNER_EVERY_K) + t / max(1, settings.SUMMARY_EVERY_TURNS),
        "supervisor": t if settings.SUPERVISOR_MODE == "full" else 0.0,
    }
    out: dict[str, float] = {}
    for role, rpm in per_role.items():
        model = settings.model_for(role)
        if rpm > 0 and model:
            out[model] = out.get(model, 0.0) + rpm
    return out


def build_readiness(
    settings,
    quota,
    *,
    mode: str,
    target_minutes: int,
    rates: Rates,
    tts_primary: str,
    tts_fallbacks: list[str],
    tts_credits_left: Optional[float],
    tts_note: str = "",
) -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    known_minutes: list[float] = []

    # Otak AI: model dengan menit tersisa paling sedikit yang menentukan.
    llm_rows = []
    unknown: list[str] = []
    for model, rpm in llm_requests_per_min(settings, rates).items():
        if model.startswith(COMPAT_PREFIX):
            llm_rows.append({"model": model, "paid": True, "requests_per_min": round(rpm, 2), "minutes_left": None, "percent_left": None, "remaining": None})
            continue  # berbayar per panggilan: tanpa kuota harian
        st = quota.status(model)
        minutes = None if st["remaining"] is None else st["remaining"] / rpm
        llm_rows.append({**st, "requests_per_min": round(rpm, 2), "minutes_left": None if minutes is None else int(minutes)})
    limited = [r for r in llm_rows if not r.get("paid")]
    worst = min((r for r in limited if r["minutes_left"] is not None), key=lambda r: r["minutes_left"], default=None)
    pick = worst or (limited[0] if limited else None)
    llm_unlimited = not limited  # hanya model berbayar (compat:) atau tanpa model: tidak dibatasi kuota harian
    services.append({
        "kind": "llm",
        "label": "Otak AI",
        "percent_left": pick["percent_left"] if pick else None,
        "minutes_left": pick["minutes_left"] if pick else None,
        "unlimited": llm_unlimited,
        "paid": bool(llm_rows) and llm_unlimited,
        "detail": llm_rows,
    })
    if worst is not None:
        known_minutes.append(worst["minutes_left"])
    if limited and any(r["minutes_left"] is None for r in limited):
        unknown.append("Otak AI")

    # Suara AI
    if tts_primary in ("edge", "gtts", "mock"):
        tts = {"kind": "tts", "label": "Suara AI", "percent_left": None, "minutes_left": None, "unlimited": True, "detail": tts_primary}
    else:
        minutes = None if tts_credits_left is None else int(tts_credits_left / max(1e-6, rates.tts_credits_per_min))
        tts = {"kind": "tts", "label": "Suara AI", "percent_left": None, "minutes_left": minutes, "unlimited": False,
               "credits_left": tts_credits_left, "credits_per_min": round(rates.tts_credits_per_min, 1), "detail": tts_note or tts_primary}
        if minutes is not None:
            known_minutes.append(minutes)
        else:
            unknown.append("Suara AI")
    services.append(tts)

    if mode == "A":
        services.append({"kind": "stt", "label": "Pendengar suara penyiar", "percent_left": None, "minutes_left": None, "unlimited": True,
                         "detail": "Web Speech di browser prompter"})

    fallbacks = []
    if settings.GEMINI_MODEL_PERSONA_FALLBACK:
        fallbacks.append("llm")
    if tts_fallbacks:
        fallbacks.append("tts")
    return {
        "services": services,
        # minutes_safe dari layanan yang diketahui saja; `unknown` menyebut layanan berkuota yang sisanya belum bisa dibaca.
        # UI: "Tidak terbatas" hanya bila semua layanan tanpa batas (unknown kosong dan minutes_safe None).
        "minutes_safe": min(known_minutes) if known_minutes else None,
        "unknown": unknown,
        "target_minutes": target_minutes,
        "fallbacks": fallbacks,
        "rates_source": rates.source,
        "ai_turns_per_min": round(rates.ai_turns_per_min, 2),
        "estimated": True,
    }
