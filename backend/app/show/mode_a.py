"""Mode A (FR-2, FR-7): 1 penyiar manusia + 1 penyiar AI.

Tidak ada loop otomatis. Setiap ucapan penyiar (transkrip PTT dari prompter):
1. filler pendek AI langsung diputar dari bank (tanpa LLM);
2. persona menjawab singkat → Supervisor (batas SUPERVISOR_TIMEOUT_MS_MODE_A) →
   TTS dipecah per kalimat: kalimat pertama dikirim ke pemutar begitu siap, sisanya
   menyusul sebagai `audio_part`;
3. Showrunner hanya memberi saran (prompter/konsol) dan `steer_hint` untuk AI.

Penyiar memandu: "next topik" memindah segmen. Ucapan baru saat AI masih bicara
menghentikan jawaban AI yang sedang berjalan (penyiar boleh memotong).
Ucapan penyiar tidak diperiksa Supervisor (FR-5), tetapi masuk konteks dan log.
"""

from __future__ import annotations

import asyncio
import re
import time
from time import time as wall_clock
from typing import Any, Optional

from app.agents.persona import HistoryEntry, TurnContext
from app.agents.supervisor import Supervisor
from app.agents.persona import PersonaResult
from app.schemas import Emotion, LatencyMs, PersonaCard, PersonaOutput, ShowState, TurnRecord
from app.show.engine import ShowEngine
from app.tts.filler import FillerBank

HUMAN_ID = "human"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MIN_PART_WORDS = 4


def split_sentences(text: str) -> list[str]:
    """Pecah per kalimat untuk TTS bertahap; kalimat sangat pendek digabung ke berikutnya."""
    parts: list[str] = []
    for sentence in (s.strip() for s in _SENTENCE_END.split(text.strip())):
        if not sentence:
            continue
        if parts and len(parts[-1].split()) < MIN_PART_WORDS:
            parts[-1] = f"{parts[-1]} {sentence}"
        else:
            parts.append(sentence)
    return parts or [text.strip()]


class ModeAEngine(ShowEngine):
    def __init__(self, *args: Any, ai_persona: str, human_name: str, personas: dict[str, PersonaCard], **kwargs: Any):
        super().__init__(*args, personas=personas, mode="A", **kwargs)
        if ai_persona not in personas:
            raise ValueError(f"Persona AI tidak dikenal: {ai_persona}")
        self.ai = personas[ai_persona]
        self.personas = [self.ai]
        self.human_name = human_name.strip() or "Penyiar"
        # Supervisor lebih ketat waktunya: penyiar manusia menunggu jawaban.
        self.supervisor = Supervisor(
            self.supervisor._llm,
            self.supervisor._model,
            self.settings.SUPERVISOR_MODE,
            self.supervisor._rng,
            self.settings.SUPERVISOR_MAX_REGEN,
            self.settings.SUPERVISOR_TIMEOUT_MS_MODE_A,
        )
        self._supervisor_mode = self.settings.SUPERVISOR_MODE
        self.fillers = FillerBank(self.tts, self.audio_dir)
        self._reply: Optional[asyncio.Task] = None
        self._answering = False  # jawaban AI sedang berjalan; False sebelum snapshot terakhir dari blok finally
        self._human_turns_in_topic = 0

    # ── Status ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap["human"] = {"id": HUMAN_ID, "name": self.human_name}
        snap["ai_persona"] = self.ai.id
        snap["busy"] = self._answering
        snap["topic_points"] = self._topic_points()
        snap["fillers_ready"] = len(self.fillers._bank.get(self.ai.id, []))
        return snap

    def _topic_points(self) -> list[dict[str, Any]]:
        """Poin topik aktif dengan centang dari Showrunner (prompter, FR-11)."""
        if self.plan.segment != "topic":
            return []
        topic = self.blocker.topics[self.plan.topic_idx]
        covered = self.progress[topic.id].covered
        return [{"id": p.id, "text": p.text, "covered": p.id in covered} for p in topic.poin]

    # ── Siklus hidup ─────────────────────────────────────────────────────────

    def start(self) -> None:
        self.state = ShowState.LIVE
        self.started_at = time.monotonic()
        self._task = asyncio.create_task(self._open(), name=self.session_id)

    async def _open(self) -> None:
        self.log.event(
            "session_start",
            mode="A",
            seed=self.seed,
            blocker=self.blocker.model_dump(mode="json"),
            personas=[self.ai.id],
            human_name=self.human_name,
            config={k: getattr(self.settings, k) for k in ("LLM_MODE", "TTS_MODE", "TTS_PROVIDER", "TTS_FALLBACK", "SUPERVISOR_MODE", "SHOWRUNNER_POLICY", "SHOWRUNNER_EVERY_K", "SUPERVISOR_TIMEOUT_MS_MODE_A")},
            models={r: self.settings.model_for(r) for r in ("persona", "supervisor", "showrunner")},
            prompts={a.prompt.name: a.prompt.version for a in (self.persona_agent, self.supervisor, self.showrunner)},
        )
        for warning in self.tts.warnings:  # mis. ELEVENLABS_API_KEY kosong → jatuh ke Edge
            await self._alert("tts", warning)
        await self._broadcast_state()
        n = await self.fillers.prepare(self.ai)
        if n == 0:
            await self._alert("tts", "Bank filler kosong (TTS gagal); jawaban tetap jalan tanpa filler")
        self.log.event("quota", fillers_ready=n, tts=self.tts.status())
        await self._broadcast_state()

    async def stop(self) -> None:
        if self._reply and not self._reply.done():
            self._reply.cancel()
        await super().stop()

    async def skip(self) -> None:
        """Next topik oleh penyiar: segmen pindah seketika (tidak ada giliran yang disiapkan di depan)."""
        if self.state not in (ShowState.LIVE, ShowState.PAUSED) or self.plan.finished:
            return
        before = (self.plan.segment, self.plan.topic_idx)
        self._advance_segment()
        self._human_turns_in_topic = 0
        self.log.event("operator_action", action="next", from_segment=before[0], from_topic_idx=before[1], to_segment=self.plan.segment)
        if self.plan.finished:
            await self._finish("completed")
            return
        await self._announce()
        await self._broadcast_state()

    async def _announce(self) -> None:
        p = self.plan
        if p.announce_topic is not None:
            t = p.announce_topic
            p.announce_topic = None
            topic = {"id": t.id, "judul": t.judul, "pertanyaan_penonton": t.pertanyaan_penonton}
            self.on_air.update(segment="topic", topic=topic)
            self.progress[t.id].started_at = time.monotonic()
            self.log.event("topic_change", topic_id=t.id, judul=t.judul, turn=self.turn_no)
            await self._emit("topic_change", topic)
        elif p.announce_closing:
            p.announce_closing = False
            self.on_air.update(segment="closing", topic=None)
            self.log.event("topic_change", topic_id=None, judul="Closing", turn=self.turn_no)
            await self._emit("topic_change", {"id": None, "judul": "Closing", "pertanyaan_penonton": self.blocker.closing.ajakan})

    # ── Giliran ──────────────────────────────────────────────────────────────

    def _context(self, speaker: PersonaCard) -> TurnContext:
        """Lawan bicara AI adalah penyiar manusia; transisi diputuskan penyiar, bukan AI."""
        p, b = self.plan, self.blocker
        topic = b.topics[p.topic_idx] if p.segment == "topic" else None
        done = [t.judul for t in b.topics[: p.topic_idx]] if p.segment == "topic" else ([t.judul for t in b.topics] if p.segment == "closing" else [])
        return TurnContext(
            blocker=b,
            segment=p.segment,
            topic=topic,
            uncovered_points=self.progress[topic.id].uncovered if topic else [],
            history=self.history,
            partner_name=self.human_name,
            turn_in_segment=p.seg_turns,
            steer_hint=self.steer_hint,
            topics_done=done,
            mode="A",
            human_name=self.human_name,
        )

    async def human_turn(self, text: str, stt_ms: int = 0) -> Optional[dict[str, Any]]:
        """Transkrip final PTT. Kembalikan info filler yang diputar (atau None)."""
        text = text.strip()
        if self.state != ShowState.LIVE or not text:
            return None
        received = time.monotonic()
        if self._reply and not self._reply.done():
            # Penyiar memotong: jawaban AI yang sedang berjalan dihentikan.
            self._reply.cancel()
            await self._emit("stop_audio", {"reason": "interrupt"})
            self.log.event("operator_action", action="interrupt", turn=self.turn_no)

        self.turn_no += 1
        entry = {"turn": self.turn_no, "persona": HUMAN_ID, "name": self.human_name, "text": text, "emotion": "neutral",
                 "segment": self.plan.segment, "topic_id": self._topic_id(), "supervisor": "forward", "tts_provider": "", "gap_ms": 0, "ts": round(wall_clock(), 1)}
        self.history.append(HistoryEntry(HUMAN_ID, self.human_name, text))
        self.transcript.append(entry)
        self.log.event("stt", turn=self.turn_no, text=text, stt_ms=stt_ms, segment=self.plan.segment, topic_id=self._topic_id())
        await self._emit("human_turn", entry)

        filler = self.fillers.pick(self.ai.id)
        if filler:
            await self._emit("filler", {"persona": self.ai.id, "audio_url": filler.url, "duration_s": filler.duration_s, "text": filler.text})
        self._reply = asyncio.create_task(self._answer(received, filler.text if filler else None, stt_ms))
        return {"filler": filler.text if filler else None}

    def _topic_id(self) -> Optional[str]:
        return self.blocker.topics[self.plan.topic_idx].id if self.plan.segment == "topic" else None

    async def _answer(self, received: float, filler: Optional[str], stt_ms: int) -> None:
        self._answering = True
        try:
            await self._resume.wait()
            speaker = self.ai
            ctx = self._context(speaker)
            turn = self.turn_no + 1
            self.turn_no = turn
            latency = LatencyMs(stt=stt_ms)
            candidate = await self._persona_turn(speaker, ctx)
            latency.persona = candidate.latency_ms
            sup_start = time.perf_counter()
            reviewed = await self.supervisor.review(speaker, candidate, ctx, lambda corr: self._persona_turn(speaker, ctx, corr), turn)
            latency.supervisor = int((time.perf_counter() - sup_start) * 1000)
            if self.supervisor.mode != self._supervisor_mode:
                await self._alert("quota", f"Supervisor turun ke mode {self.supervisor.mode}: {self.supervisor.last_llm_error[:120]}")
                self._supervisor_mode = self.supervisor.mode

            parts = split_sentences(reviewed.text)
            first = await self._tts_part(speaker, parts[0], turn, 0)
            latency.tts = first["latency_ms"] if first else 0
            latency.gap_before_play = int((time.monotonic() - received) * 1000)  # lepas PTT → jawaban mulai dikirim
            self._playback_id = f"{self.session_id}:{turn}"
            self._playback_done.clear()
            entry = {"turn": turn, "persona": speaker.id, "name": speaker.name, "text": reviewed.text, "emotion": reviewed.emotion.value,
                     "segment": ctx.segment, "topic_id": ctx.topic.id if ctx.topic else None, "supervisor": reviewed.verdict.action,
                     "tts_provider": first["provider"] if first else "", "gap_ms": latency.gap_before_play, "ts": round(wall_clock(), 1)}
            self.transcript.append(entry)
            self.history.append(HistoryEntry(speaker.id, speaker.name, reviewed.text))
            self.on_air["speaking"] = speaker.id
            total = sum(len(p.split()) for p in parts) / 3.0
            await self._emit("turn", {**entry, "audio_url": first["url"] if first else None, "parts": len(parts),
                                      "duration_s": round(total, 1), "playback_id": self._playback_id})

            durations = [first["duration_s"] if first else 0.0]
            providers = {first["provider"]} if first else set()
            credits = first["credits"] if first else 0
            fallback_used = bool(first and first["fallback"])
            for i, part in enumerate(parts[1:], start=1):
                nxt = await self._tts_part(speaker, part, turn, i)
                if nxt:
                    durations.append(nxt["duration_s"])
                    providers.add(nxt["provider"])
                    credits += nxt["credits"]
                    fallback_used = fallback_used or nxt["fallback"]
                await self._emit("audio_part", {"playback_id": self._playback_id, "index": i, "audio_url": nxt["url"] if nxt else None})

            record = TurnRecord(
                session_id=self.session_id, mode="A", segment=ctx.segment, topic_id=entry["topic_id"], turn=turn, persona=speaker.id,
                raw_text=candidate.output.text, final_text=reviewed.text, emotion=reviewed.emotion, dialog_act=candidate.dialog_act,
                supervisor=reviewed.verdict, latency_ms=latency,
                models={"persona": candidate.model, "supervisor": self.supervisor._model if self.supervisor.mode == "full" else ""},
                tts_provider=",".join(sorted(providers)), tts_fallback_used=fallback_used, audio_url=first["url"] if first else None,
                duration_s=round(sum(durations), 2), credit_cost=credits, filler=filler, seed=self.seed,
            )
            self.log.event("turn", record)
            if reviewed.verdict.action != "forward" or reviewed.verdict.rule_hits:
                self.log.event("supervisor", reviewed.verdict, turn=turn, persona=speaker.id)
                await self._emit("supervisor", {"turn": turn, "persona": speaker.id, **reviewed.verdict.model_dump()})

            self.plan.seg_turns += 1
            await self._after_exchange(ctx, turn, sum(durations))
            await self._wait_playback(sum(durations))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._alert("engine", f"Jawaban AI gagal: {type(e).__name__}: {e}")
        finally:
            self._answering = False
            self.on_air["speaking"] = None
            await self._broadcast_state()

    async def _persona_failed(self, speaker: PersonaCard, ctx: TurnContext, message: str, permanent: bool = False) -> PersonaResult:
        """Mode A: penyiar yang memandu, jadi siaran tidak dibawa ke Closing; cukup peringatan + kalimat aman."""
        self._persona_failures += 1
        self.log.event("error", stage="persona", message=message[:300])
        if self._persona_failures >= self.settings.PERSONA_FAILURES_BEFORE_WRAP:
            await self._alert("engine", f"AI gagal menjawab {self._persona_failures}x berturut-turut ({message[:80]}); penyiar ambil alih dulu")
        text = self.supervisor.fallback(speaker, ctx.segment)
        return PersonaResult(PersonaOutput(text=text, emotion=Emotion.NEUTRAL), raw="", model="fallback", latency_ms=0, dialog_act=None, catchphrase=None)

    async def _tts_part(self, speaker: PersonaCard, text: str, turn: int, index: int) -> Optional[dict[str, Any]]:
        try:
            r = await self.tts.synthesize(text, speaker.id)
        except Exception as e:
            await self._alert("tts", f"Giliran {turn} bagian {index + 1} tanpa suara: {str(e)[:200]}")
            return None
        if r.fallback_used:
            await self._alert_once(f"tts_fallback:{r.provider}", f"TTS {self.tts.primary.name} gagal ({r.fallback_reason[:100]}); suara memakai {r.provider}")
        path = self.audio_dir / f"{self.session_id}_{turn:04d}_{index}.{r.ext}"
        path.write_bytes(r.audio)
        return {"url": f"/audio/{path.name}", "fallback": r.fallback_used,
                "duration_s": r.duration_s, "provider": r.provider, "latency_ms": r.latency_ms, "credits": r.credit_cost}

    async def _wait_playback(self, duration_s: float) -> None:
        timeout = duration_s + 5.0 if self._has_owner() else duration_s * self._time_scale
        try:
            await asyncio.wait_for(self._playback_done.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    async def _after_exchange(self, ctx: TurnContext, turn: int, audio_s: float) -> None:
        """Showrunner mode saran (FR-4): hanya memberi saran dan steer_hint, tidak memindah topik."""
        if ctx.segment != "topic" or ctx.topic is None:
            return
        prog = self.progress[ctx.topic.id]
        prog.turns += 2  # satu pertukaran = ucapan penyiar + jawaban AI
        prog.audio_s += audio_s
        prog.history = [h for h in self.history if h.persona_id in (HUMAN_ID, self.ai.id)][-24:]
        self._human_turns_in_topic += 1
        if self._human_turns_in_topic % max(1, self.settings.SHOWRUNNER_EVERY_K) != 0:
            return
        try:
            decision = await asyncio.wait_for(self.showrunner.decide(prog, turn), self.settings.SHOWRUNNER_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            return
        self.last_showrunner = decision
        self.steer_hint = decision.steer_hint if decision.decision == "steer" else ""
        self.log.event("showrunner", decision, advisory=True)
        await self._emit("showrunner", {**decision.model_dump(), "advisory": True})
