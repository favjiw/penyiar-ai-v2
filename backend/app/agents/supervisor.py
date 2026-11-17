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

from app.tuning import tuning

import asyncio
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.agents.persona import HistoryEntry, PersonaResult, TurnContext
from app.llm import LLMClient, LLMError, LLMQuotaExhausted, register_mock
from app.content import content
from app.prompts import load_prompt
from app.schemas import CorrectionMemory, Emotion, LedgerEntry, PersonaCard, SupervisorJudgement, SupervisorMode, SupervisorVerdict


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
# Keterangan panggung dalam kurung dibuang; *penekanan* cukup dibuang bintangnya (lewat _MARKDOWN).
_STAGE = re.compile(r"\((?:[^()]{0,30})\)|\[(?:[^\[\]]{0,30})\]")
_MARKDOWN = re.compile(r"[*#`_~>|]|^\s*[-•]\s+", flags=re.MULTILINE)


def banned_words() -> tuple[str, ...]:
    return content.banned_words()


def fallback_bank() -> dict[str, dict[str, list[str]]]:
    return content.fallback_bank()


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
    if len(words) > tuning.SUPERVISOR_MAX_WORDS:
        hits.append("too_long")
    padded = f" {norm} "
    for w in banned_words():
        if f" {_normalize(w)} " in padded:
            hits.append(f"banned:{w}")
    if norm and any(norm == _normalize(h.text) for h in history[-tuning.SUPERVISOR_REPEAT_WINDOW:]):
        hits.append("exact_repeat")
    return hits


def _repeat_free_pick(candidates: list[str], history: list[HistoryEntry], rng: random.Random, persona_id: str, used: dict[str, int]) -> str:
    if not candidates:
        return ""
    offset = used.get(persona_id, 0)
    recent = {_normalize(h.text) for h in history[-tuning.SUPERVISOR_REPEAT_WINDOW:]}
    for i in range(len(candidates)):
        c = candidates[(offset + i) % len(candidates)]
        if _normalize(c) not in recent:
            used[persona_id] = offset + i + 1
            return c
    choice = candidates[offset % len(candidates)]
    used[persona_id] = offset + 1
    return choice


@dataclass
class Reviewed:
    text: str
    emotion: Emotion
    verdict: SupervisorVerdict
    persona_result: PersonaResult  # hasil persona yang dipakai (asli atau buat ulang)
    judgement_prompt: str = ""

    @property
    def hook(self) -> str:
        """Verdict dalam kosakata hook: teruskan | koreksi | ganti."""
        return {"forward": "teruskan", "regenerate": "koreksi", "fallback": "ganti"}[self.verdict.action]


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
        t = content.text
        none = content.snippet("sup.none_item")
        claims = [t("sup.ledger_line", claim=e.claim, turn=e.turn) for e in self.ledger if e.persona == persona.id]
        topic = f'"{ctx.topic.judul}"' if ctx.topic else ctx.segment
        extra = (
            (t("sup.seg_transition", next=ctx.transition_to.judul) if ctx.transition_to else "")
            + (t("sup.seg_nudge", nudge_to=ctx.nudge_to) if ctx.nudge_to else "")
            + (content.snippet("sup.seg_opening") if ctx.segment == "opening" and ctx.turn_in_segment == 0 else "")
        )
        plain_none = content.snippet("sup.none_plain")
        lines = [
            t("sup.persona", name=persona.name, partner=ctx.partner_name),
            t("sup.facts", items="\n".join(f"- {f}" for f in persona.background_facts)),
            t("sup.opinions", items="\n".join(f"- {o}" for o in persona.opinions)),
            t("sup.ledger", items="\n".join(claims) if claims else none),
            t("sup.segment", segment=ctx.segment, topic=topic, extra=extra),
            t("sup.done", topics="; ".join(ctx.topics_done) or plain_none),
            t("sup.history", history="\n".join(f"{h.name}: {h.text}" for h in ctx.history[-6:]) or plain_none),
            t("sup.candidate", name=persona.name, text=text),
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
            return SupervisorJudgement(
                persona="ok", blocker="ok", safety="ok", responsiveness="ok", clarity_level=None, evasion_technique=None,
                evidence="judgement_unparsed", correction="", claims=[]
            ), latency, prompt

    # ── Alur pemeriksaan ─────────────────────────────────────────────────────

    def fallback(self, persona: PersonaCard, segment: str = "topic", history: Optional[list[HistoryEntry]] = None) -> str:
        """Kalimat aman sesuai segmen (sapaan di opening, pamit di closing), bergiliran supaya tidak berulang."""
        bank = fallback_bank().get(persona.id, {}).get(segment) or fallback_bank().get(persona.id, {}).get("topic") or [content.snippet("fallback_last_resort")]
        key = f"{persona.id}:{segment}"
        return _repeat_free_pick(bank, history or [], self._rng, key, self._fallback_used)

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
            if isinstance(e, LLMQuotaExhausted):
                self.mode = "rules"  # kuota harian habis: sisa sesi pakai aturan saja
            return clean, hits, None, 0, ""
        return clean, hits, judgement, latency, prompt

    @staticmethod
    def _violates(hits: list[str], sanitized_only: set[str], judgement: Optional[SupervisorJudgement]) -> bool:
        if any(h not in sanitized_only for h in hits):
            return True
        return bool(judgement and "violation" in (judgement.persona, judgement.blocker, judgement.safety, judgement.responsiveness))

    async def check(self, persona: PersonaCard, candidate: PersonaResult, ctx: TurnContext, regenerate: Regenerate, turn: int) -> Reviewed:
        """Hook di antara LLM dan TTS (`teruskan | koreksi | ganti`, lihat `Reviewed.hook`).

        Dengan SUPERVISOR_MODE=off (default) hook ini pass-through: teks persona diteruskan apa adanya
        tanpa pemanggilan LLM. `rules` dan `full` menjalankan pemeriksaan FR-5 penuh.
        """
        return await self.review(persona, candidate, ctx, regenerate, turn)

    async def review(self, persona: PersonaCard, candidate: PersonaResult, ctx: TurnContext, regenerate: Regenerate, turn: int) -> Reviewed:
        out = candidate.output
        if self.mode == "off":
            return Reviewed(out.text, out.emotion, SupervisorVerdict(mode="off"), candidate)
        if candidate.model == "fallback":
            # Kalimat dari bank aman sudah disaring; memeriksanya hanya menambah latensi saat LLM sedang lambat.
            return Reviewed(out.text, out.emotion, SupervisorVerdict(mode=self.mode, evidence="kalimat aman dari bank, tidak diperiksa"), candidate)

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
            verdict.checks = {
                "persona": judgement.persona,
                "blocker": judgement.blocker,
                "safety": judgement.safety,
                "responsiveness": judgement.responsiveness,
            }
            verdict.evidence = judgement.evidence
        if not self._violates(hits, cleanup, judgement):
            if judgement:
                self._record_claims(persona, judgement.claims, turn)
            return Reviewed(clean, out.emotion, verdict, candidate, prompt)

        # Pelanggaran: buat ulang sekali dengan memori koreksi, lalu periksa lagi.
        correction_text = (judgement.correction if judgement and judgement.correction else "") or content.text("sup.rewrite", hits=", ".join(h for h in hits if h not in cleanup))
        if judgement and judgement.responsiveness == "violation":
            correction_text = content.text("sup.answer_first", correction=correction_text)
        correction = CorrectionMemory(
            persona_reminder=correction_text,
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
        return Reviewed(self.fallback(persona, ctx.segment, ctx.history), Emotion.NEUTRAL, verdict, candidate, prompt)


# ── Mock ─────────────────────────────────────────────────────────────────────


def _mock_judgement(prompt: str, n: int) -> dict:
    candidate = prompt.rsplit("UCAPAN KANDIDAT", 1)[-1]
    bad = "LANGGAR" in candidate
    return {
        "persona": "ok",
        "blocker": "violation" if bad else "ok",
        "safety": "ok",
        "responsiveness": "ok",
        "clarity_level": "CR",
        "evasion_technique": "Direct Answer",
        "evidence": "kandidat memuat penanda uji LANGGAR" if bad else "",
        "correction": "jangan ulangi penanda uji" if bad else "",
        "claims": [],
    }


register_mock(SupervisorJudgement, _mock_judgement)
