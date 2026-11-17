"""Kartu persona dari database (lihat app/content.py)."""

from __future__ import annotations

from app.content import content
from app.schemas import PersonaCard


def load_personas() -> dict[str, PersonaCard]:
    return content.personas()
