"""Daftar suara terkurasi (`app/data/voices.json`) yang bisa dipilih operator sebelum live (FR-6)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

VOICES_FILE = Path(__file__).resolve().parents[1] / "data" / "voices.json"


class VoiceOption(BaseModel):
    id: str  # voice id provider
    provider: Literal["elevenlabs", "edge"]
    name: str
    gender: Literal["male", "female"]
    notes: str = ""


@lru_cache(maxsize=1)
def _load() -> tuple[VoiceOption, ...]:
    raw = json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    return tuple(VoiceOption.model_validate(v) for v in raw["voices"])


def load_voice_catalog() -> list[VoiceOption]:
    return list(_load())


def find_voice(voice_id: str) -> VoiceOption | None:
    return next((v for v in _load() if v.id == voice_id), None)
