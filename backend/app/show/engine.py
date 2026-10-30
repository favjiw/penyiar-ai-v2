"""Show Engine (FR-2): orkestrator mode B (AI + AI) dari blocker terkunci.

Alur satu giliran: Persona → Supervisor → TTS → antrean putar. Giliran n+1
dibuat selagi audio giliran n diputar (pipelining, pola dari clock_runner repo
lama tanpa TalkBudget). Segmen: Opening (OPENING_TURNS giliran) → Topik 1..n
(Showrunner memutuskan transisi) → Closing (CLOSING_TURNS giliran).

Pemutaran: pemilik audio (konsol) memutar
`turn` dan melapor `ended`. Tanpa pemilik audio (mis. uji tanpa browser),
engine menunggu sepanjang durasi audio (headless).

Kontrol operator: pause/resume (giliran yang sedang diputar selesai dulu),
skip (audio dihentikan, lompat ke topik berikutnya atau penutup), stop.
Mode A (manusia + AI) dikerjakan di Tahap 4.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from time import time as wall_clock  # waktu dinding untuk cap transkrip; tes mengganti `time.monotonic`
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.agents.persona import HistoryEntry, PersonaAgent, PersonaResult, TurnContext
from app.agents.showrunner import Showrunner, TopicProgress
from app.agents.supervisor import Supervisor
from app.config import Settings
from app.llm import LLMClient, LLMError, LLMQuotaExhausted
from app.schemas import (
    Blocker,
    BlockerTopic,
    Emotion,
    LatencyMs,
    PersonaCard,
    PersonaOutput,
    Segment,
    ShowMode,
    ShowrunnerDecision,
    ShowState,
    SupervisorVerdict,
    TurnRecord,
)
from app.session_log import SessionLogger
from app.tts import FailoverTTS, TTSError

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
PLAYBACK_GRACE_SEC = 5.0
TRANSCRIPT_KEEP = 60


@dataclass
class PreparedTurn:
    epoch: int
    turn: int
    persona: PersonaCard
    segment: Segment
    topic: Optional[BlockerTopic]
    text: str
    emotion: Emotion
    record: TurnRecord
    audio_path: Optional[Path]
    duration_s: float
    starts_topic: Optional[BlockerTopic] = None  # giliran pertama topik baru → topic_change saat diputar
    starts_closing: bool = False


@dataclass
class Plan:
    """Posisi siaran untuk giliran yang akan DIBUAT (bisa satu langkah di depan yang diputar)."""

    segment: Segment = "opening"
    topic_idx: int = 0
    seg_turns: int = 0
    pending: Optional[str] = None  # "transition" | "to_closing"
    finished: bool = False
    announce_topic: Optional[BlockerTopic] = None
    announce_closing: bool = False


class ShowEngine:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        tts: FailoverTTS,
        blocker: Blocker,
        personas: dict[str, PersonaCard],
        emit: Emit,
        audio_dir: Path,
        mode: ShowMode = "B",
        seed: Optional[int] = None,
        has_audio_owner: Callable[[], bool] = lambda: False,
        time_scale: float = 1.0,
    ):
        if mode == "A" and type(self) is ShowEngine:
            raise ValueError("Mode A memakai ModeAEngine (app/show/mode_a.py)")
        if not blocker.locked:
            raise ValueError("Blocker harus dikunci sebelum live")
        self.settings, self.blocker, self.mode = settings, blocker, mode
        self.session_id = f"show_{time.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        rng = random.Random(self.seed)
        self.personas = [personas["raka"], personas["salsa"]]
        self.tts = tts
        self._emit_raw = emit
        self._has_owner = has_audio_owner
        self._time_scale = time_scale  # headless: 0 = tanpa menunggu (tes, harness FR-14)
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.persona_agent = PersonaAgent(llm, settings.model_for("persona"), rng, settings.PERSONA_TEMPERATURE)
        self.supervisor = Supervisor(
            llm, settings.model_for("supervisor"), settings.SUPERVISOR_MODE, rng, settings.SUPERVISOR_MAX_REGEN, settings.SUPERVISOR_TIMEOUT_MS
        )
        self.showrunner = Showrunner(
            llm,
            settings.model_for("showrunner"),
            settings.SHOWRUNNER_POLICY,
            settings.SHOWRUNNER_EVERY_K,
            settings.MIN_TURNS_PER_TOPIC,
            settings.MAX_TURNS_PER_TOPIC,
            settings.FIXED_TURNS_PER_TOPIC,
            tuple(p.id for p in self.personas),
        )
        self.log = SessionLogger(self.session_id, settings.LOG_DIR)

        self.state = ShowState.IDLE
        self.plan = Plan()
        self.epoch = 0
        self.turn_no = 0
        self.history: list[HistoryEntry] = []
        self.progress: dict[str, TopicProgress] = {
            t.id: TopicProgress(topic=t, is_last=i == len(blocker.topics) - 1) for i, t in enumerate(blocker.topics)
        }
        self.steer_hint = ""
        self.next_speaker: Optional[str] = None
        self._last_speakers: list[str] = []
        self.transcript: list[dict[str, Any]] = []
        self.on_air: dict[str, Any] = {"segment": "opening", "topic": None, "speaking": None}
        self.last_showrunner: Optional[ShowrunnerDecision] = None
        self._on_air_pos: tuple[Segment, int] = ("opening", 0)  # posisi yang sedang terdengar
        self.started_at = 0.0
        self._resume = asyncio.Event()
        self._resume.set()
        self._playback_id: Optional[str] = None
        self._playback_done = asyncio.Event()
        self._last_play_end: Optional[float] = None
        self._task: Optional[asyncio.Task] = None
        self.error: Optional[str] = None
        self._persona_failures = 0
        self._persona_failing_since = 0.0
        self._supervisor_mode = settings.SUPERVISOR_MODE

    # ── Event dan status ─────────────────────────────────────────────────────

    async def _emit(self, type_: str, data: dict[str, Any]) -> None:
        try:
            await self._emit_raw(type_, data)
        except Exception as e:  # klien putus tidak boleh menghentikan siaran
            logger.warning("Emit %s gagal: %s", type_, e)

    def snapshot(self) -> dict[str, Any]:
        """Status lengkap untuk klien yang baru tersambung atau reload (FR-8 keandalan)."""
        topic = self.on_air.get("topic")
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "mode": self.mode,
            "blocker": {"id": self.blocker.id, "tema": self.blocker.tema, "variant_label": self.blocker.variant_label, "topics": [t.judul for t in self.blocker.topics]},
            "personas": [{"id": p.id, "name": p.name} for p in self.personas],
            "segment": self.on_air["segment"],
            "topic": topic,
            "speaking": self.on_air.get("speaking"),
            "turn": self.turn_no,
            "elapsed_s": round(time.monotonic() - self.started_at, 1) if self.started_at else 0,
            "transcript": self.transcript[-TRANSCRIPT_KEEP:],
            "showrunner": self.last_showrunner.model_dump() if self.last_showrunner else None,
            "coverage": {tid: {"covered": sorted(p.covered), "total": len(p.topic.poin)} for tid, p in self.progress.items()},
            "tts": self.tts.status(),
            "error": self.error,
        }

    async def _broadcast_state(self) -> None:
        await self._emit("state", self.snapshot())

    # ── Kontrol operator ─────────────────────────────────────────────────────

    def start(self) -> None:
        self.state = ShowState.LIVE
        self.started_at = time.monotonic()
        self._task = asyncio.create_task(self._run(), name=self.session_id)

    async def pause(self) -> None:
        if self.state == ShowState.LIVE:
            self.state = ShowState.PAUSED
            self._resume.clear()
            self.log.event("operator_action", action="pause")
            await self._broadcast_state()

    async def resume(self) -> None:
        if self.state == ShowState.PAUSED:
            self.state = ShowState.LIVE
            self._resume.set()
            self.log.event("operator_action", action="resume")
            await self._broadcast_state()

    async def skip(self) -> None:
        """Lompat ke topik berikutnya (atau penutup); giliran yang sudah disiapkan dibuang."""
        if self.state not in (ShowState.LIVE, ShowState.PAUSED) or self.plan.finished:
            return
        # Rencana bisa sudah satu giliran di depan (giliran pertama topik berikutnya sudah
        # disiapkan); skip dihitung dari yang sedang on air, bukan dari rencana.
        before = self._on_air_pos
        self.epoch += 1
        self.plan = Plan(segment=before[0], topic_idx=before[1])
        self._advance_segment()
        self.log.event("operator_action", action="skip", from_segment=before[0], from_topic_idx=before[1], to_segment=self.plan.segment)
        await self._emit("stop_audio", {"reason": "skip"})
        self._playback_done.set()

    async def stop(self) -> None:
        if self.state == ShowState.ENDED:
            return
        self.log.event("operator_action", action="stop")
        await self._emit("stop_audio", {"reason": "stop"})
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        await self._finish("stopped")

    def playback_feedback(self, data: dict[str, Any]) -> None:
        if data.get("playback_id") != self._playback_id:
            return
        if data.get("status") == "error":
            self.log.event("error", stage="playback", playback_id=self._playback_id, message=str(data.get("message", "audio gagal diputar"))[:200])
        if data.get("status") in ("ended", "error"):
            self._playback_done.set()

    def release_playback(self) -> None:
        """Pemilik audio berganti atau putus: jangan menunggu laporan yang tidak akan datang."""
        self._playback_done.set()

    # ── Rencana segmen ───────────────────────────────────────────────────────

    def _advance_segment(self) -> None:
        p = self.plan
        p.seg_turns, p.pending = 0, None
        self.steer_hint, self.next_speaker = "", None
        if p.segment == "opening":
            p.segment, p.topic_idx = "topic", 0
            p.announce_topic = self.blocker.topics[0]
        elif p.segment == "topic" and p.topic_idx + 1 < len(self.blocker.topics):
            p.topic_idx += 1
            p.announce_topic = self.blocker.topics[p.topic_idx]
        elif p.segment == "topic":
            p.segment = "closing"
            p.announce_closing = True
        else:
            p.finished = True

    def _pick_speaker(self) -> PersonaCard:
        ids = [p.id for p in self.personas]
        if not self._last_speakers:
            choice = ids[0]
        else:
            choice = ids[1] if self._last_speakers[-1] == ids[0] else ids[0]
            if self.next_speaker in ids:
                choice = self.next_speaker
                self.next_speaker = None
            # hindari satu persona >2 kali berturut-turut (FR-2)
            if self._last_speakers[-2:] == [choice, choice]:
                choice = ids[1] if choice == ids[0] else ids[0]
        self._last_speakers.append(choice)
        return next(p for p in self.personas if p.id == choice)

    def _context(self, speaker: PersonaCard) -> TurnContext:
        p, b = self.plan, self.blocker
        partner = next(x for x in self.personas if x.id != speaker.id)
        topic = b.topics[p.topic_idx] if p.segment == "topic" else None
        progress = self.progress[topic.id] if topic else None
        done = [t.judul for t in b.topics[: p.topic_idx]] if p.segment == "topic" else ([t.judul for t in b.topics] if p.segment == "closing" else [])
        return TurnContext(
            blocker=b,
            segment=p.segment,
            topic=topic,
            uncovered_points=progress.uncovered if progress else [],
            history=self.history,
            partner_name=partner.name,
            turn_in_segment=p.seg_turns,
            steer_hint=self.steer_hint,
            transition_to=b.topics[p.topic_idx + 1] if p.pending == "transition" else None,
            to_closing=p.pending == "to_closing",
            closing_final=p.segment == "closing" and p.seg_turns >= self.settings.CLOSING_TURNS - 1,
            topics_done=done,
            mode=self.mode,
        )

    # ── Membuat satu giliran ─────────────────────────────────────────────────

    async def _alert(self, stage: str, message: str) -> None:
        """Masalah yang perlu diketahui operator, tapi siaran tetap jalan."""
        self.log.event("error", stage=stage, message=message[:300])
        await self._emit("alert", {"stage": stage, "message": message[:300], "turn": self.turn_no})

    async def _persona_turn(self, speaker: PersonaCard, ctx: TurnContext, correction=None) -> PersonaResult:
        try:
            result = await asyncio.wait_for(self.persona_agent.generate(speaker, ctx, correction), self.settings.PERSONA_TIMEOUT_MS / 1000)
            self._persona_failures = 0
            return result
        except LLMQuotaExhausted as e:
            fallback_model = self.settings.GEMINI_MODEL_PERSONA_FALLBACK
            if fallback_model and self.persona_agent._model != fallback_model:
                await self._alert("quota", f"Kuota harian model persona habis; pindah ke {fallback_model}")
                self.log.event("quota", role="persona", model_from=self.persona_agent._model, model_to=fallback_model)
                self.persona_agent._model = fallback_model
                return await self._persona_turn(speaker, ctx, correction)
            return await self._persona_failed(speaker, ctx, str(e), permanent=True)
        except (LLMError, asyncio.TimeoutError) as e:
            return await self._persona_failed(speaker, ctx, str(e) or "melewati PERSONA_TIMEOUT_MS")

    async def _persona_failed(self, speaker: PersonaCard, ctx: TurnContext, message: str, permanent: bool = False) -> PersonaResult:
        """Kalimat aman untuk giliran ini; siaran dibawa ke Closing bila persona mati terus.

        `permanent` (kuota harian habis tanpa model cadangan) langsung memenuhi syarat;
        galat lain (jaringan, timeout) harus beruntun sekaligus berlangsung
        PERSONA_FAILURE_WRAP_SEC, supaya gangguan DNS sesaat tidak menutup siaran.
        """
        now = time.monotonic()
        if self._persona_failures == 0:
            self._persona_failing_since = now
        self._persona_failures += 1
        self.log.event("error", stage="persona", message=message[:300])
        long_enough = permanent or now - self._persona_failing_since >= self.settings.PERSONA_FAILURE_WRAP_SEC
        if self._persona_failures >= self.settings.PERSONA_FAILURES_BEFORE_WRAP and long_enough and self.plan.segment != "closing":
            # Tanpa persona, siaran hanya memutar kalimat aman berulang: lebih baik ditutup rapi.
            await self._alert("engine", f"Persona gagal {self._persona_failures}x berturut-turut ({message[:80]}); siaran dibawa ke Closing")
            p = self.plan
            p.segment, p.seg_turns, p.pending, p.announce_closing, p.announce_topic = "closing", 0, None, True, None
        # Kuota/jaringan: kalimat aman dari bank supaya siaran tetap jalan.
        text = self.supervisor.fallback(speaker, ctx.segment)
        return PersonaResult(PersonaOutput(text=text, emotion=Emotion.NEUTRAL), raw="", model="fallback", latency_ms=0, dialog_act=None, catchphrase=None)

    async def _produce(self) -> Optional[PreparedTurn]:
        """Buat giliran berikutnya sesuai rencana, atau None bila siaran selesai."""
        p = self.plan
        if p.finished:
            return None
        epoch = self.epoch
        speaker = self._pick_speaker()
        ctx = self._context(speaker)
        starts_topic, p.announce_topic = p.announce_topic, None
        starts_closing, p.announce_closing = p.announce_closing, False
        self.turn_no += 1
        turn = self.turn_no

        latency = LatencyMs()
        candidate = await self._persona_turn(speaker, ctx)
        latency.persona = candidate.latency_ms
        sup_start = time.perf_counter()
        reviewed = await self.supervisor.review(speaker, candidate, ctx, lambda corr: self._persona_turn(speaker, ctx, corr), turn)
        latency.supervisor = int((time.perf_counter() - sup_start) * 1000)
        if self.supervisor.mode != self._supervisor_mode:
            await self._alert("quota", f"Supervisor turun ke mode {self.supervisor.mode}: {self.supervisor.last_llm_error[:120]}")
            self._supervisor_mode = self.supervisor.mode

        audio_path, duration, tts_provider, tts_reason, credits = None, max(1.5, len(reviewed.text.split()) / 3.0), "", "", 0
        try:
            result = await self.tts.synthesize(reviewed.text, speaker.gender, speaker.voices)
            latency.tts = result.latency_ms
            audio_path = self.audio_dir / f"{self.session_id}_{turn:04d}.{result.ext}"
            audio_path.write_bytes(result.audio)
            duration, tts_provider, tts_reason, credits = result.duration_s, result.provider, result.fallback_reason, result.credit_cost
        except (TTSError, Exception) as e:
            self.log.event("error", stage="tts", turn=turn, message=str(e)[:300])

        record = TurnRecord(
            session_id=self.session_id,
            mode=self.mode,
            segment=ctx.segment,
            topic_id=ctx.topic.id if ctx.topic else None,
            turn=turn,
            persona=speaker.id,
            raw_text=candidate.output.text,
            final_text=reviewed.text,
            emotion=reviewed.emotion,
            dialog_act=candidate.dialog_act,
            supervisor=reviewed.verdict,
            latency_ms=latency,
            models={"persona": candidate.model, "supervisor": self.supervisor._model if self.supervisor.mode == "full" else "", "tts": tts_provider},
            tts_provider=tts_provider,
            tts_fallback_reason=tts_reason,
            audio_url=f"/audio/{audio_path.name}" if audio_path else None,
            duration_s=round(duration, 2),
            credit_cost=credits,
            seed=self.seed,
        )
        if epoch != self.epoch:  # operator skip saat giliran ini dibuat
            self._last_speakers.pop()
            return await self._produce()

        self.history.append(HistoryEntry(speaker.id, speaker.name, reviewed.text))
        prepared = PreparedTurn(epoch, turn, speaker, ctx.segment, ctx.topic, reviewed.text, reviewed.emotion, record, audio_path, duration, starts_topic, starts_closing)
        await self._after_turn(ctx, prepared, reviewed.verdict)
        return prepared

    async def _after_turn(self, ctx: TurnContext, prepared: PreparedTurn, verdict: SupervisorVerdict) -> None:
        """Perbarui rencana setelah giliran dibuat; panggil Showrunner bila waktunya."""
        p = self.plan
        if verdict.action != "forward" or verdict.rule_hits:
            self.log.event("supervisor", verdict, turn=prepared.turn, persona=prepared.persona.id, raw_text=prepared.record.raw_text, final_text=prepared.text)
            await self._emit("supervisor", {"turn": prepared.turn, "persona": prepared.persona.id, **verdict.model_dump()})

        if ctx.transition_to is not None or ctx.to_closing:
            self._advance_segment()
            return
        p.seg_turns += 1
        if p.segment == "opening" and p.seg_turns >= self.settings.OPENING_TURNS:
            self._advance_segment()
        elif p.segment == "closing" and p.seg_turns >= self.settings.CLOSING_TURNS:
            p.finished = True
        elif p.segment == "topic":
            prog = self.progress[ctx.topic.id]
            if prog.started_at is None:
                self._start_topic_clock(prog)
            prog.turns += 1
            prog.audio_s += prepared.duration_s
            prog.history.append(self.history[-1])
            if prog.started_at is not None:
                prog.elapsed_s = time.monotonic() - prog.started_at
            if self.showrunner.should_call(prog):
                try:
                    decision = await asyncio.wait_for(
                        self.showrunner.decide(prog, prepared.turn, self._pacing_hint(ctx.topic, prog)), self.settings.SHOWRUNNER_TIMEOUT_MS / 1000
                    )
                except asyncio.TimeoutError:
                    decision = self.showrunner.fallback_decision(prog, prepared.turn, "melewati SHOWRUNNER_TIMEOUT_MS")
                self.last_showrunner = decision
                self.log.event("showrunner", decision)
                await self._emit("showrunner", decision.model_dump())
                self.steer_hint = decision.steer_hint if decision.decision == "steer" else ""
                self.next_speaker = decision.next_speaker
                if decision.decision == "transition":
                    p.pending = "transition"
                elif decision.decision == "close":
                    p.pending = "to_closing"

    def _start_topic_clock(self, prog: TopicProgress) -> None:
        """Jatah waktu topik [F]: sisa target sesi (dikurangi cadangan Closing) dibagi sisa topik."""
        prog.started_at = time.monotonic()
        target = self.settings.SESSION_TARGET_MIN * 60
        if not target:
            return
        elapsed = prog.started_at - self.started_at
        remaining_topics = len(self.blocker.topics) - self.blocker.topics.index(prog.topic)
        closing_reserve = self.settings.CLOSING_TURNS * 10
        prog.budget_s = max(60.0, (target - elapsed - closing_reserve) / remaining_topics)
        self.log.event("quota", topic_id=prog.topic.id, topic_budget_s=round(prog.budget_s), session_elapsed_s=round(elapsed))

    def _pacing_hint(self, topic: BlockerTopic, prog: TopicProgress) -> str:
        """Petunjuk lunak durasi untuk Showrunner (FR-4): jatah per topik vs yang sudah berjalan."""
        target = self.settings.SESSION_TARGET_MIN
        if not target:
            return ""
        n = len(self.blocker.topics)
        idx = self.blocker.topics.index(topic)
        elapsed = (time.monotonic() - self.started_at) / 60 if self.started_at else 0
        remaining_topics = n - idx
        budget = max(1.0, (target - elapsed) / remaining_topics + prog.audio_s / 60)
        return (
            f"siaran sudah ±{elapsed:.0f} dari target ±{target} menit; ini topik {idx + 1} dari {n}; "
            f"jatah lunak topik ini ±{budget:.0f} menit, sudah berjalan ±{prog.audio_s / 60:.1f} menit"
        )

    # ── Pemutaran ────────────────────────────────────────────────────────────

    async def _play(self, t: PreparedTurn) -> None:
        self._on_air_pos = (t.segment, self.blocker.topics.index(t.topic) if t.topic else 0)
        if t.starts_topic is not None:
            topic = {"id": t.starts_topic.id, "judul": t.starts_topic.judul, "pertanyaan_penonton": t.starts_topic.pertanyaan_penonton}
            self.on_air.update(segment="topic", topic=topic)
            self.log.event("topic_change", topic_id=t.starts_topic.id, judul=t.starts_topic.judul, turn=t.turn)
            self.log.event("quota", tts=self.tts.status())
            await self._emit("topic_change", topic)
        elif t.starts_closing:
            self.on_air.update(segment="closing", topic=None)
            self.log.event("topic_change", topic_id=None, judul="Closing", turn=t.turn)
            await self._emit("topic_change", {"id": None, "judul": "Closing", "pertanyaan_penonton": self.blocker.closing.ajakan})

        start = time.monotonic()
        gap = int((start - self._last_play_end) * 1000) if self._last_play_end is not None else 0
        t.record.latency_ms.gap_before_play = gap
        self.log.event("turn", t.record)
        entry = {"turn": t.turn, "persona": t.persona.id, "name": t.persona.name, "text": t.text, "emotion": t.emotion.value,
                 "segment": t.segment, "topic_id": t.topic.id if t.topic else None, "supervisor": t.record.supervisor.action,
                 "tts_provider": t.record.tts_provider, "gap_ms": gap, "ts": round(wall_clock(), 1)}
        self.transcript.append(entry)
        self.on_air["speaking"] = t.persona.id

        self._playback_id = f"{self.session_id}:{t.turn}"
        self._playback_done.clear()
        await self._emit("turn", {**entry, "audio_url": t.record.audio_url, "duration_s": t.duration_s, "playback_id": self._playback_id})
        if t.record.audio_url and self._has_owner():
            try:
                await asyncio.wait_for(self._playback_done.wait(), t.duration_s + PLAYBACK_GRACE_SEC)
            except asyncio.TimeoutError:
                logger.warning("Tidak ada laporan selesai untuk giliran %d; lanjut", t.turn)
        else:
            try:
                await asyncio.wait_for(self._playback_done.wait(), t.duration_s * self._time_scale)  # headless: tunggu durasi audio
            except asyncio.TimeoutError:
                pass
        self.on_air["speaking"] = None
        self._last_play_end = time.monotonic()

    # ── Loop utama ───────────────────────────────────────────────────────────

    async def _run(self) -> None:
        self.log.event(
            "session_start",
            mode=self.mode,
            seed=self.seed,
            blocker=self.blocker.model_dump(mode="json"),
            personas=[p.id for p in self.personas],
            config={k: getattr(self.settings, k) for k in (
                "LLM_MODE", "TTS_MODE", "TTS_PRIMARY", "SUPERVISOR_MODE", "SHOWRUNNER_POLICY", "SHOWRUNNER_EVERY_K",
                "MIN_TURNS_PER_TOPIC", "MAX_TURNS_PER_TOPIC", "FIXED_TURNS_PER_TOPIC", "PIPELINE_DEPTH", "OPENING_TURNS", "CLOSING_TURNS")},
            models={r: self.settings.model_for(r) for r in ("persona", "supervisor", "showrunner")},
            prompts={a.prompt.name: a.prompt.version for a in (self.persona_agent, self.supervisor, self.showrunner)},
        )
        await self._broadcast_state()
        # Pipelining (FR-2): produsen menyiapkan sampai PIPELINE_DEPTH giliran di depan;
        # satu slot terbuka setiap kali sebuah giliran mulai diputar. Depth 1 = giliran n+1
        # dibuat selagi n diputar; depth 2 menambah satu giliran cadangan untuk meredam API lambat.
        ready: asyncio.Queue[Optional[PreparedTurn] | Exception] = asyncio.Queue()
        slots = asyncio.Semaphore(max(1, self.settings.PIPELINE_DEPTH))

        async def producer() -> None:
            try:
                while True:
                    await slots.acquire()
                    item = await self._produce()
                    await ready.put(item)
                    if item is None:
                        return
            except Exception as e:  # diteruskan ke loop utama supaya tercatat sebagai galat sesi
                await ready.put(e)

        producing = asyncio.create_task(producer())
        try:
            while True:
                item = await ready.get()
                if isinstance(item, Exception):
                    raise item
                if item is None:
                    break
                await self._resume.wait()
                if item.epoch != self.epoch:  # di-skip sebelum diputar
                    slots.release()
                    continue
                slots.release()
                await self._broadcast_state()
                await self._play(item)
                await self._broadcast_state()
            await self._finish("completed")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Show Engine berhenti karena galat")
            self.error = f"{type(e).__name__}: {e}"
            self.log.event("error", stage="engine", message=self.error[:500])
            await self._finish("error")
        finally:
            producing.cancel()

    async def _finish(self, reason: str) -> None:
        if self.state == ShowState.ENDED:
            return
        self.state = ShowState.ENDED
        self._resume.set()
        self.log.event(
            "session_end",
            reason=reason,
            turns=self.turn_no,
            elapsed_s=round(time.monotonic() - self.started_at, 1),
            credits_used=self.tts.credits_used,
            ledger=[e.model_dump() for e in self.supervisor.ledger],
        )
        await self._broadcast_state()
