"""Show Engine (FR-2): orkestrator siaran dari blocker terkunci.

Peserta berupa daftar (`participants.py`). Kelas ini menjalankan mode B (semua peserta AI,
otomatis); mode A (penyiar manusia memandu) ada di `mode_a.py` sebagai turunan yang
memakai kerangka yang sama: state machine, Supervisor, TTS, pemutaran, dan log.

Alur satu giliran: Persona → Supervisor → TTS → antrean putar. Giliran n+1
dibuat selagi audio giliran n diputar (pipelining, pola dari clock_runner repo
lama tanpa TalkBudget). Segmen: Opening (OPENING_TURNS giliran) → Topik 1..n
(Showrunner memutuskan transisi) → Closing (CLOSING_TURNS giliran).

Pemutaran: pemilik audio (konsol) memutar
`turn` dan melapor `ended`. Tanpa pemilik audio (mis. uji tanpa browser),
engine menunggu sepanjang durasi audio (headless).

Kontrol operator: pause/resume (giliran yang sedang diputar selesai dulu),
skip (audio dihentikan, lompat ke topik berikutnya atau penutup), stop.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from time import time as wall_clock  # waktu dinding untuk cap transkrip; tes mengganti `time.monotonic`
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence

from app.agents.persona import HistoryEntry, PersonaAgent, PersonaResult, TurnContext, detect_interrogative
from app.agents.showrunner import Showrunner, TopicProgress
from app.agents.summary import ConversationSummary
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
from app.show.pointclock import PointClock, trim_to_budget
from app.show.participants import Participant, build_participants
from app.show.turnlog import TurnLog, topic_index
from app.tts import FailoverTTS, TTSError

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
PLAYBACK_GRACE_SEC = 5.0
TRANSCRIPT_KEEP = 60
# Peringatan untuk konsol (DESIGN.md §4): kode → (tingkat, judul, pesan dengan istilah UI).
ALERT_TEXT: dict[str, tuple[str, str, str]] = {
    "tts_silent": ("yellow", "Satu giliran AI tanpa suara", "Suara AI gagal dibuat untuk giliran ini. Siaran tetap jalan; cek Detail teknis bila berulang."),
    "tts_fallback": ("blue", "Suara cadangan aktif", "Suara AI pindah ke cadangan dan terdengar sedikit berbeda. Siaran tetap jalan."),
    "tts_warning": ("yellow", "Ada catatan soal suara AI", "Suara AI mungkin tidak sesuai pilihan. Lihat Detail teknis."),
    "llm_fallback": ("blue", "Otak AI pindah ke cadangan", "Kuota otak AI habis; siaran memakai cadangan otomatis."),
    "ai_failing": ("yellow", "AI gagal menjawab", "Kalau terus berulang, siaran dibawa ke penutup. Penyiar bisa ambil alih dulu."),
    "tts_quota_low": ("yellow", "Kuota suara AI hampir habis", "Setelah habis, suara pindah ke cadangan dan terdengar sedikit berbeda. Bisa mulai disiapkan penutupnya."),
    "supervisor_rules": ("blue", "Pemeriksaan ucapan AI disederhanakan", "Ucapan AI sementara diperiksa dengan aturan dasar saja. Siaran tetap jalan."),
    "engine_error": ("yellow", "Ada gangguan di sistem", "Siaran tetap jalan. Lihat Detail teknis."),
}
ALERT_STAGE_CODE = {"tts": "tts_silent", "quota": "llm_fallback", "engine": "ai_failing"}
OPENING_CLOSING_TARGET_S = 180  # Opening ±3 menit, Closing ±3 menit (PRD v2.7 FR-1, §1.3.3)


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
    tts_chars: int = 0
    point_idx: int = -1  # indeks poin (batas waktu per poin); -1 di Opening/Closing atau saat timer mati


@dataclass
class Plan:
    """Posisi siaran untuk giliran yang akan DIBUAT (bisa satu langkah di depan yang diputar)."""

    segment: Segment = "opening"
    topic_idx: int = 0
    seg_turns: int = 0
    point_idx: int = 0  # poin aktif dalam topik (batas waktu per poin)
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
        ai_ids: Optional[Sequence[str]] = None,
        human_name: str = "",
    ):
        if mode == "A" and type(self) is ShowEngine:
            raise ValueError("Mode A memakai HumanLedEngine (app/show/mode_a.py)")
        if not blocker.locked:
            raise ValueError("Blocker harus dikunci sebelum live")
        self.settings, self.blocker, self.mode = settings, blocker, mode
        self.session_id = f"show_{time.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        rng = random.Random(self.seed)
        self._rng = rng
        self.participants: list[Participant] = build_participants(mode, personas, ai_ids, human_name)
        self.personas = [p.persona for p in self.participants if p.persona]  # peserta AI, urut daftar
        self.human_name = next((p.name for p in self.participants if p.is_human), "")
        self.tts = tts
        self._alerted: set[str] = set()
        self._emit_raw = emit
        self._has_owner = has_audio_owner
        self._time_scale = time_scale  # headless: 0 = tanpa menunggu (tes, harness FR-14)
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.persona_agent = PersonaAgent(llm, settings.model_for("persona"), rng, settings.PERSONA_TEMPERATURE)
        supervisor_mode = "full" if settings.PILOT_CONDITION == "D" else settings.SUPERVISOR_MODE
        self.supervisor = Supervisor(
            llm, settings.model_for("supervisor"), supervisor_mode, rng, settings.SUPERVISOR_MAX_REGEN, settings.SUPERVISOR_TIMEOUT_MS
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
        self.turn_log = TurnLog(settings.sessions_path / self.session_id)
        self.summary = ConversationSummary(llm, settings.model_for("showrunner"), settings.SUMMARY_EVERY_TURNS)

        self.state = ShowState.IDLE
        self.plan = Plan()
        self.epoch = 0
        self.turn_no = 0
        self.history: list[HistoryEntry] = []
        self.progress: dict[str, TopicProgress] = {
            t.id: TopicProgress(topic=t, is_last=i == len(blocker.topics) - 1) for i, t in enumerate(blocker.topics)
        }
        self.timed = settings.POINT_TIME_LIMIT_S > 0  # batas waktu per poin (R4); 0 = Showrunner per topik seperti sebelumnya
        self.point_clock = PointClock(settings.POINT_TIME_LIMIT_S, settings.POINT_WRAP_S, settings.TTS_WORDS_PER_SEC)
        self.point_progress: dict[tuple[str, str], TopicProgress] = {}
        self.point_played: dict[tuple[str, str], float] = {}
        self._early_close = False  # Showrunner menilai poin sudah jenuh: giliran berikutnya menutup
        self._closed_point: Optional[tuple[str, str]] = None  # mode A: poin yang baru ditutup jawaban AI, dipindah setelah pertukaran
        self._clock_running = False
        self._point_open: Optional[tuple[str, str]] = None
        self.steer_hint = ""
        self.next_speaker: Optional[str] = None
        self._last_speakers: list[str] = []
        self.transcript: list[dict[str, Any]] = []
        self.on_air: dict[str, Any] = {"segment": "opening", "topic": None, "speaking": None}
        self.last_showrunner: Optional[ShowrunnerDecision] = None
        self._on_air_pos: tuple[Segment, int] = ("opening", 0)  # posisi yang sedang terdengar
        self.started_at = 0.0
        # Jam siaran aktif (tanpa waktu jeda) untuk prompter/konsol: "Siaran m:ss / target" + cincin waktu segmen.
        self._paused_total = 0.0
        self._paused_at: Optional[float] = None
        self._ended_at: Optional[float] = None
        self._segment_started_active = 0.0
        # Diisi API saat mulai: {credits_left, per_min, used_at_start}; credits_left None = sisa tidak diketahui.
        self.tts_budget: dict[str, Any] = {}
        self._tts_low_alerted = False
        self._bg_tasks: set[asyncio.Task] = set()  # tugas latar yang harus tetap dirujuk sampai selesai
        self._resume = asyncio.Event()
        self._resume.set()
        self._playback_id: Optional[str] = None
        self._playback_done = asyncio.Event()
        self._last_play_end: Optional[float] = None
        self._task: Optional[asyncio.Task] = None
        self.error: Optional[str] = None
        self._persona_failures = 0
        self._persona_failing_since = 0.0
        self._supervisor_mode = supervisor_mode

    # ── Event dan status ─────────────────────────────────────────────────────

    async def _emit(self, type_: str, data: dict[str, Any]) -> None:
        if type_ == "topic_change":
            self._segment_started_active = self._active_s()
        try:
            await self._emit_raw(type_, data)
        except Exception as e:  # klien putus tidak boleh menghentikan siaran
            logger.warning("Emit %s gagal: %s", type_, e)
        if type_ == "topic_change":
            await self._emit("show_clock", self.show_clock())

    def tts_minutes_left(self) -> Optional[float]:
        """Perkiraan menit suara AI yang tersisa (kredit saat mulai − kredit terpakai sesi ini) ÷ laju; None bila tidak diketahui."""
        b = self.tts_budget
        if not b or b.get("credits_left") is None or not b.get("per_min"):
            return None
        used = self.tts.credits_used - b.get("used_at_start", 0)
        return max(0.0, (b["credits_left"] - used) / b["per_min"])

    def _check_tts_quota(self) -> None:
        left = self.tts_minutes_left()
        if left is None or self._tts_low_alerted or left > self.settings.TTS_QUOTA_ALERT_MIN:
            return
        self._tts_low_alerted = True
        task = asyncio.get_running_loop().create_task(self._alert("tts", f"Perkiraan sisa kredit suara ±{left:.0f} menit", "tts_quota_low"))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _active_s(self) -> float:
        """Detik siaran berjalan sejak mulai, tanpa waktu jeda."""
        if not self.started_at:
            return 0.0
        now = self._ended_at or time.monotonic()
        paused = self._paused_total + ((now - self._paused_at) if self._paused_at is not None else 0.0)
        return max(0.0, now - self.started_at - paused)

    def _segment_target_s(self) -> int:
        topic = self.on_air.get("topic")
        if self.on_air.get("segment") == "topic" and topic:
            t = next((x for x in self.blocker.topics if x.id == topic.get("id")), None)
            if t is not None:
                return t.menit * 60
        return OPENING_CLOSING_TARGET_S

    def show_clock(self) -> dict[str, Any]:
        """Jam siaran (PRD v2.7): total aktif vs target durasi, dan waktu segmen (topik/Opening/Closing)
        vs perkiraan menitnya. Klien menghitung maju sendiri selama `running`."""
        active = self._active_s()
        plan_min = OPENING_CLOSING_TARGET_S * 2 / 60 + sum(t.menit for t in self.blocker.topics)
        return {
            "elapsed_s": round(active, 1),
            "target_s": int((self.blocker.durasi_menit or plan_min) * 60),
            "segment_elapsed_s": round(max(0.0, active - self._segment_started_active), 1),
            "segment_target_s": self._segment_target_s(),
            "running": self.state == ShowState.LIVE,
        }

    def snapshot(self) -> dict[str, Any]:
        """Status lengkap untuk klien yang baru tersambung atau reload (FR-8 keandalan)."""
        topic = self.on_air.get("topic")
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "mode": self.mode,
            "blocker": {"id": self.blocker.id, "tema": self.blocker.tema, "variant_label": self.blocker.variant_label, "topics": [t.judul for t in self.blocker.topics]},
            "rundown": self._rundown(),
            "personas": [{"id": p.id, "name": p.name} for p in self.personas],
            "participants": [{"id": p.id, "name": p.name, "kind": p.kind} for p in self.participants],
            "segment": self.on_air["segment"],
            "topic": topic,
            "speaking": self.on_air.get("speaking"),
            "turn": self.turn_no,
            "elapsed_s": round(time.monotonic() - self.started_at, 1) if self.started_at else 0,
            "transcript": self.transcript[-TRANSCRIPT_KEEP:],
            "showrunner": self.last_showrunner.model_dump() if self.last_showrunner else None,
            "coverage": {tid: {"covered": sorted(p.covered), "total": len(p.topic.poin)} for tid, p in self.progress.items()},
            "topic_points": self._topic_points(),
            "tts": self.tts.status(),
            "point_clock": self._clock_payload(self._clock_running),
            "show_clock": self.show_clock(),
            "tts_minutes_left": None if (m := self.tts_minutes_left()) is None else int(m),
            "tts_quota_low": m is not None and m <= self.settings.TTS_QUOTA_ALERT_MIN,
            "error": self.error,
        }

    def _topic_points(self) -> list[dict[str, Any]]:
        """Poin topik aktif dengan centang dan penanda poin aktif (prompter, FR-11)."""
        if self.on_air.get("segment") != "topic":
            return []
        on_topic = self.on_air.get("topic")
        topic = next((t for t in self.blocker.topics if on_topic and t.id == on_topic.get("id")), None)
        if topic is None:
            topic = self.blocker.topics[self.plan.topic_idx]
        covered = self.progress[topic.id].covered
        if self.timed:
            on_point = self.on_air.get("point")
            cur = on_point["idx"] if on_point and on_point.get("topic_id") == topic.id else min(self.plan.point_idx, len(topic.poin) - 1)
            return [{"id": p.id, "text": p.text, "covered": i < cur or p.id in covered, "current": i == cur} for i, p in enumerate(topic.poin)]
        return [{"id": p.id, "text": p.text, "covered": p.id in covered} for p in topic.poin]

    def _rundown(self) -> dict[str, Any]:
        """Blocker terkunci apa adanya, untuk prompter penyiar manusia."""
        b = self.blocker
        return {
            "opening": {"hook": b.opening.hook, "poin": b.opening.poin},
            "topics": [
                {
                    "id": t.id, "judul": t.judul, "sudut_pandang": t.sudut_pandang, "menit": t.menit,
                    "poin": [{"id": p.id, "text": p.text} for p in t.poin],
                    "pertanyaan_penonton": t.pertanyaan_penonton, "transisi": t.transisi,
                }
                for t in b.topics
            ],
            "closing": {"rangkuman": b.closing.rangkuman, "ajakan": b.closing.ajakan},
        }

    async def _broadcast_state(self) -> None:
        await self._emit("state", self.snapshot())

    # ── Kontrol operator ─────────────────────────────────────────────────────

    @property
    def session_dir(self) -> Path:
        return self.settings.sessions_path / self.session_id

    def save_session_blocker(self) -> None:
        """Salin blocker terkunci ke sessions/<session_id>/blocker.json (bahan riset: apa yang dibaca AI dan penyiar)."""
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            (self.session_dir / "blocker.json").write_text(self.blocker.model_dump_json(indent=2), encoding="utf-8")
        except OSError as e:
            self.log.event("error", stage="session_blocker", message=str(e)[:300])

    def start(self) -> None:
        self.state = ShowState.LIVE
        self.started_at = time.monotonic()
        self.save_session_blocker()
        self._task = asyncio.create_task(self._run(), name=self.session_id)

    async def pause(self) -> None:
        if self.state == ShowState.LIVE:
            self.state = ShowState.PAUSED
            self._paused_at = time.monotonic()
            self._resume.clear()
            self.log.event("operator_action", action="pause")
            await self._broadcast_state()

    async def resume(self) -> None:
        if self.state == ShowState.PAUSED:
            self.state = ShowState.LIVE
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
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
        self._advance_segment("skip")
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

    def _advance_segment(self, reason: str = "advance") -> None:
        p = self.plan
        self._end_point(reason)
        p.point_idx, self._early_close, self._closed_point = 0, False, None
        self.point_clock.reset()
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
        self._sync_point_limit()

    def _pick_speaker(self) -> PersonaCard:
        """Bergiliran menurut daftar peserta AI; Showrunner boleh menunjuk `next_speaker`."""
        ids = [p.id for p in self.personas]

        def after(pid: str) -> str:
            return ids[(ids.index(pid) + 1) % len(ids)]

        if not self._last_speakers:
            choice = ids[0]
        else:
            prev = self._last_speakers[-1]
            choice = after(prev)
            if self.next_speaker in ids:
                requested = self.next_speaker
                self.next_speaker = None
                if len(ids) == 2 and requested == prev:
                    choice = after(prev)  # mode 2 AI wajib bergantian ketat
                else:
                    choice = requested
            if choice == prev:
                choice = after(prev)
        self._last_speakers.append(choice)
        return next(p for p in self.personas if p.id == choice)

    # ── Batas waktu per poin (R4) ────────────────────────────────────────────

    def _sync_point_limit(self) -> None:
        """Mode B: batas poin = menit topik ÷ jumlah poin (keputusan Favian 8 Nov 2026), minimal POINT_TIME_LIMIT_S
        dan cukup untuk giliran penutup; tanpa POINT_LIMIT_FROM_TOPIC tetap POINT_TIME_LIMIT_S (R4 asli)."""
        if not self.timed:  # mode A atau timer mati: tidak ada batas per poin
            self.point_clock.limit_s = 0
            return
        base = float(self.settings.POINT_TIME_LIMIT_S)
        limit = base
        if self.timed and self.settings.POINT_LIMIT_FROM_TOPIC and self.plan.segment == "topic":
            t = self.blocker.topics[self.plan.topic_idx]
            limit = max(base, t.menit * 60 / max(1, len(t.poin)))
        self.point_clock.limit_s = limit

    def _point_key(self) -> Optional[tuple[str, str]]:
        if not self.timed or self.plan.segment != "topic":
            return None
        topic = self.blocker.topics[self.plan.topic_idx]
        return topic.id, topic.poin[min(self.plan.point_idx, len(topic.poin) - 1)].id

    def _point_info(self, topic: BlockerTopic, idx: int) -> dict[str, Any]:
        return {"topic_id": topic.id, "point_id": topic.poin[idx].id, "idx": idx, "total": len(topic.poin), "text": topic.poin[idx].text}

    def _set_point_onair(self) -> None:
        """Mode A: poin yang terdengar = poin pada rencana (tidak ada antrean di depan)."""
        key = self._point_key()
        self.on_air["point"] = self._point_info(self.blocker.topics[self.plan.topic_idx], self.plan.point_idx) if key else None

    def _clock_payload(self, running: bool) -> dict[str, Any]:
        if not self.timed or self.state == ShowState.ENDED:
            return {"active": False}
        pos = self.on_air.get("point")
        if not pos:
            return {"active": False, "limit_s": self.point_clock.limit_s}
        played = self.point_played.get((pos["topic_id"], pos["point_id"]), 0.0)
        return {"active": True, **pos, "limit_s": self.point_clock.limit_s, "played_s": round(played, 1), "running": running, "ts": round(wall_clock(), 2)}

    async def _emit_clock(self, running: bool) -> None:
        self._clock_running = running
        if self.timed:
            await self._emit("point_clock", self._clock_payload(running))

    def _decorate_point(self, ctx: TurnContext) -> None:
        """Isi konteks giliran dengan fokus poin, anggaran kata, dan tanda giliran penutup (sisa waktu menipis)."""
        if not self.timed or ctx.segment != "topic" or ctx.topic is None:
            return
        p, topic = self.plan, ctx.topic
        i = min(p.point_idx, len(topic.poin) - 1)
        clock = self.point_clock
        ctx.point, ctx.point_no, ctx.point_total = topic.poin[i].text, i + 1, len(topic.poin)
        ctx.uncovered_points = []  # poin lain tidak disebut, supaya AI tidak melompat
        close = self._early_close or clock.should_close()
        ctx.max_words = clock.max_words()
        if close:
            ctx.close_point = True
            if i + 1 < len(topic.poin):
                ctx.next_point = topic.poin[i + 1].text
            elif p.topic_idx + 1 < len(self.blocker.topics):
                ctx.transition_to = self.blocker.topics[p.topic_idx + 1]
            else:
                ctx.to_closing = True

    def _commit_point(self, seconds: float, count_turn: bool = True, key: Optional[tuple[str, str]] = None) -> None:
        """`key` dari konteks giliran: hanya dihitung bila poin itu masih poin aktif (operator bisa memindah topik di tengah giliran)."""
        current = self._point_key()
        if current is None or (key is not None and key != current):
            return
        key = current
        if self._point_open != key:
            self._point_open = key
            self.log.event("point_start", topic_id=key[0], point_id=key[1], limit_s=self.point_clock.limit_s, turn=self.turn_no)
        self.point_clock.commit(seconds, count_turn)

    def _add_played(self, key: Optional[tuple[str, str]], seconds: float) -> None:
        if key is not None:
            self.point_played[key] = self.point_played.get(key, 0.0) + max(0.0, seconds)

    def _end_point(self, reason: str) -> None:
        """Catat akhir satu obrolan (poin): reason = timer | early | skip | advance."""
        if self._point_open is None:
            return
        topic_id, point_id = self._point_open
        c = self.point_clock
        self.log.event(
            "point_end", topic_id=topic_id, point_id=point_id, reason=reason, limit_s=c.limit_s, committed_s=round(c.committed_s, 1),
            played_s_at_close=round(self.point_played.get(self._point_open, 0.0), 1), turns=c.turns, turn=self.turn_no,
        )
        if topic_id in self.progress:
            self.progress[topic_id].covered.add(point_id)
        self._point_open = None

    def _others(self, speaker: PersonaCard) -> list[tuple[str, str]]:
        """Peserta selain `speaker`, untuk prompt persona: (nama, peran)."""
        return [(p.name, "penyiar manusia" if p.is_human else "penyiar AI") for p in self.participants if p.id != speaker.id]

    def _remember(self, entry: HistoryEntry) -> None:
        """Masukkan giliran ke riwayat dan jadwalkan pembaruan ringkasan bila giliran lama sudah keluar dari jendela."""
        self.history.append(entry)
        self.summary.schedule(self.history)

    def _context(self, speaker: PersonaCard) -> TurnContext:
        p, b = self.plan, self.blocker
        others = self._others(speaker)
        topic = b.topics[p.topic_idx] if p.segment == "topic" else None
        progress = self.progress[topic.id] if topic else None
        done = [t.judul for t in b.topics[: p.topic_idx]] if p.segment == "topic" else ([t.judul for t in b.topics] if p.segment == "closing" else [])
        ctx = TurnContext(
            blocker=b,
            segment=p.segment,
            topic=topic,
            uncovered_points=progress.uncovered if progress else [],
            history=self.history,
            partner_name=", ".join(n for n, _ in others),
            turn_in_segment=p.seg_turns,
            steer_hint=self.steer_hint,
            transition_to=b.topics[p.topic_idx + 1] if p.pending == "transition" else None,
            to_closing=p.pending == "to_closing",
            closing_final=p.segment == "closing" and p.seg_turns >= self.settings.CLOSING_TURNS - 1,
            topics_done=done,
            mode=self.mode,
            others=others if len(others) > 1 else [],  # satu lawan bicara cukup lewat partner_name
            summary=self.summary.text,
            pilot_condition=self.settings.PILOT_CONDITION,
        )
        self._decorate_point(ctx)
        if self.settings.PILOT_CONDITION == "C" and ctx.history:
            last = ctx.history[-1]
            if last.persona_id != speaker.id and detect_interrogative(last.text):
                ctx.force_no_dialog_act = True
                ctx.steer_hint = ""
                ctx.uncovered_points = []
                ctx.point = ""
        return ctx

    # ── Membuat satu giliran ─────────────────────────────────────────────────

    async def _alert(self, stage: str, message: str, code: str = "") -> None:
        """Masalah yang perlu diketahui operator, tapi siaran tetap jalan.

        Event `alert` (PRD v2.7 §6.3): `level` red|yellow|blue, `code`, `title` dan `message` dengan
        istilah UI untuk operator; pesan mentah (nama vendor/model) hanya di `detail` (Detail teknis).
        """
        self.log.event("error", stage=stage, message=message[:300])
        code = code or ALERT_STAGE_CODE.get(stage, "engine_error")
        level, title, friendly = ALERT_TEXT.get(code, ALERT_TEXT["engine_error"])
        await self._emit("alert", {
            "level": level, "code": code, "title": title, "message": friendly,
            "detail": message[:300], "stage": stage, "turn": self.turn_no, "at": wall_clock(),
        })

    async def _alert_once(self, key: str, message: str, code: str = "tts_fallback") -> None:
        if key not in self._alerted:
            self._alerted.add(key)
            await self._alert("tts", message, code)

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
            self._end_point("wrap")
            self.point_clock.reset()
            p.segment, p.seg_turns, p.pending, p.announce_closing, p.announce_topic = "closing", 0, None, True, None
            self._sync_point_limit()
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
        reviewed = await self.supervisor.check(speaker, candidate, ctx, lambda corr: self._persona_turn(speaker, ctx, corr), turn)
        latency.supervisor = int((time.perf_counter() - sup_start) * 1000)
        if self.supervisor.mode != self._supervisor_mode:
            await self._alert("quota", f"Supervisor turun ke mode {self.supervisor.mode}: {self.supervisor.last_llm_error[:120]}", "supervisor_rules")
            self._supervisor_mode = self.supervisor.mode

        if ctx.max_words:  # backstop anggaran kata: buang kalimat utuh di ujung, tidak pernah memotong kalimat
            trimmed = trim_to_budget(reviewed.text, ctx.max_words, keep_last=ctx.close_point)
            if trimmed != reviewed.text:
                self.log.event("point_trim", turn=turn, words_before=len(reviewed.text.split()), words_after=len(trimmed.split()), max_words=ctx.max_words)
                reviewed = replace(reviewed, text=trimmed)

        audio_path, duration, tts_provider, tts_reason, credits, tts_voice = None, max(1.5, len(reviewed.text.split()) / 3.0), "", "", 0, ""
        try:
            result = await self.tts.synthesize(reviewed.text, speaker.id)
            latency.tts = result.latency_ms
            audio_path = self.audio_dir / f"{self.session_id}_{turn:04d}.{result.ext}"
            audio_path.write_bytes(result.audio)
            duration, tts_provider, tts_reason, credits = result.duration_s, result.provider, result.fallback_reason, result.credit_cost
            tts_voice = result.voice.split("|")[0]
            if result.fallback_used:
                await self._alert_once(f"tts_fallback:{result.provider}", f"TTS {self.tts.primary.name} gagal ({tts_reason[:100]}); suara memakai {result.provider}")
        except (TTSError, Exception) as e:
            # Siaran tidak boleh bisu tanpa kabar: operator melihat peringatan di konsol.
            await self._alert("tts", f"Giliran {turn} tanpa suara: {str(e)[:200]}")

        final_text = reviewed.text
        if self.history and final_text.strip() and final_text.strip() == self.history[-1].text.strip():
            final_text = self.supervisor.fallback(speaker, ctx.segment, self.history)
            reviewed = replace(reviewed, text=final_text)

        record = TurnRecord(
            session_id=self.session_id,
            mode=self.mode,
            segment=ctx.segment,
            topic_id=ctx.topic.id if ctx.topic else None,
            turn=turn,
            persona=speaker.id,
            raw_text=candidate.output.text,
            final_text=final_text,
            emotion=reviewed.emotion,
            dialog_act=candidate.dialog_act,
            supervisor=reviewed.verdict,
            latency_ms=latency,
            models={"persona": candidate.model, "supervisor": self.supervisor._model if self.supervisor.mode == "full" else "", "tts": tts_provider},
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            tts_fallback_reason=tts_reason,
            tts_fallback_used=bool(tts_reason),
            audio_url=f"/audio/{audio_path.name}" if audio_path else None,
            duration_s=round(duration, 2),
            credit_cost=credits,
            seed=self.seed,
        )
        if epoch != self.epoch:  # operator skip saat giliran ini dibuat
            self._last_speakers.pop()
            return await self._produce()

        self._remember(HistoryEntry(speaker.id, speaker.name, reviewed.text))
        prepared = PreparedTurn(
            epoch, turn, speaker, ctx.segment, ctx.topic, reviewed.text, reviewed.emotion, record, audio_path, duration,
            starts_topic, starts_closing, tts_chars=len(reviewed.text) if audio_path else 0, point_idx=ctx.point_no - 1 if ctx.point else -1,
        )
        await self._after_turn(ctx, prepared, reviewed.verdict)
        return prepared

    def log_turn(
        self, *, turn: int, speaker: str, speaker_name: str, is_human: bool, segment: str, topic_id: Optional[str], text: str, raw_text: str,
        t_start: float, t_end: float, asr_ms: int, llm_ms: int, tts_ms: int, model: str, tts_chars: int, filler: Optional[str],
        supervisor_ms: int = 0, supervisor_action: str = "forward", tts_provider: str = "", tts_fallback_used: bool = False,
        dialog_act: Optional[str] = None, gap_ms: int = 0, interrupted: bool = False, tts_voice: str = "", condition: str = "A",
        user_query: str = "", draft_text: str = "", supervisor_intervened: bool = False, supervisor_verdict: Optional[dict[str, Any]] = None,
        timing_breakdown: Optional[dict[str, Any]] = None, nudge: bool = False,
    ) -> None:
        """Satu baris `sessions/<id>/turns.jsonl` (lihat turnlog.py untuk arti tiap medan)."""
        if not is_human:
            self._check_tts_quota()
        try:
            self.turn_log.write(
                session_id=self.session_id, mode=self.mode, turn_idx=turn, speaker=speaker, speaker_name=speaker_name, is_human=is_human,
                segment=segment, topic_idx=topic_index(topic_id), topic_id=topic_id, text=text, raw_text=raw_text,
                t_start=round(t_start, 3), t_end=round(t_end, 3), latency_asr_ms=asr_ms, latency_llm_ms=llm_ms, latency_supervisor_ms=supervisor_ms,
                latency_tts_ms=tts_ms, gap_before_play_ms=gap_ms, model=model, tts_chars=tts_chars, filler_used=filler,
                supervisor_action=supervisor_action, tts_provider=tts_provider, tts_fallback_used=tts_fallback_used,
                dialog_act=dialog_act, interrupted=interrupted, tts_voice=tts_voice,
                nudge=nudge,  # mode A: giliran ini memuat kode halus pindah topik (dipisah di analisis evasi)
                condition=condition, user_query=user_query, draft_text=draft_text,
                supervisor_intervened=supervisor_intervened,
                supervisor_verdict=supervisor_verdict or {},
                timing_breakdown=timing_breakdown or {
                    "asr_ms": asr_ms,
                    "persona_llm_ms": llm_ms,
                    "supervisor_ms": supervisor_ms,
                    "tts_first_chunk_ms": tts_ms,
                },
            )
        except OSError as e:
            self.log.event("error", stage="turn_log", message=str(e)[:300])

    async def _after_turn(self, ctx: TurnContext, prepared: PreparedTurn, verdict: SupervisorVerdict) -> None:
        """Perbarui rencana setelah giliran dibuat; panggil Showrunner bila waktunya."""
        p = self.plan
        if verdict.action != "forward" or verdict.rule_hits:
            self.log.event("supervisor", verdict, turn=prepared.turn, persona=prepared.persona.id, raw_text=prepared.record.raw_text, final_text=prepared.text)
            await self._emit("supervisor", {"turn": prepared.turn, "persona": prepared.persona.id, **verdict.model_dump()})

        if self.timed and ctx.segment == "topic" and ctx.point and ctx.topic is not None and p.segment == "topic":
            await self._timed_after_turn(ctx, prepared)
            return
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

    async def _timed_after_turn(self, ctx: TurnContext, prepared: PreparedTurn) -> None:
        """Batas waktu per poin: catat audio giliran, tutup poin bila giliran ini penutup, atau tanya Showrunner (penutupan dini)."""
        p, topic = self.plan, ctx.topic
        point = topic.poin[ctx.point_no - 1]
        prog = self.progress[topic.id]
        if prog.started_at is None:
            prog.started_at = time.monotonic()
        p.seg_turns += 1  # giliran ke-n dalam topik (0 = giliran pembuka topik, untuk hits_style)
        prog.turns += 1
        prog.audio_s += prepared.duration_s
        prog.history.append(self.history[-1])
        self._commit_point(prepared.duration_s)
        if ctx.close_point:
            self._end_point("early" if self._early_close else "timer")
            self._early_close = False
            if ctx.next_point:
                p.point_idx += 1
                self.point_clock.reset()
                self._sync_point_limit()
                self.steer_hint, self.next_speaker = "", None
            else:
                self._advance_segment()  # topik berikutnya atau Closing
            return
        # Showrunner menilai satu poin ini saja; waktu tetap batas atas
        pp = self.point_progress.setdefault((topic.id, point.id), TopicProgress(topic=topic.model_copy(update={"poin": [point]}), is_last=False))
        pp.turns += 1
        pp.audio_s += prepared.duration_s
        pp.history.append(self.history[-1])
        low = self.settings.POINT_MIN_TURNS
        if self.settings.SHOWRUNNER_POLICY != "llm" or pp.turns < low or (pp.turns - low) % max(1, self.settings.SHOWRUNNER_EVERY_K) != 0:
            return
        try:
            decision = await asyncio.wait_for(
                self.showrunner.decide(pp, prepared.turn, "", min_turns=low, max_turns=10**6), self.settings.SHOWRUNNER_TIMEOUT_MS / 1000
            )
        except asyncio.TimeoutError:
            return
        self.last_showrunner = decision
        self.log.event("showrunner", decision, point_id=point.id)
        await self._emit("showrunner", decision.model_dump())
        self.steer_hint = decision.steer_hint if decision.decision == "steer" else ""
        self.next_speaker = decision.next_speaker
        if decision.decision in ("transition", "close"):
            self._early_close = True

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

        point_key: Optional[tuple[str, str]] = None
        if self.timed:
            if t.point_idx >= 0 and t.topic is not None:
                self.on_air["point"] = self._point_info(t.topic, t.point_idx)
                point_key = (t.topic.id, t.topic.poin[t.point_idx].id)
            else:
                self.on_air["point"] = None
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
        t_start, completed = wall_clock(), False
        try:
            await self._emit("turn", {**entry, "audio_url": t.record.audio_url, "duration_s": t.duration_s, "playback_id": self._playback_id})
            await self._emit_clock(True)
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
            completed = True
            self._add_played(point_key, t.duration_s)
            await self._emit_clock(False)
        finally:
            self.on_air["speaking"] = None
            # Klien selain pemutar (konsol, prompter) perlu tahu giliran selesai; pemutar hanya melapor "started".
            await self._emit("speaking", {"persona": None})
            self._last_play_end = time.monotonic()
            self.log_turn(
                turn=t.turn, speaker=t.persona.id, speaker_name=t.persona.name, is_human=False, segment=t.segment,
                topic_id=t.topic.id if t.topic else None, text=t.text, raw_text=t.record.raw_text,
                t_start=t_start, t_end=wall_clock(), asr_ms=0, llm_ms=t.record.latency_ms.persona, supervisor_ms=t.record.latency_ms.supervisor,
                tts_ms=t.record.latency_ms.tts, model=t.record.models.get("persona", ""), tts_chars=t.tts_chars, filler=None,
                supervisor_action=t.record.supervisor.action, tts_provider=t.record.tts_provider, tts_fallback_used=t.record.tts_fallback_used,
                dialog_act=t.record.dialog_act, gap_ms=gap, interrupted=not completed, tts_voice=t.record.tts_voice,
                condition=self.settings.PILOT_CONDITION, draft_text=t.record.raw_text,
                supervisor_verdict=t.record.supervisor.model_dump(mode="json"),
                supervisor_intervened=t.record.supervisor.action != "forward",
                timing_breakdown={
                    "asr_ms": 0,
                    "persona_llm_ms": t.record.latency_ms.persona,
                    "supervisor_ms": t.record.latency_ms.supervisor,
                    "tts_first_chunk_ms": t.record.latency_ms.tts,
                },
            )

    # ── Loop utama ───────────────────────────────────────────────────────────

    async def _run(self) -> None:
        self.log.event(
            "session_start",
            mode=self.mode,
            seed=self.seed,
            blocker=self.blocker.model_dump(mode="json"),
            personas=[p.id for p in self.personas],
            participants=[{"id": p.id, "name": p.name, "kind": p.kind} for p in self.participants],
            voices={p.id: self.tts.voice_for(p.id) for p in self.personas},
            config={k: getattr(self.settings, k) for k in (
                "LLM_MODE", "TTS_MODE", "TTS_PROVIDER", "TTS_FALLBACK", "SUPERVISOR_MODE", "SHOWRUNNER_POLICY", "SHOWRUNNER_EVERY_K",
                "MIN_TURNS_PER_TOPIC", "MAX_TURNS_PER_TOPIC", "FIXED_TURNS_PER_TOPIC", "PIPELINE_DEPTH", "OPENING_TURNS", "CLOSING_TURNS",
                "SUMMARY_EVERY_TURNS", "POINT_TIME_LIMIT_S", "POINT_WRAP_S", "POINT_MIN_TURNS", "TTS_WORDS_PER_SEC")},
            models={r: self.settings.model_for(r) for r in ("persona", "supervisor", "showrunner")},
            prompts={a.prompt.name: a.prompt.version for a in (self.persona_agent, self.supervisor, self.showrunner)},
        )
        for warning in self.tts.warnings:  # mis. ELEVENLABS_API_KEY kosong → jatuh ke Edge
            await self._alert("tts", warning, "tts_warning")
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
        self._ended_at = time.monotonic()
        self._resume.set()
        self.summary.cancel()
        self._end_point("stop" if reason == "stopped" else "end")
        self.on_air["point"] = None
        await self._emit_clock(False)
        self.log.event(
            "session_end",
            reason=reason,
            turns=self.turn_no,
            elapsed_s=round(time.monotonic() - self.started_at, 1),
            credits_used=self.tts.credits_used,
            ledger=[e.model_dump() for e in self.supervisor.ledger],
        )
        await self._broadcast_state()
