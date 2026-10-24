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
    id: str = ""  # diisi server (t1p1, ...); poin baru dari editor boleh tanpa id
    text: str
    perlu_cek: bool = False


class BlockerTopic(BaseModel):
    id: str = ""
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


# ── Show Engine (Tahap 2: FR-2, FR-4, FR-5, FR-12) ───────────────────────────

ShowMode = Literal["A", "B"]
Segment = Literal["opening", "topic", "closing"]
SupervisorMode = Literal["off", "rules", "full"]
ShowrunnerPolicy = Literal["llm", "fixed_turns", "coverage_only"]


class ShowState(str, Enum):
    IDLE = "idle"
    LIVE = "live"
    PAUSED = "paused"
    ENDED = "ended"


class StartShowRequest(BaseModel):
    blocker_id: str
    mode: ShowMode = "B"
    ai_persona: Optional[str] = None  # mode A: raka | salsa
    human_name: str = ""  # mode A: nama tampilan penyiar manusia (§15.2 #2)
    seed: Optional[int] = None


class PTTTurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    stt_ms: int = 0  # lepas tombol → transkrip final, diukur di browser


# Supervisor (FR-5)

CheckResult = Literal["ok", "violation"]


class SupervisorJudgement(BaseModel):
    """Keluaran LLM Supervisor (mode full)."""

    persona: CheckResult
    blocker: CheckResult
    safety: CheckResult
    evidence: str
    correction: str  # arahan singkat untuk regenerasi; kosong bila semua ok
    claims: list[str]  # klaim faktual baru tentang diri persona di ucapan ini


class SupervisorVerdict(BaseModel):
    mode: SupervisorMode
    action: Literal["forward", "regenerate", "fallback"] = "forward"
    checks: dict[str, str] = Field(default_factory=lambda: {"persona": "ok", "blocker": "ok", "safety": "ok"})
    rule_hits: list[str] = Field(default_factory=list)
    evidence: str = ""
    regenerations: int = 0
    llm_latency_ms: int = 0
    timed_out: bool = False


# Showrunner (FR-4, §9.3)

ShowrunnerDecisionType = Literal["continue", "steer", "transition", "close"]


class ShowrunnerJudgement(BaseModel):
    """Keluaran LLM Showrunner."""

    points_covered: list[str]
    saturation: float
    decision: ShowrunnerDecisionType
    steer_hint: str
    new_angle: str  # sudut baru di luar poin yang masih nyambung ke topik, untuk sisa jatah waktu
    next_speaker: str  # raka | salsa | "" (bebas)
    reason: str


class ShowrunnerDecision(BaseModel):
    turn: int
    topic_id: str
    points_covered: list[str] = Field(default_factory=list)
    saturation: float = 0.0
    decision: ShowrunnerDecisionType = "continue"
    steer_hint: str = ""
    next_speaker: Optional[str] = None
    reason: str = ""
    policy: Literal["llm", "fixed_turns", "coverage_only", "budget"] = "llm"  # budget = cadangan berbasis jatah waktu
    forced: bool = False
    latency_ms: int = 0


# Log giliran (§9.4)


class TurnRecord(BaseModel):
    session_id: str
    mode: ShowMode
    segment: Segment
    topic_id: Optional[str]
    turn: int
    persona: str
    raw_text: str
    final_text: str
    emotion: Emotion
    dialog_act: Optional[str] = None
    supervisor: SupervisorVerdict
    latency_ms: LatencyMs = Field(default_factory=LatencyMs)
    models: dict[str, str] = Field(default_factory=dict)
    tts_provider: str = ""
    tts_fallback_reason: str = ""
    audio_url: Optional[str] = None
    duration_s: float = 0.0
    credit_cost: int = 0
    filler: Optional[str] = None
    seed: Optional[int] = None
