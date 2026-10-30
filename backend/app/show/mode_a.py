"""Mode A dan C (FR-2, FR-7): penyiar manusia memandu, AI menanggapi.

- Mode A: 1 manusia + 1 AI (pilihan operator).
- Mode C: 1 manusia (pemegang sesi) + semua AI. Manusia satu-satunya yang menekan "next topik".

Tidak ada loop otomatis. Setiap ucapan penyiar (transkrip PTT dari prompter) memulai satu pertukaran:
1. filler pendek AI yang akan menjawab diputar dari bank (tanpa LLM);
2. AI menjawab singkat → Supervisor (hook, batas SUPERVISOR_TIMEOUT_MS_MODE_A) → TTS dipecah
   per kalimat: kalimat pertama dikirim ke pemutar begitu siap, sisanya menyusul sebagai `audio_part`;
3. Mode C: yang menjawab adalah AI yang disapa namanya ("kalian" menyapa semua); tanpa sapaan,
   AI bergantian. AI lain boleh menimpali (peluang MODE_C_CHIME_PROBABILITY, wajib bila manusia
   menyapa lebih dari satu), dengan batas MODE_C_MAX_AI_STREAK giliran AI berturut-turut sebelum
   giliran kembali ke manusia;
4. Showrunner hanya memberi saran (prompter/konsol) dan `steer_hint` untuk AI.

Ucapan baru saat AI masih bicara menghentikan jawaban yang sedang berjalan (penyiar boleh memotong).
Ucapan penyiar tidak diperiksa Supervisor (FR-5), tetapi masuk konteks dan log.
"""

from __future__ import annotations

import asyncio
import re
import time
from time import time as wall_clock
from typing import Any, Optional, Sequence

from app.agents.persona import HistoryEntry, PersonaResult, TurnContext
from app.agents.supervisor import Supervisor
from app.schemas import Emotion, LatencyMs, PersonaCard, PersonaOutput, ShowState, TurnRecord
from app.show.engine import ShowEngine
from app.show.participants import HUMAN_ID, addressed_ais
from app.tts.filler import FillerBank

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


class HumanLedEngine(ShowEngine):
    def __init__(
        self,
        *args: Any,
        human_name: str,
        personas: dict[str, PersonaCard],
        ai_persona: Optional[str] = None,
        ai_personas: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ):
        ids = list(ai_personas) if ai_personas else ([ai_persona] if ai_persona else [])
        if not ids:
            raise ValueError("Mode A dan C butuh minimal satu persona AI")
        unknown = [i for i in ids if i not in personas]
        if unknown:
            raise ValueError(f"Persona AI tidak dikenal: {', '.join(unknown)}")
        super().__init__(*args, personas=personas, mode="A" if len(ids) == 1 else "C", ai_ids=ids, human_name=human_name, **kwargs)
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
        self._answering = False  # pertukaran AI sedang berjalan; False sebelum snapshot terakhir dari blok finally
        self._thinking: Optional[str] = None  # id AI yang sedang menyiapkan jawaban (LLM/TTS), belum bersuara
        self._ai_streak = 0  # giliran AI berturut-turut sejak ucapan manusia terakhir
        self._last_responder: Optional[str] = None
        self._exchanges_in_topic = 0

    @property
    def ai(self) -> PersonaCard:
        """AI pertama; di mode A satu-satunya."""
        return self.personas[0]

    def _ai(self, persona_id: str) -> PersonaCard:
        return next(p for p in self.personas if p.id == persona_id)

    # ── Status ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap["human"] = {"id": HUMAN_ID, "name": self.human_name}
        snap["ai_persona"] = self.ai.id if self.mode == "A" else None
        snap["busy"] = self._answering
        snap["thinking"] = self._thinking
        snap["ai_streak"] = self._ai_streak
        snap["topic_points"] = self._topic_points()
        snap["fillers_ready"] = sum(len(self.fillers._bank.get(p.id, [])) for p in self.personas)
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
        self.save_session_blocker()
        self._task = asyncio.create_task(self._open(), name=self.session_id)

    async def _open(self) -> None:
        self.log.event(
            "session_start",
            mode=self.mode,
            seed=self.seed,
            blocker=self.blocker.model_dump(mode="json"),
            personas=[p.id for p in self.personas],
            participants=[{"id": p.id, "name": p.name, "kind": p.kind} for p in self.participants],
            human_name=self.human_name,
            config={k: getattr(self.settings, k) for k in (
                "LLM_MODE", "TTS_MODE", "TTS_PROVIDER", "TTS_FALLBACK", "SUPERVISOR_MODE", "SHOWRUNNER_POLICY", "SHOWRUNNER_EVERY_K",
                "SUPERVISOR_TIMEOUT_MS_MODE_A", "MODE_C_MAX_AI_STREAK", "MODE_C_CHIME_PROBABILITY", "SUMMARY_EVERY_TURNS")},
            models={r: self.settings.model_for(r) for r in ("persona", "supervisor", "showrunner")},
            prompts={a.prompt.name: a.prompt.version for a in (self.persona_agent, self.supervisor, self.showrunner, self.summary)},
        )
        for warning in self.tts.warnings:  # mis. ELEVENLABS_API_KEY kosong → jatuh ke Edge
            await self._alert("tts", warning)
        await self._broadcast_state()
        ready = 0
        for persona in self.personas:
            n = await self.fillers.prepare(persona)
            ready += n
            if n == 0:
                await self._alert("tts", f"Bank filler {persona.name} kosong (TTS gagal); jawaban tetap jalan tanpa filler")
        self.log.event("quota", fillers_ready=ready, tts=self.tts.status())
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
        self._exchanges_in_topic = 0
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

    def _context(self, speaker: PersonaCard, chime_after: str = "") -> TurnContext:  # type: ignore[override]
        """Konteks AI di siaran yang dipandu manusia; transisi topik diputuskan penyiar, bukan AI."""
        p, b = self.plan, self.blocker
        others = self._others(speaker)
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
            mode=self.mode,
            human_name=self.human_name,
            others=others if len(others) > 1 else [],  # mode A: lawan bicara satu-satunya (manusia) sudah disebut terpisah
            summary=self.summary.text,
            chime_after=chime_after,
        )

    def _plan_responders(self, text: str) -> tuple[str, bool]:
        """(AI yang menjawab, wajib ada AI lain yang menimpali). Disapa namanya, kalau tidak bergiliran."""
        ids = [p.id for p in self.personas]
        if len(ids) == 1:
            return ids[0], False
        named = addressed_ais(text, [pt for pt in self.participants if not pt.is_human])
        if named:
            first, forced = named[0], len(named) > 1
        else:
            nxt = ids[(ids.index(self._last_responder) + 1) % len(ids)] if self._last_responder in ids else ids[0]
            first, forced = nxt, False
        self._last_responder = first
        return first, forced

    def _next_chime(self, spoke: list[str], forced: bool) -> Optional[PersonaCard]:
        """AI yang menimpali berikutnya, atau None bila giliran harus kembali ke manusia."""
        if len(self.personas) < 2 or self._ai_streak >= self.settings.MODE_C_MAX_AI_STREAK:
            return None
        candidates = [p for p in self.personas if p.id not in spoke] or [p for p in self.personas if p.id != spoke[-1]]
        if forced or self._rng.random() < self.settings.MODE_C_CHIME_PROBABILITY:
            return candidates[0]
        return None

    async def human_turn(self, text: str, stt_ms: int = 0, speech_ms: int = 0) -> Optional[dict[str, Any]]:
        """Transkrip final PTT. Kembalikan info filler yang diputar (atau None)."""
        text = text.strip()
        if self.state != ShowState.LIVE or not text:
            return None
        received = time.monotonic()
        arrived = wall_clock()
        if self._reply and not self._reply.done():
            # Penyiar memotong: jawaban AI yang sedang berjalan dihentikan.
            self._reply.cancel()
            await self._emit("stop_audio", {"reason": "interrupt"})
            self.log.event("operator_action", action="interrupt", turn=self.turn_no)

        self.turn_no += 1
        self._ai_streak = 0
        entry = {"turn": self.turn_no, "persona": HUMAN_ID, "name": self.human_name, "text": text, "emotion": "neutral",
                 "segment": self.plan.segment, "topic_id": self._topic_id(), "supervisor": "forward", "tts_provider": "", "gap_ms": 0, "ts": round(arrived, 1)}
        self._remember(HistoryEntry(HUMAN_ID, self.human_name, text))
        self.transcript.append(entry)
        self.log.event("stt", turn=self.turn_no, text=text, stt_ms=stt_ms, speech_ms=speech_ms, segment=self.plan.segment, topic_id=self._topic_id())
        released = arrived - stt_ms / 1000  # tombol dilepas; transkrip final tiba stt_ms kemudian
        self.log_turn(
            turn=self.turn_no, speaker=HUMAN_ID, speaker_name=self.human_name, is_human=True, segment=self.plan.segment, topic_id=self._topic_id(),
            text=text, raw_text=text, t_start=released - speech_ms / 1000, t_end=released, asr_ms=stt_ms, llm_ms=0, tts_ms=0, model="", tts_chars=0, filler=None,
        )
        await self._emit("human_turn", entry)

        first, forced = self._plan_responders(text)
        filler = self.fillers.pick(first)
        if filler:
            await self._emit("filler", {"persona": first, "audio_url": filler.url, "duration_s": filler.duration_s, "text": filler.text})
        self._reply = asyncio.create_task(self._exchange(received, first, forced, filler.text if filler else None, stt_ms))
        return {"filler": filler.text if filler else None, "responder": first}

    def _topic_id(self) -> Optional[str]:
        return self.blocker.topics[self.plan.topic_idx].id if self.plan.segment == "topic" else None

    async def _set_thinking(self, persona_id: Optional[str]) -> None:
        if self._thinking != persona_id:
            self._thinking = persona_id
            await self._broadcast_state()

    async def _exchange(self, received: float, first: str, forced_chime: bool, filler: Optional[str], stt_ms: int) -> None:
        """Satu pertukaran: AI yang menjawab, lalu (mode C) AI lain boleh menimpali sampai batas streak."""
        self._answering = True
        try:
            await self._resume.wait()
            speaker, chime_after, spoke, total_audio, turn = self._ai(first), "", [], 0.0, self.turn_no
            while True:
                turn, audio_s = await self._ai_turn(speaker, received, filler if not spoke else None, stt_ms if not spoke else 0, chime_after)
                spoke.append(speaker.id)
                total_audio += audio_s
                self._ai_streak += 1
                nxt = self._next_chime(spoke, forced_chime)
                forced_chime = False
                if nxt is None:
                    break
                received, chime_after, speaker = time.monotonic(), speaker.name, nxt
            await self._after_exchange(turn, total_audio, ai_turns=len(spoke))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._alert("engine", f"Jawaban AI gagal: {type(e).__name__}: {e}")
        finally:
            self._answering = False
            self._thinking = None
            self.on_air["speaking"] = None
            await self._broadcast_state()

    async def _ai_turn(self, speaker: PersonaCard, received: float, filler: Optional[str], stt_ms: int, chime_after: str) -> tuple[int, float]:
        """Satu giliran AI sampai selesai diputar. Kembalikan (nomor giliran, durasi audio detik)."""
        await self._set_thinking(speaker.id)
        ctx = self._context(speaker, chime_after)
        turn = self.turn_no + 1
        self.turn_no = turn
        latency = LatencyMs(stt=stt_ms)
        candidate = await self._persona_turn(speaker, ctx)
        latency.persona = candidate.latency_ms
        sup_start = time.perf_counter()
        reviewed = await self.supervisor.check(speaker, candidate, ctx, lambda corr: self._persona_turn(speaker, ctx, corr), turn)
        latency.supervisor = int((time.perf_counter() - sup_start) * 1000)
        if self.supervisor.mode != self._supervisor_mode:
            await self._alert("quota", f"Supervisor turun ke mode {self.supervisor.mode}: {self.supervisor.last_llm_error[:120]}")
            self._supervisor_mode = self.supervisor.mode

        parts = split_sentences(reviewed.text)
        first = await self._tts_part(speaker, parts[0], turn, 0)
        latency.tts = first["latency_ms"] if first else 0
        latency.gap_before_play = int((time.monotonic() - received) * 1000)  # lepas PTT (atau AI sebelumnya selesai) → jawaban mulai dikirim
        self._playback_id = f"{self.session_id}:{turn}"
        self._playback_done.clear()
        entry = {"turn": turn, "persona": speaker.id, "name": speaker.name, "text": reviewed.text, "emotion": reviewed.emotion.value,
                 "segment": ctx.segment, "topic_id": ctx.topic.id if ctx.topic else None, "supervisor": reviewed.verdict.action,
                 "tts_provider": first["provider"] if first else "", "gap_ms": latency.gap_before_play, "ts": round(wall_clock(), 1)}
        self.transcript.append(entry)
        self._remember(HistoryEntry(speaker.id, speaker.name, reviewed.text))
        self.on_air["speaking"] = speaker.id
        self._thinking = None
        total = sum(len(p.split()) for p in parts) / 3.0
        t_start, completed = wall_clock(), False
        durations = [first["duration_s"] if first else 0.0]
        providers = {first["provider"]} if first else set()
        credits = first["credits"] if first else 0
        fallback_used = bool(first and first["fallback"])
        tts_ms = first["latency_ms"] if first else 0
        tts_chars = len(parts[0]) if first else 0
        try:
            await self._emit("turn", {**entry, "audio_url": first["url"] if first else None, "parts": len(parts),
                                      "duration_s": round(total, 1), "playback_id": self._playback_id})
            for i, part in enumerate(parts[1:], start=1):
                nxt = await self._tts_part(speaker, part, turn, i)
                if nxt:
                    durations.append(nxt["duration_s"])
                    providers.add(nxt["provider"])
                    credits += nxt["credits"]
                    fallback_used = fallback_used or nxt["fallback"]
                    tts_ms += nxt["latency_ms"]
                    tts_chars += len(part)
                await self._emit("audio_part", {"playback_id": self._playback_id, "index": i, "audio_url": nxt["url"] if nxt else None})

            record = TurnRecord(
                session_id=self.session_id, mode=self.mode, segment=ctx.segment, topic_id=entry["topic_id"], turn=turn, persona=speaker.id,
                raw_text=candidate.output.text, final_text=reviewed.text, emotion=reviewed.emotion, dialog_act=candidate.dialog_act,
                supervisor=reviewed.verdict, latency_ms=latency,
                models={"persona": candidate.model, "supervisor": self.supervisor._model if self.supervisor.mode == "full" else ""},
                tts_provider=",".join(sorted(providers)), tts_fallback_used=fallback_used, audio_url=first["url"] if first else None,
                duration_s=round(sum(durations), 2), credit_cost=credits, filler=filler, seed=self.seed,
            )
            self.log.event("turn", record, chime_after=chime_after or None)
            if reviewed.verdict.action != "forward" or reviewed.verdict.rule_hits:
                self.log.event("supervisor", reviewed.verdict, turn=turn, persona=speaker.id)
                await self._emit("supervisor", {"turn": turn, "persona": speaker.id, **reviewed.verdict.model_dump()})

            self.plan.seg_turns += 1
            await self._wait_playback(sum(durations))
            completed = True
        finally:
            self.log_turn(
                turn=turn, speaker=speaker.id, speaker_name=speaker.name, is_human=False, segment=ctx.segment,
                topic_id=entry["topic_id"], text=reviewed.text, raw_text=candidate.output.text, t_start=t_start, t_end=wall_clock(),
                asr_ms=stt_ms, llm_ms=candidate.latency_ms, supervisor_ms=latency.supervisor, tts_ms=tts_ms, model=candidate.model,
                tts_chars=tts_chars, filler=filler, supervisor_action=reviewed.verdict.action, tts_provider=",".join(sorted(providers)),
                tts_fallback_used=fallback_used, dialog_act=candidate.dialog_act, gap_ms=latency.gap_before_play, interrupted=not completed,
            )
        return turn, sum(durations)

    async def _persona_failed(self, speaker: PersonaCard, ctx: TurnContext, message: str, permanent: bool = False) -> PersonaResult:
        """Siaran dipandu manusia, jadi tidak dibawa ke Closing; cukup peringatan + kalimat aman."""
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

    async def _after_exchange(self, turn: int, audio_s: float, ai_turns: int) -> None:
        """Showrunner mode saran (FR-4): hanya memberi saran dan steer_hint, tidak memindah topik."""
        if self.plan.segment != "topic":
            return
        topic = self.blocker.topics[self.plan.topic_idx]
        prog = self.progress[topic.id]
        prog.turns += 1 + ai_turns  # satu pertukaran = ucapan penyiar + jawaban AI (mode C: bisa dua)
        prog.audio_s += audio_s
        ids = {HUMAN_ID, *(p.id for p in self.personas)}
        prog.history = [h for h in self.history if h.persona_id in ids][-24:]
        self._exchanges_in_topic += 1
        if self._exchanges_in_topic % max(1, self.settings.SHOWRUNNER_EVERY_K) != 0:
            return
        try:
            decision = await asyncio.wait_for(self.showrunner.decide(prog, turn), self.settings.SHOWRUNNER_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            return
        self.last_showrunner = decision
        self.steer_hint = decision.steer_hint if decision.decision == "steer" else ""
        self.log.event("showrunner", decision, advisory=True)
        await self._emit("showrunner", {**decision.model_dump(), "advisory": True})


ModeAEngine = HumanLedEngine  # nama lama
