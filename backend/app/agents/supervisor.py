"""Supervisor (FR-5): pemeriksa setiap ucapan AI sebelum TTS (AI-in-the-Loop).

Urutan per giliran:
1. aturan cepat (markdown/emoji/keterangan panggung dibersihkan; kata terlarang,
   panjang ekstrem, dan pengulangan persis memicu buat ulang) tanpa LLM;
2. mode `full`: LLM menilai persona, blocker, dan keamanan dengan rubrik;
3. pelanggaran → buat ulang persona sekali dengan CorrectionMemory;
   masih melanggar, gagal, atau waktu habis → kalimat aman dari bank.

Mode `off` meneruskan ucapan apa adanya (baseline eksperimen).
Bila pemeriksaan LLM pertama melewati batas waktu, ucapan yang sudah lolos
aturan cepat tetap diteruskan dan ditandai `timed_out`, supaya siaran tidak
macet; batas waktu di jalur buat ulang berujung ke kalimat aman.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.agents.persona import HistoryEntry, PersonaResult, TurnContext
from app.llm import LLMClient, LLMError, register_mock
from app.prompts import load_prompt
from app.schemas import CorrectionMemory, Emotion, LedgerEntry, PersonaCard, SupervisorJudgement, SupervisorMode, SupervisorVerdict

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "supervisor"
MAX_WORDS = 90
REPEAT_WINDOW = 8

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
# Keterangan panggung dalam kurung dibuang; *penekanan* cukup dibuang bintangnya (lewat _MARKDOWN).
_STAGE = re.compile(r"\((?:[^()]{0,30})\)|\[(?:[^\[\]]{0,30})\]")
_MARKDOWN = re.compile(r"[*#`_~>|]|^\s*[-•]\s+", flags=re.MULTILINE)


@lru_cache
def banned_words() -> tuple[str, ...]:
    lines = (DATA_DIR / "banned_words.txt").read_text(encoding="utf-8").splitlines()
    return tuple(l.strip().lower() for l in lines if l.strip() and not l.startswith("#"))


@lru_cache
def fallback_bank() -> dict[str, dict[str, list[str]]]:
    return json.loads((DATA_DIR / "fallback.json").read_text(encoding="utf-8"))


def sanitize(text: str) -> tuple[str, list[str]]:
    """Buang hal yang tidak bisa diucapkan TTS. Kembalikan (teks bersih, aturan yang terpicu)."""
    hits = []
    if _STAGE.search(text):
        hits.append("stage_direction")
        text = _STAGE.sub(" ", text)
    if _EMOJI.search(text):
        hits.append("emoji")
        text = _EMOJI.sub(" ", text)
    if _MARKDOWN.search(text):
        hits.append("markdown")
        text = _MARKDOWN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(), hits


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def rule_violations(text: str, history: list[HistoryEntry]) -> list[str]:
    """Pelanggaran jelas yang memicu buat ulang tanpa LLM."""
    hits = []
    norm = _normalize(text)
    words = norm.split()
    if not words:
        hits.append("empty")
    if len(words) > MAX_WORDS:
        hits.append("too_long")
    padded = f" {norm} "
    for w in banned_words():
        if f" {_normalize(w)} " in padded:
            hits.append(f"banned:{w}")
    if norm and any(norm == _normalize(h.text) for h in history[-REPEAT_WINDOW:]):
        hits.append("exact_repeat")
    return hits


@dataclass
class Reviewed:
    text: str
    emotion: Emotion
    verdict: SupervisorVerdict
    persona_result: PersonaResult  # hasil persona yang dipakai (asli atau buat ulang)
    judgement_prompt: str = ""


Regenerate = Callable[[CorrectionMemory], Awaitable[PersonaResult]]


class Supervisor:
    def __init__(
        self,
        llm: LLMClient,
        model: str,
        mode: SupervisorMode,
        rng: random.Random,
        max_regen: int = 1,
        timeout_ms: int = 5000,
    ):
        self._llm, self._model, self.mode, self._rng = llm, model, mode, rng
        self._max_regen = max_regen
        self._timeout = timeout_ms / 1000
        self.prompt = load_prompt("supervisor")
        self.ledger: list[LedgerEntry] = []
        self._fallback_used: dict[str, int] = {}
        self.llm_failures = 0
        self.last_llm_error = ""

    # ── LLM (mode full) ──────────────────────────────────────────────────────

    def judgement_prompt(self, persona: PersonaCard, text: str, ctx: TurnContext) -> str:
        claims = [f"- {e.claim} (giliran {e.turn})" for e in self.ledger if e.persona == persona.id]
        topic = f'"{ctx.topic.judul}"' if ctx.topic else ctx.segment
        lines = [
            f"PERSONA: {persona.name}. Lawan bicara: {ctx.partner_name}.",
            "Fakta inti:\n" + "\n".join(f"- {f}" for f in persona.background_facts),
            "Pendapat:\n" + "\n".join(f"- {o}" for o in persona.opinions),
            "Klaim sebelumnya (ledger):\n" + ("\n".join(claims) if claims else "- (belum ada)"),
            f"SEGMEN: {ctx.segment}; topik aktif: {topic}"
            + (f"; giliran ini transisi ke \"{ctx.transition_to.judul}\"" if ctx.transition_to else "")
            + ("; giliran pembukaan (boleh menyebut diri AI)" if ctx.segment == "opening" and ctx.turn_in_segment == 0 else ""),
            "Topik yang sudah lewat: " + ("; ".join(ctx.topics_done) or "(belum ada)"),
            "Obrolan terakhir:\n" + ("\n".join(f"{h.name}: {h.text}" for h in ctx.history[-6:]) or "(belum ada)"),
            f"UCAPAN KANDIDAT ({persona.name}): {text}",
        ]
        return "\n\n".join(lines)

    async def _judge(self, persona: PersonaCard, text: str, ctx: TurnContext) -> tuple[SupervisorJudgement, int, str]:
        prompt = self.judgement_prompt(persona, text, ctx)
        start = time.perf_counter()
        resp = await self._llm.generate(
            prompt, model=self._model, system_instruction=self.prompt.text, response_schema=SupervisorJudgement, temperature=0.0
        )
        latency = int((time.perf_counter() - start) * 1000)
        try:
            return SupervisorJudgement.model_validate(resp.parsed), latency, prompt
        except Exception:
            # Keluaran rusak tidak boleh menahan siaran; dianggap lolos dan dicatat.
            return SupervisorJudgement(persona="ok", blocker="ok", safety="ok", evidence="judgement_unparsed", correction="", claims=[]), latency, prompt

    # ── Alur pemeriksaan ─────────────────────────────────────────────────────

    def fallback(self, persona: PersonaCard, segment: str = "topic") -> str:
        """Kalimat aman sesuai segmen (sapaan di opening, pamit di closing), bergiliran supaya tidak berulang."""
        bank = fallback_bank().get(persona.id, {}).get(segment) or fallback_bank().get(persona.id, {}).get("topic") or ["Oke, lanjut."]
        key = f"{persona.id}:{segment}"
        i = self._fallback_used.get(key, self._rng.randrange(len(bank)))
        self._fallback_used[key] = i + 1
        return bank[i % len(bank)]

    def _record_claims(self, persona: PersonaCard, claims: list[str], turn: int) -> None:
        for claim in claims[:3]:
            if claim.strip():
                self.ledger.append(LedgerEntry(persona=persona.id, claim=claim.strip(), turn=turn))

    async def _check(self, persona: PersonaCard, text: str, ctx: TurnContext) -> tuple[str, list[str], Optional[SupervisorJudgement], int, str]:
        """Bersihkan + aturan + (full) LLM. Kembalikan (teks bersih, aturan, judgement, latensi LLM, prompt)."""
        clean, sanitized = sanitize(text)
        hits = sanitized + rule_violations(clean, ctx.history)
        if self.mode != "full" or len(hits) > len(sanitized):
            return clean, hits, None, 0, ""
        try:
            judgement, latency, prompt = await self._judge(persona, clean, ctx)
        except LLMError as e:
            # Kuota/jaringan: giliran ini cukup diperiksa aturan (PRD §8), siaran jalan terus.
            self.llm_failures += 1
            self.last_llm_error = str(e)[:200]
            return clean, hits, None, 0, ""
        return clean, hits, judgement, latency, prompt

    @staticmethod
    def _violates(hits: list[str], sanitized_only: set[str], judgement: Optional[SupervisorJudgement]) -> bool:
        if any(h not in sanitized_only for h in hits):
            return True
        return bool(judgement and "violation" in (judgement.persona, judgement.blocker, judgement.safety))

    async def review(self, persona: PersonaCard, candidate: PersonaResult, ctx: TurnContext, regenerate: Regenerate, turn: int) -> Reviewed:
        out = candidate.output
        if self.mode == "off":
            return Reviewed(out.text, out.emotion, SupervisorVerdict(mode="off"), candidate)

        cleanup = {"stage_direction", "emoji", "markdown"}
        verdict = SupervisorVerdict(mode=self.mode)
        deadline = time.perf_counter() + self._timeout

        try:
            clean, hits, judgement, latency, prompt = await asyncio.wait_for(self._check(persona, out.text, ctx), self._timeout)
        except asyncio.TimeoutError:
            clean, _ = sanitize(out.text)
            verdict.timed_out = True
            verdict.evidence = "pemeriksaan LLM melewati batas waktu; diteruskan setelah lolos aturan cepat"
            return Reviewed(clean, out.emotion, verdict, candidate)

        verdict.rule_hits = hits
        verdict.llm_latency_ms = latency
        if judgement:
            verdict.checks = {"persona": judgement.persona, "blocker": judgement.blocker, "safety": judgement.safety}
            verdict.evidence = judgement.evidence
        if not self._violates(hits, cleanup, judgement):
            if judgement:
                self._record_claims(persona, judgement.claims, turn)
            return Reviewed(clean, out.emotion, verdict, candidate, prompt)

        # Pelanggaran: buat ulang sekali dengan memori koreksi, lalu periksa lagi.
        correction = CorrectionMemory(
            persona_reminder=(judgement.correction if judgement and judgement.correction else "")
            or f"Tulis ulang tanpa: {', '.join(h for h in hits if h not in cleanup)}.",
            facts_to_enforce=[f"{e.claim}" for e in self.ledger if e.persona == persona.id][-3:],
            conversation_summary=verdict.evidence,
        )
        for _ in range(self._max_regen):
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                verdict.timed_out = True
                break
            verdict.regenerations += 1
            try:
                retry = await asyncio.wait_for(regenerate(correction), remaining)
                clean2, hits2, judgement2, latency2, prompt2 = await asyncio.wait_for(
                    self._check(persona, retry.output.text, ctx), max(0.01, deadline - time.perf_counter())
                )
            except asyncio.TimeoutError:
                verdict.timed_out = True
                break
            verdict.llm_latency_ms += latency2
            if not self._violates(hits2, cleanup, judgement2):
                verdict.action = "regenerate"
                if judgement2:
                    self._record_claims(persona, judgement2.claims, turn)
                return Reviewed(clean2, retry.output.emotion, verdict, retry, prompt2)

        verdict.action = "fallback"
        return Reviewed(self.fallback(persona, ctx.segment), Emotion.NEUTRAL, verdict, candidate, prompt)


# ── Mock ─────────────────────────────────────────────────────────────────────


def _mock_judgement(prompt: str, n: int) -> dict:
    candidate = prompt.rsplit("UCAPAN KANDIDAT", 1)[-1]
    bad = "LANGGAR" in candidate
    return {
        "persona": "ok",
        "blocker": "violation" if bad else "ok",
        "safety": "ok",
        "evidence": "kandidat memuat penanda uji LANGGAR" if bad else "",
        "correction": "jangan ulangi penanda uji" if bad else "",
        "claims": [],
    }


register_mock(SupervisorJudgement, _mock_judgement)
