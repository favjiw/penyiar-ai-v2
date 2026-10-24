"""Showrunner (FR-4, fokus publikasi): kapan obrolan lanjut, diarahkan, atau pindah topik.

Kebijakan (SHOWRUNNER_POLICY):
- `llm`: LLM menilai cakupan poin dan kejenuhan, lalu memutuskan;
- `fixed_turns`: pindah setiap FIXED_TURNS_PER_TOPIC giliran (baseline publikasi);
- `coverage_only`: LLM hanya menilai cakupan; pindah bila semua poin tercakup.

Aturan keras di semua kebijakan: tidak ada transisi sebelum MIN_TURNS_PER_TOPIC,
dan MAX_TURNS_PER_TOPIC memaksa transisi (`forced`). Bila LLM gagal (mis. kuota),
keputusan jatuh ke `fixed_turns` dan tercatat (PRD §8).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from app.agents.persona import HistoryEntry
from app.llm import LLMClient, LLMError, register_mock
from app.prompts import load_prompt
from app.schemas import BlockerTopic, ShowrunnerDecision, ShowrunnerJudgement, ShowrunnerPolicy

logger = logging.getLogger(__name__)
DEFAULT_FIXED_TURNS = 12


@dataclass
class TopicProgress:
    topic: BlockerTopic
    is_last: bool
    turns: int = 0
    audio_s: float = 0.0
    covered: set[str] = field(default_factory=set)
    history: list[HistoryEntry] = field(default_factory=list)

    @property
    def uncovered(self) -> list[str]:
        return [p.text for p in self.topic.poin if p.id not in self.covered]

    @property
    def coverage(self) -> float:
        return len(self.covered) / max(1, len(self.topic.poin))


class Showrunner:
    def __init__(
        self,
        llm: LLMClient,
        model: str,
        policy: ShowrunnerPolicy,
        every_k: int = 3,
        min_turns: int = 6,
        max_turns: int = 40,
        fixed_turns: int = 0,
        personas: tuple[str, ...] = ("raka", "salsa"),
    ):
        self._llm, self._model, self.policy = llm, model, policy
        self.every_k, self.min_turns, self.max_turns = every_k, min_turns, max_turns
        self.fixed_turns = fixed_turns or DEFAULT_FIXED_TURNS
        self._personas = personas
        self.prompt = load_prompt("showrunner")

    def should_call(self, progress: TopicProgress) -> bool:
        if progress.turns >= self.max_turns:
            return True
        if self.policy == "fixed_turns":
            return progress.turns >= self.fixed_turns
        return progress.turns > 0 and (progress.turns % self.every_k == 0 or progress.turns == self.min_turns)

    def judgement_prompt(self, p: TopicProgress, target_hint: str = "") -> str:
        lines = [
            f'TOPIK AKTIF: "{p.topic.judul}" (sudut pandang: {p.topic.sudut_pandang})' + (" — topik terakhir" if p.is_last else ""),
            "POIN:\n" + "\n".join(f"- {pt.id}: {pt.text}" + (" (sudah tercakup)" if pt.id in p.covered else "") for pt in p.topic.poin),
            f"GILIRAN DI TOPIK INI: {p.turns} (minimal {self.min_turns} sebelum boleh pindah); durasi audio ±{p.audio_s:.0f} detik.",
        ]
        if target_hint:
            lines.append(f"Petunjuk lunak durasi (bukan aturan): {target_hint}")
        lines.append("OBROLAN SEJAK TOPIK DIMULAI:\n" + "\n".join(f"{h.name}: {h.text}" for h in p.history[-24:]))
        return "\n\n".join(lines)

    def _fixed(self, p: TopicProgress, turn: int, reason: str = "") -> ShowrunnerDecision:
        go = p.turns >= self.fixed_turns
        return ShowrunnerDecision(
            turn=turn,
            topic_id=p.topic.id,
            points_covered=sorted(p.covered),
            decision=("close" if p.is_last else "transition") if go else "continue",
            reason=reason or (f"{p.turns} giliran tercapai" if go else f"{p.turns}/{self.fixed_turns} giliran"),
            policy="fixed_turns",
        )

    def fallback_decision(self, p: TopicProgress, turn: int, reason: str) -> ShowrunnerDecision:
        """Keputusan tanpa LLM (kuota habis, jaringan, atau batas waktu): aturan fixed_turns."""
        return self._fixed(p, turn, reason=reason)

    async def decide(self, p: TopicProgress, turn: int, target_hint: str = "") -> ShowrunnerDecision:
        valid_ids = {pt.id for pt in p.topic.poin}
        if p.turns >= self.max_turns:
            return ShowrunnerDecision(
                turn=turn,
                topic_id=p.topic.id,
                points_covered=sorted(p.covered),
                decision="close" if p.is_last else "transition",
                reason=f"batas keras {self.max_turns} giliran",
                policy=self.policy,
                forced=True,
            )
        if self.policy == "fixed_turns":
            return self._fixed(p, turn)

        start = time.perf_counter()
        try:
            resp = await self._llm.generate(
                self.judgement_prompt(p, target_hint),
                model=self._model,
                system_instruction=self.prompt.text,
                response_schema=ShowrunnerJudgement,
                temperature=0.2,
            )
            j = ShowrunnerJudgement.model_validate(resp.parsed)
        except (LLMError, ValueError) as e:
            logger.warning("Showrunner LLM gagal, pakai fixed_turns: %s", e)
            return self._fixed(p, turn, reason=f"LLM gagal ({str(e)[:80]}); fixed_turns")
        latency = int((time.perf_counter() - start) * 1000)

        # Cakupan hanya bertambah; id yang tidak ada di topik diabaikan.
        p.covered |= {pid for pid in j.points_covered if pid in valid_ids}
        uncovered = [pt for pt in p.topic.poin if pt.id not in p.covered]
        decision, hint, reason = j.decision, j.steer_hint, j.reason

        if self.policy == "coverage_only":
            if not uncovered:
                decision, hint, reason = "transition", "", "semua poin tercakup"
            else:
                decision, hint, reason = "steer", f"bahas {uncovered[0].id}: {uncovered[0].text}", f"{len(p.covered)}/{len(p.topic.poin)} poin"

        if decision in ("transition", "close"):
            if p.turns < self.min_turns:
                decision = "steer" if uncovered else "continue"
                hint = f"bahas {uncovered[0].id}: {uncovered[0].text}" if uncovered else ""
                reason = f"belum {self.min_turns} giliran; {reason}"
            else:
                decision = "close" if p.is_last else "transition"
        elif decision == "close" and not p.is_last:
            decision = "transition"

        next_speaker = j.next_speaker.strip().lower() or None
        return ShowrunnerDecision(
            turn=turn,
            topic_id=p.topic.id,
            points_covered=sorted(p.covered),
            saturation=max(0.0, min(1.0, j.saturation)),
            decision=decision,
            steer_hint=hint if decision == "steer" else "",
            next_speaker=next_speaker if next_speaker in self._personas else None,
            reason=reason,
            policy=self.policy,
            latency_ms=latency,
        )


# ── Mock ─────────────────────────────────────────────────────────────────────


def _mock_showrunner(prompt: str, n: int) -> dict:
    ids = re.findall(r"^- (t\d+p\d+):", prompt, flags=re.MULTILINE)
    turns = int(re.search(r"GILIRAN DI TOPIK INI: (\d+)", prompt).group(1))
    covered = ids[: min(len(ids), turns // 2)]
    done = len(covered) == len(ids)
    return {
        "points_covered": covered,
        "saturation": min(1.0, turns / 12),
        "decision": "transition" if done else "steer",
        "steer_hint": "" if done else f"bahas {ids[len(covered)]}",
        "next_speaker": "",
        "reason": "mock: cakupan mengikuti jumlah giliran",
    }


register_mock(ShowrunnerJudgement, _mock_showrunner)
