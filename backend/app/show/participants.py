"""Peserta siaran: daftar, bukan pasangan tetap.

Setiap mode hanya berbeda pada isi daftar dan aturan giliran:

- A: penyiar manusia + 1 AI (pilihan operator);
- B: semua penyiar AI, otomatis.

Kode engine memakai daftar ini, tidak menyebut "raka" atau "salsa" secara langsung, jadi
mode B dengan lebih dari dua AI cukup menambah isi daftar (dan kartu persona).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from app.schemas import PersonaCard

HUMAN_ID = "human"
DEFAULT_AI_IDS = ("raka", "salsa")


@dataclass(frozen=True)
class Participant:
    id: str
    name: str
    kind: Literal["human", "ai"]
    persona: Optional[PersonaCard] = None

    @property
    def is_human(self) -> bool:
        return self.kind == "human"


def build_participants(
    mode: str,
    personas: dict[str, PersonaCard],
    ai_ids: Sequence[str] | None = None,
    human_name: str = "",
) -> list[Participant]:
    """Daftar peserta untuk satu mode. `ai_ids` default: mode A wajib satu id; B memakai semua AI bawaan."""
    if mode not in ("A", "B"):
        raise ValueError(f"Mode tidak dikenal: {mode}")
    ids = list(ai_ids) if ai_ids else list(DEFAULT_AI_IDS)
    unknown = [i for i in ids if i not in personas]
    if unknown:
        raise ValueError(f"Persona AI tidak dikenal: {', '.join(unknown)}")
    if mode == "A" and len(ids) != 1:
        raise ValueError("Mode A butuh tepat satu AI")
    if mode == "B" and len(ids) < 2:
        raise ValueError("Mode B butuh minimal dua AI")
    ais = [Participant(i, personas[i].name, "ai", personas[i]) for i in ids]
    if mode == "B":
        return ais
    return [Participant(HUMAN_ID, human_name.strip() or "Penyiar", "human"), *ais]
