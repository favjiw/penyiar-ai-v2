"""Persona Engine (FR-3): satu giliran ucapan Raka atau Salsa.

Dipakai ulang dari profil `natural_v2` repo lama (conversation/engine.py):
sampler dialog act, panjang giliran bervariasi, catchphrase sesekali dengan
cooldown, dan penjaga anti-repetisi (pembuka/penutup dan trigram) yang memicu
satu kali buat ulang. Yang baru: konteks blocker (segmen, topik aktif, poin
yang belum tercakup), arahan Showrunner, dan memori koreksi Supervisor.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.agents.hits_style import style_extras
from app.llm import LLMClient, register_mock
from app.prompts import load_prompt
from app.schemas import Blocker, BlockerTopic, CorrectionMemory, Emotion, PersonaCard, PersonaOutput, Segment

CATCHPHRASE_PROBABILITY = 1.0 / 6.0
CATCHPHRASE_COOLDOWN_TURNS = 6
HISTORY_TURNS = 12
ANTI_REPETITION_WINDOW = 6
TRIGRAM_REPEAT_LIMIT = 3
TRIGRAM_HISTORY_WINDOW = 10

DIALOG_ACT_HINTS = {
    "anecdote": "ceritakan pengalaman atau anekdot spesifik milikmu yang nyambung ke poin ini",
    "opinion_diff": "sampaikan pendapat yang agak beda dari lawan bicara beserta alasannya",
    "new_angle": "tambahkan satu sudut atau detail baru ke obrolan",
    "personal_question": "tanyakan hal personal yang ringan ke lawan bicara",
    "tease": "goda lawan bicara secara ringan dan ramah",
    "short_react": "beri reaksi singkat satu kalimat",
    "audience": "lempar pertanyaan ke penonton supaya mereka nulis di komentar",
}
OPENING_AI_DISCLOSURE = "Di pembukaan ini sebutkan dengan santai bahwa kalian berdua penyiar AI HITS."


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
    mode: str = "B"
    human_name: str = ""


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
    for entry in history[-ANTI_REPETITION_WINDOW:]:
        e = _tokens(entry.text)
        if len(e) >= 3 and (opener == " ".join(e[:3]) or closer == " ".join(e[-3:])):
            return True
    counts: dict[str, int] = {}
    for entry in history[-TRIGRAM_HISTORY_WINDOW:]:
        for tg in _trigrams(entry.text):
            counts[tg] = counts.get(tg, 0) + 1
    return any(counts.get(tg, 0) + 1 >= TRIGRAM_REPEAT_LIMIT for tg in _trigrams(text))


def anti_repetition_guidance(history: list[HistoryEntry]) -> str:
    recent = history[-ANTI_REPETITION_WINDOW:]
    openers, closers = [], []
    for entry in recent:
        toks = _tokens(entry.text)
        if len(toks) >= 3:
            openers.append(" ".join(toks[:3]))
            closers.append(" ".join(toks[-3:]))
    forbidden = [x for x in set(openers) if openers.count(x) >= 2] + [x for x in set(closers) if closers.count(x) >= 2]
    if not forbidden:
        return ""
    return "Jangan membuka atau menutup giliran dengan: " + ", ".join(f'"{f}"' for f in forbidden[:6]) + "."


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) or "- (tidak ada)"


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
        if ctx.segment != "topic" or ctx.transition_to or ctx.to_closing:
            return None
        choices = [a for a in DIALOG_ACT_HINTS if a != self._last_act]
        if ctx.mode == "A":
            choices = [a for a in choices if a != "audience"]  # penyiar manusia yang memandu penonton
        act = self._rng.choice(choices)
        self._last_act = act
        return act

    def _sample_length(self, ctx: TurnContext) -> str:
        if ctx.mode == "A":
            return "1 sampai 3 kalimat pendek; beri ruang penyiar manusia memandu"
        roll = self._rng.random()
        if roll < 0.4:
            return "satu kalimat pendek (sekitar 8 sampai 15 kata)"
        if roll < 0.8:
            return "sedang (sekitar 20 sampai 35 kata)"
        return "panjang (maksimal sekitar 60 kata)"

    def _sample_catchphrase(self, persona: PersonaCard) -> Optional[str]:
        if not persona.catchphrases:
            return None
        last = self._catchphrase_turn.get(persona.id, -CATCHPHRASE_COOLDOWN_TURNS)
        if self._turn - last < CATCHPHRASE_COOLDOWN_TURNS or self._rng.random() >= CATCHPHRASE_PROBABILITY:
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
        b = ctx.blocker
        parts = [f"TEMA SIARAN: {b.tema} ({b.variant_label})", "Rundown: " + " → ".join(["Opening", *[t.judul for t in b.topics], "Closing"])]
        if ctx.topics_done:
            parts.append("Topik yang sudah lewat (jangan dibahas lagi): " + "; ".join(ctx.topics_done))

        if ctx.segment == "opening":
            parts.append(f"SEGMEN: Opening. Hook: {b.opening.hook}\nYang dilakukan di pembukaan:\n{_bullets(b.opening.poin)}")
            if ctx.turn_in_segment == 0:
                parts.append(OPENING_AI_DISCLOSURE)
        elif ctx.segment == "topic" and ctx.topic:
            t = ctx.topic
            parts.append(f"SEGMEN: Topik \"{t.judul}\" (sudut pandang: {t.sudut_pandang})")
            parts.append("Poin yang belum dibahas:\n" + _bullets(ctx.uncovered_points))
            parts.append(f"Pertanyaan untuk penonton (lempar sesekali, jangan tiap giliran): {t.pertanyaan_penonton}")
        else:
            parts.append(f"SEGMEN: Closing. Rangkuman: {b.closing.rangkuman}. Ajakan ke penonton: {b.closing.ajakan}")

        if ctx.mode == "A":
            parts.append(f"Lawan bicaramu penyiar manusia bernama {ctx.human_name}. Jawab singkat, beri ruang dia memandu.")
        else:
            parts.append(f"Lawan bicaramu: {ctx.partner_name}.")

        if ctx.history:
            parts.append("Obrolan terakhir:\n" + "\n".join(f"{h.name}: {h.text}" for h in ctx.history[-HISTORY_TURNS:]))

        instructions: list[str] = []
        if ctx.transition_to is not None:
            instructions.append(
                f"Giliran ini menutup topik sekarang dan mengantar ke topik berikutnya: \"{ctx.transition_to.judul}\". "
                f"Bahan jembatan (jangan dibaca mentah, pakai kata-katamu): {ctx.topic.transisi if ctx.topic else ''}"
            )
        elif ctx.to_closing:
            instructions.append("Giliran ini menutup topik terakhir dan mengantar ke penutup siaran.")
        elif ctx.closing_final:
            instructions.append("Ini giliran terakhir siaran: tutup dengan rapi, pamit ke penonton, jangan buka topik baru.")
        if ctx.steer_hint and ctx.segment == "topic" and ctx.transition_to is None:
            instructions.append(f"Arahan produser: {ctx.steer_hint}")
        if act:
            instructions.append(f"Tugas giliran ini: {DIALOG_ACT_HINTS[act]}.")
        instructions += style_extras(ctx.turn_in_segment, closing=ctx.segment == "closing")
        instructions.append(f"Panjang giliran: {length}.")
        if anti := anti_repetition_guidance(ctx.history):
            instructions.append(anti)
        if catchphrase:
            instructions.append(f'Boleh memakai catchphrase ini kali ini saja: "{catchphrase}"')
        if correction:
            fix = [correction.persona_reminder, *correction.facts_to_enforce]
            instructions.append("KOREKSI dari produser untuk giliran ini (wajib dipatuhi):\n" + _bullets([f for f in fix if f]))
        parts.append("\n".join(instructions))
        parts.append(f"Sekarang giliran {persona.name} bicara. Balas dalam JSON.")
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
    "Sobat Hits, kalian tim yang mana nih? Tulis di komentar ya.",
    "Oke, bener juga, jatuhnya jadi kebiasaan ya.",
    "Serius? Gue malah kebalikannya, santai aja.",
    "Nah itu dia yang bikin seru dibahas.",
]


def _mock_persona(prompt: str, n: int) -> dict:
    segment = re.search(r"^SEGMEN: (\w+)", prompt, flags=re.MULTILINE)
    seg = segment.group(1) if segment else "Topik"
    if "giliran terakhir siaran" in prompt:
        text = "Oke Sobat Hits, makasih udah nemenin kita, sampai ketemu lagi!"
    elif "mengantar ke topik berikutnya" in prompt:
        text = "Oke, dari situ kita geser ke obrolan berikutnya ya."
    elif seg == "Opening":
        text = "Halo Sobat Hits! Kita berdua penyiar AI HITS, yuk ngobrol santai bareng." if n % 2 else "Hai semuanya, seru nih tema kita hari ini."
    else:
        text = f"{_MOCK_LINES[n % len(_MOCK_LINES)]} Bagian ke-{n}."
    return {"text": text, "emotion": ["happy", "neutral", "excited", "thoughtful"][n % 4]}


register_mock(PersonaOutput, _mock_persona)
