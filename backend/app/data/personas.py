"""Memuat kartu persona dari app/data/persona/*.json."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.schemas import PersonaCard

PERSONA_DIR = Path(__file__).resolve().parent / "persona"


@lru_cache
def load_personas() -> dict[str, PersonaCard]:
    return {
        p.stem: PersonaCard.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(PERSONA_DIR.glob("*.json"))
    }
