"""Tahap 0: hitung kebutuhan request Gemini untuk sesi mode B (PRD §13).

Isi batas free tier hasil pengecekan AI Studio di quota.md, lalu jalankan:
    python tahap0/quota_calc.py --turn-audio-s 8 --minutes 20 60
    python tahap0/quota_calc.py --rpm-persona 10 --rpd-persona 250 ...

Asumsi per giliran AI (mode B):
  persona: 1 + rasio regenerasi Supervisor
  supervisor: rasio giliran yang lolos aturan cepat dan perlu LLM (mode full)
  showrunner: 1 per SHOWRUNNER_EVERY_K giliran
  tts: 1 per giliran (mode B tidak dipecah per kalimat)
"""

from __future__ import annotations

import argparse
import math

ROLES = ["persona", "supervisor", "showrunner", "tts"]


def per_turn(args) -> dict[str, float]:
    return {
        "persona": 1 + args.regen_rate,
        "supervisor": args.supervisor_llm_rate * (1 + args.regen_rate),
        "showrunner": 1 / args.every_k,
        "tts": 1.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, nargs="+", default=[20, 60])
    ap.add_argument("--turn-audio-s", type=float, default=8.0, help="rata-rata durasi audio satu giliran")
    ap.add_argument("--gap-s", type=float, default=1.0, help="jeda antargiliran")
    ap.add_argument("--every-k", type=int, default=3)
    ap.add_argument("--regen-rate", type=float, default=0.1)
    ap.add_argument("--supervisor-llm-rate", type=float, default=1.0)
    for role in ROLES:
        ap.add_argument(f"--rpm-{role}", type=float, default=None)
        ap.add_argument(f"--rpd-{role}", type=float, default=None)
    args = ap.parse_args()

    turns_per_min = 60 / (args.turn_audio_s + args.gap_s)
    need = per_turn(args)
    print(f"Giliran per menit: {turns_per_min:.2f}\n")
    print(f"{'peran':<11}{'req/menit':>10}" + "".join(f"{f'total {m:g}m':>12}" for m in args.minutes) + f"{'RPM':>7}{'RPD':>7}  status")
    for role in ROLES:
        rpm_need = need[role] * turns_per_min
        totals = [math.ceil(rpm_need * m) for m in args.minutes]
        rpm, rpd = getattr(args, f"rpm_{role}"), getattr(args, f"rpd_{role}")
        status = []
        if rpm is not None and rpm_need > rpm:
            status.append(f"RPM kurang ({rpm_need:.1f} > {rpm:g})")
        if rpd is not None:
            for m, t in zip(args.minutes, totals):
                if t > rpd:
                    status.append(f"RPD kurang untuk {m:g}m")
        print(
            f"{role:<11}{rpm_need:>10.2f}" + "".join(f"{t:>12}" for t in totals)
            + f"{'' if rpm is None else f'{rpm:g}':>7}{'' if rpd is None else f'{rpd:g}':>7}  {'; '.join(status) or ('ok' if rpm or rpd else '-')}"
        )


if __name__ == "__main__":
    main()
