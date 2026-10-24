"""Model Pydantic untuk struktur data PRD §9.

Skema ini acuan tunggal untuk file di data/, respons API, dan log JSONL.
Skema Showrunner, Supervisor, dan log giliran ditambahkan di Tahap 2.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Emotion(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    SAD = "sad"
    SURPRISED = "surprised"
    THOUGHTFUL = "thoughtful"
    EMPATHETIC = "empathetic"


# ── Persona (§9.2) ───────────────────────────────────────────────────────────


class PersonaCard(BaseModel):
    id: str
    name: str
    gender: Literal["male", "female"]
    voices: dict[str, str] = Field(default_factory=dict)  # provider -> voice id
    speaking_style: str = ""
    catchphrases: list[str] = Field(default_factory=list)
    topic_limits: list[str] = Field(default_factory=list)
    background_facts: list[str] = Field(default_factory=list)
    do_not: list[str] = Field(default_factory=list)
    opinions: list[str] = Field(default_factory=list)
    clips: str = ""
    filler_bank: str = ""


class PersonaOutput(BaseModel):
    text: str
    emotion: Emotion


class CorrectionMemory(BaseModel):
    persona_reminder: str = ""
    conversation_summary: str = ""
    facts_to_enforce: list[str] = Field(default_factory=list)


class LedgerEntry(BaseModel):
    persona: str
    claim: str
    turn: int


class LatencyMs(BaseModel):
    stt: int = 0
    persona: int = 0
    supervisor: int = 0
    tts: int = 0
    avatar_render: int = 0
    gap_before_play: int = 0


# ── Blocker (§9.1, FR-1) ─────────────────────────────────────────────────────


class BlockerPoint(BaseModel):
    id: str
    text: str
    perlu_cek: bool = False


class BlockerTopic(BaseModel):
    id: str
    judul: str
    sudut_pandang: str
    poin: list[BlockerPoint]
    pertanyaan_penonton: str
    transisi: str


class BlockerOpening(BaseModel):
    hook: str
    poin: list[str]


class BlockerClosing(BaseModel):
    rangkuman: str
    ajakan: str


class Blocker(BaseModel):
    id: str
    tema: str
    catatan: str = ""
    versi: int = 1
    locked: bool = False
    created_at: str
    variant_label: str
    opening: BlockerOpening
    topics: list[BlockerTopic]
    closing: BlockerClosing
    parent_id: Optional[str] = None  # blocker terkunci yang menjadi dasar versi ini
    generation_id: Optional[str] = None  # varian dari satu permintaan generate yang sama


# Bentuk keluaran LLM: tanpa id/versi (diisi server), supaya skema structured
# output sederhana dan model tidak mengarang id.


class DraftPoint(BaseModel):
    text: str
    perlu_cek: bool


class DraftTopic(BaseModel):
    judul: str
    sudut_pandang: str
    poin: list[DraftPoint]
    pertanyaan_penonton: str
    transisi: str


class DraftVariant(BaseModel):
    variant_label: str
    opening: BlockerOpening
    topics: list[DraftTopic]
    closing: BlockerClosing


class DraftVariants(BaseModel):
    variants: list[DraftVariant]


class GenerateBlockerRequest(BaseModel):
    tema: str = Field(min_length=1, max_length=60)
    catatan: str = Field(default="", max_length=500)
    jumlah_topik: int = Field(default=3, ge=1, le=3)
    jumlah_varian: int = Field(default=3, ge=2, le=3)
