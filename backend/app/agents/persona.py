"""Persona Engine (FR-3): satu giliran ucapan Raka atau Salsa.

Dipakai ulang dari profil `natural_v2` repo lama (conversation/engine.py):
sampler dialog act, panjang giliran bervariasi, catchphrase sesekali dengan
cooldown, dan penjaga anti-repetisi (pembuka/penutup dan trigram) yang memicu
satu kali buat ulang. Yang baru: konteks blocker (segmen, topik aktif, poin
yang belum tercakup), arahan Showrunner, dan memori koreksi Supervisor.
"""

from __future__ import annotations

from app.tuning import tuning

import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.agents.hits_style import style_extras
from app.llm import LLMClient, register_mock
from app.content import content
from app.prompts import load_prompt
from app.schemas import Blocker, BlockerTopic, CorrectionMemory, Emotion, PersonaCard, PersonaOutput, Segment

_INTERROGATIVE_PATTERNS = (
    r"\?",
    r"\b(siapa|apa|kenapa|kok|gimana|bagaimana|kapan|di mana|dimana|ke mana|kemana|yang mana|mana|berapa|ngapain)\b",
    r"\b(setuju|bener|benar|serius|pernah|wajar|cocok|liat|bisa)\s*(gak|nggak|ga|enggak|kah)\b",
    r"\b(lu|lo|kamu)\s+pilih\s+mana\b",
    r"\b(pilih|milih)\s+mana\b",
)


def detect_interrogative(text: str) -> bool:
    txt = (text or "").strip().lower()
    if not txt:
        return False
    return any(re.search(p, txt) for p in _INTERROGATIVE_PATTERNS)


@dataclass
class HistoryEntry:
    persona_id: str
    name: str
    text: str


@dataclass
class TurnContext:
    """Konteks satu giliran yang disusun Show Engine (FR-2)."""

    blocker: Blocker
    segment: Segment
    topic: Optional[BlockerTopic]
    uncovered_points: list[str]
    history: list[HistoryEntry]
    partner_name: str
    turn_in_segment: int
    steer_hint: str = ""
    transition_to: Optional[BlockerTopic] = None  # giliran ini mengantar ke topik berikutnya
    to_closing: bool = False  # giliran ini mengantar ke penutup
    closing_final: bool = False  # giliran terakhir siaran
    topics_done: list[str] = field(default_factory=list)
    mode: str = "B"  # A: manusia + 1 AI, B: AI + AI
    human_name: str = ""
    others: list[tuple[str, str]] = field(default_factory=list)  # peserta lain: (nama, peran)
    summary: str = ""  # ringkasan obrolan di luar jendela riwayat
    pilot_condition: str = "A"
    force_no_dialog_act: bool = False
    # Batas waktu per poin (R4): kosong/0 bila timer mati atau segmen bukan topik
    point: str = ""  # poin yang sedang dibahas (satu obrolan)
    point_no: int = 0
    point_total: int = 0
    max_words: int = 0  # anggaran kata giliran ini dari sisa waktu poin
    close_point: bool = False  # giliran ini menutup poin secara natural
    next_point: str = ""  # poin berikutnya dalam topik yang sama (kosong bila poin terakhir)
    # Mode A (PRD v2.7): kode halus satu kali per topik saat topik lewat waktu; isinya topik berikutnya atau "penutup".
    nudge_to: str = ""


@dataclass
class PersonaResult:
    output: PersonaOutput
    raw: str
    model: str
    latency_ms: int
    dialog_act: Optional[str]
    catchphrase: Optional[str]
    guard_regenerations: int = 0
    prompt: str = ""


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _trigrams(text: str) -> set[str]:
    toks = _tokens(text)
    return {" ".join(toks[i : i + 3]) for i in range(len(toks) - 2)}


def repetition_triggered(text: str, history: list[HistoryEntry]) -> bool:
    """Pembuka/penutup tiga kata sama dengan giliran baru-baru ini, atau trigram terlalu sering muncul."""
    toks = _tokens(text)
    if len(toks) < 3:
        return False
    opener, closer = " ".join(toks[:3]), " ".join(toks[-3:])
    for entry in history[-tuning.ANTI_REPETITION_WINDOW:]:
        e = _tokens(entry.text)
        if len(e) >= 3 and (opener == " ".join(e[:3]) or closer == " ".join(e[-3:])):
            return True
    counts: dict[str, int] = {}
    for entry in history[-tuning.TRIGRAM_HISTORY_WINDOW:]:
        for tg in _trigrams(entry.text):
            counts[tg] = counts.get(tg, 0) + 1
    return any(counts.get(tg, 0) + 1 >= tuning.TRIGRAM_REPEAT_LIMIT for tg in _trigrams(text))


def anti_repetition_guidance(history: list[HistoryEntry]) -> str:
    recent = history[-tuning.ANTI_REPETITION_WINDOW:]
    openers, closers = [], []
    for entry in recent:
        toks = _tokens(entry.text)
        if len(toks) >= 3:
            openers.append(" ".join(toks[:3]))
            closers.append(" ".join(toks[-3:]))
    forbidden = [x for x in set(openers) if openers.count(x) >= 2] + [x for x in set(closers) if closers.count(x) >= 2]
    if not forbidden:
        return ""
    return content.text("turn.anti_repetition", phrases=", ".join(f'"{f}"' for f in forbidden[:6]))


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) or content.snippet("turn.no_items")


class PersonaAgent:
    def __init__(self, llm: LLMClient, model: str, rng: random.Random, temperature: float = 0.9):
        self._llm, self._model, self._rng = llm, model, rng
        self._temperature = temperature
        self.prompt = load_prompt("persona")
        self._last_act: Optional[str] = None
        self._catchphrase_turn: dict[str, int] = {}
        self._turn = 0

    def system_prompt(self, persona: PersonaCard) -> str:
        return self.prompt.render(
            name=persona.name,
            gender="pria" if persona.gender == "male" else "wanita",
            speaking_style=persona.speaking_style,
            background_facts=_bullets(persona.background_facts),
            opinions=_bullets(persona.opinions),
            topic_limits=_bullets(persona.topic_limits),
            do_not=_bullets(persona.do_not),
        )

    # ── Sampler (natural_v2) ─────────────────────────────────────────────────

    def _sample_act(self, ctx: TurnContext) -> Optional[str]:
        if ctx.segment != "topic" or ctx.transition_to or ctx.to_closing or ctx.close_point or ctx.force_no_dialog_act:
            return None
        choices = [a for a in content.snippets_with_prefix("dialog_act.") if a != self._last_act]
        if ctx.mode == "A":
            choices = [a for a in choices if a != "audience"]  # penyiar manusia yang memandu penonton
        act = self._rng.choice(choices)
        self._last_act = act
        return act

    def _sample_length(self, ctx: TurnContext) -> str:
        length = self._base_length(ctx)
        if ctx.max_words:
            length += content.text("length.max_words", max_words=ctx.max_words)
        return length

    def _base_length(self, ctx: TurnContext) -> str:
        if ctx.close_point:
            return content.snippet("length.close_point")
        if ctx.mode == "A":
            return content.snippet("length.mode_a")
        roll = self._rng.random()
        if roll < 0.4:
            return content.snippet("length.short")
        if roll < 0.8:
            return content.snippet("length.medium")
        return content.snippet("length.long")

    def _sample_catchphrase(self, persona: PersonaCard) -> Optional[str]:
        if not persona.catchphrases:
            return None
        last = self._catchphrase_turn.get(persona.id, -tuning.CATCHPHRASE_COOLDOWN_TURNS)
        if self._turn - last < tuning.CATCHPHRASE_COOLDOWN_TURNS or self._rng.random() >= tuning.CATCHPHRASE_PROBABILITY:
            return None
        self._catchphrase_turn[persona.id] = self._turn
        return self._rng.choice(persona.catchphrases)

    # ── Prompt giliran ───────────────────────────────────────────────────────

    def turn_prompt(
        self,
        persona: PersonaCard,
        ctx: TurnContext,
        act: Optional[str],
        length: str,
        catchphrase: Optional[str],
        correction: Optional[CorrectionMemory],
    ) -> str:
        t = content.text
        b = ctx.blocker
        parts = [
            t("turn.tema", tema=b.tema, variant=b.variant_label),
            t("turn.rundown", rundown=" → ".join(["Opening", *[x.judul for x in b.topics], "Closing"])),
        ]
        if ctx.topics_done:
            parts.append(t("turn.topics_done", topics="; ".join(ctx.topics_done)))

        if ctx.segment == "opening":
            parts.append(t("turn.opening", hook=b.opening.hook, points=_bullets(b.opening.poin)))
            if ctx.turn_in_segment == 0:
                parts.append(content.snippet("opening_ai_disclosure"))
        elif ctx.segment == "topic" and ctx.topic:
            tp = ctx.topic
            parts.append(t("turn.topic_header", judul=tp.judul, sudut=tp.sudut_pandang))
            if ctx.point:
                parts.append(t("turn.point_focus", no=ctx.point_no, total=ctx.point_total, point=ctx.point))
            else:
                parts.append(t("turn.uncovered", points=_bullets(ctx.uncovered_points)))
            parts.append(t("turn.audience_question", pertanyaan=tp.pertanyaan_penonton))
        else:
            parts.append(t("turn.closing", rangkuman=b.closing.rangkuman, ajakan=b.closing.ajakan))

        if ctx.others:
            parts.append(t("turn.others", others="; ".join(f"{name} ({role})" for name, role in ctx.others)))
        if ctx.mode == "A":
            parts.append(t("turn.human_host", human=ctx.human_name))
        elif not ctx.others:
            parts.append(t("turn.partner", partner=ctx.partner_name))

        if ctx.pilot_condition == "B":
            parts.append(content.snippet("turn.pilot_b"))

        if ctx.summary:
            parts.append(t("turn.summary", summary=ctx.summary))
        if ctx.history:
            parts.append(t("turn.history", history="\n".join(f"{h.name}: {h.text}" for h in ctx.history[-tuning.HISTORY_TURNS:])))

        who = ctx.human_name or ctx.partner_name
        instructions: list[str] = []
        if ctx.transition_to is not None:
            instructions.append(t("turn.transition", next=ctx.transition_to.judul, bridge=ctx.topic.transisi if ctx.topic else ""))
        elif ctx.to_closing:
            instructions.append(content.snippet("turn.to_closing"))
        elif ctx.close_point and ctx.next_point:
            instructions.append(t("turn.close_point", next_point=ctx.next_point))
        elif ctx.closing_final:
            instructions.append(content.snippet("turn.closing_final"))
        if ctx.nudge_to:
            instructions.append(t("turn.nudge", who=who, nudge_to=ctx.nudge_to))
        if ctx.steer_hint and ctx.segment == "topic" and ctx.transition_to is None:
            instructions.append(t("turn.steer", hint=ctx.steer_hint))
        if act:
            instructions.append(t("turn.act", act=content.snippet("dialog_act." + act)))
        instructions += style_extras(ctx.turn_in_segment, closing=ctx.segment == "closing")
        instructions.append(t("turn.length", length=length))
        if anti := anti_repetition_guidance(ctx.history):
            instructions.append(anti)
        if catchphrase:
            instructions.append(t("turn.catchphrase", phrase=catchphrase))
        if correction:
            fix = [correction.persona_reminder, *correction.facts_to_enforce]
            instructions.append(t("turn.correction", items=_bullets([f for f in fix if f])))
        parts.append("\n".join(instructions))
        parts.append(t("turn.your_turn", name=persona.name))
        return "\n\n".join(parts)

    async def generate(self, persona: PersonaCard, ctx: TurnContext, correction: Optional[CorrectionMemory] = None) -> PersonaResult:
        self._turn += 1
        act = self._sample_act(ctx)
        catchphrase = self._sample_catchphrase(persona) if ctx.segment == "topic" else None
        prompt = self.turn_prompt(persona, ctx, act, self._sample_length(ctx), catchphrase, correction)
        system = self.system_prompt(persona)

        start = time.perf_counter()
        guard = 0
        while True:
            resp = await self._llm.generate(
                prompt, model=self._model, system_instruction=system, response_schema=PersonaOutput, temperature=self._temperature
            )
            try:
                output = PersonaOutput.model_validate(resp.parsed)
            except Exception:
                output = PersonaOutput(text=resp.raw.strip() or "Hmm.", emotion=Emotion.NEUTRAL)
            if guard >= 1 or not repetition_triggered(output.text, ctx.history):
                break
            guard += 1
        return PersonaResult(
            output=output,
            raw=resp.raw,
            model=resp.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            dialog_act=act,
            catchphrase=catchphrase,
            guard_regenerations=guard,
            prompt=prompt,
        )


# ── Mock ─────────────────────────────────────────────────────────────────────

_MOCK_LINES = [
    "Wah, iya juga ya, gue baru kepikiran soal itu.",
    "Eh tapi menurut gue nggak selalu gitu sih, tergantung orangnya.",
    "Hmm, lu pernah ngalamin sendiri nggak?",
    "Haha, gue jadi inget pas zaman awal kuliah dulu.",
    "Sobat Hits, kalian tim yang mana nih? Pikirin dulu jawabannya ya.",
    "Oke, bener juga, jatuhnya jadi kebiasaan ya.",
    "Serius? Gue malah kebalikannya, santai aja.",
    "Nah itu dia yang bikin seru dibahas.",
]


def _mock_persona(prompt: str, n: int) -> dict:
    segment = re.search(r"^SEGMEN: (\w+)", prompt, flags=re.MULTILINE)
    seg = segment.group(1) if segment else "Topik"
    if "giliran terakhir siaran" in prompt:
        text = "Oke Sobat Hits, makasih udah nemenin kita, sampai ketemu lagi!"
    elif "mengantar ke poin berikutnya" in prompt:
        text = "Oke, segitu dulu soal ini, kita lanjut ke bahasan berikutnya ya."
    elif "mengantar ke topik berikutnya" in prompt:
        text = "Oke, dari situ kita geser ke obrolan berikutnya ya."
    elif seg == "Opening":
        text = "Halo Sobat Hits! Kita berdua penyiar AI HITS, yuk ngobrol santai bareng." if n % 2 else "Hai semuanya, seru nih tema kita hari ini."
    else:
        text = f"{_MOCK_LINES[n % len(_MOCK_LINES)]} Bagian ke-{n}."
    return {"text": text, "emotion": ["happy", "neutral", "excited", "thoughtful"][n % 4]}


register_mock(PersonaOutput, _mock_persona)
