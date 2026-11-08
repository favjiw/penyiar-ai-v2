"""REST + WebSocket untuk live (PRD §6.3–6.4): start/next/pause/resume/stop, audio, log."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.blocker.store import BlockerInvalid
from app.data.personas import load_personas
from app.schemas import PrecheckRequest, PTTTurnRequest, ShowState, StartShowRequest, VoiceSampleRequest
from app.session_log import read_log
from app.show.engine import ShowEngine
from app.show.mode_a import HumanLedEngine
from app.show.participants import DEFAULT_AI_IDS
from app.tts.base import TTSError
from app.tts.catalog import load_voice_catalog
from app.ws import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def audio_dir(request_or_ws) -> Path:
    return Path(request_or_ws.app.state.settings.CACHE_DIR) / "audio"


def current(request: Request) -> Optional[ShowEngine]:
    return request.app.state.engine


def require_engine(request: Request) -> ShowEngine:
    engine = current(request)
    if engine is None or engine.state == ShowState.ENDED:
        raise HTTPException(409, "Tidak ada siaran yang sedang berjalan")
    return engine


@router.post("/api/show/start")
async def start_show(req: StartShowRequest, request: Request):
    app = request.app
    running = current(request)
    if running is not None and running.state != ShowState.ENDED:
        raise HTTPException(409, f"Siaran {running.session_id} masih berjalan; stop dulu")
    personas = load_personas()
    if req.mode == "A" and req.ai_persona not in personas:
        raise HTTPException(422, "Mode A: pilih ai_persona raka atau salsa")  # sebelum mengunci apa pun
    ai_ids = [req.ai_persona] if req.mode == "A" else list(DEFAULT_AI_IDS)
    try:
        app.state.tts.check_voices(req.voices, ai_ids)  # sebelum mengunci apa pun; diterapkan sesudah lolos semua cek
    except TTSError as e:
        raise HTTPException(422, str(e))
    blocker = app.state.store.get(req.blocker_id)
    if not blocker.locked:
        # Blocking terkunci begitu live dimulai (draf hasil generate boleh langsung dipakai tanpa edit).
        try:
            blocker = app.state.store.lock(req.blocker_id)
        except BlockerInvalid as e:
            raise HTTPException(422, str(e))
    app.state.tts.set_voices(req.voices, ai_ids)
    ws: ConnectionManager = app.state.ws
    common = dict(seed=req.seed, has_audio_owner=lambda: ws.audio_owner() is not None)
    if req.mode == "A":
        human_name = req.human_name or app.state.settings.HUMAN_HOST_NAME
        engine: ShowEngine = HumanLedEngine(
            app.state.settings, app.state.llm, app.state.tts, blocker, emit=ws.broadcast, audio_dir=audio_dir(request),
            personas=personas, human_name=human_name, ai_persona=req.ai_persona, **common,
        )
    else:
        engine = ShowEngine(
            app.state.settings, app.state.llm, app.state.tts, blocker, personas, ws.broadcast, audio_dir(request), mode="B", **common
        )
    app.state.engine = engine
    engine.start()
    return engine.snapshot()


@router.get("/api/show")
async def show_state(request: Request):
    engine = current(request)
    return engine.snapshot() if engine else {"state": ShowState.IDLE.value}


@router.post("/api/show/undo-topic")
async def undo_topic(request: Request):
    """Batalkan pindah topik dari ucapan penyiar (mode A, PRD v2.7 §6.4); 409 bila sudah lewat atau tidak ada."""
    engine = require_engine(request)
    if not isinstance(engine, HumanLedEngine) or not await engine.undo_topic():
        raise HTTPException(409, "Tidak ada pindah topik dari ucapan yang bisa dibatalkan")
    return engine.snapshot()


@router.post("/api/show/{action}")
async def control(action: str, request: Request):
    engine = require_engine(request)
    handlers = {"pause": engine.pause, "resume": engine.resume, "next": engine.skip, "skip": engine.skip, "stop": engine.stop}
    if action not in handlers:
        raise HTTPException(404, f"Aksi {action} tidak dikenal")
    await handlers[action]()
    return engine.snapshot()


@router.post("/api/ptt/turn")
async def ptt_turn(req: PTTTurnRequest, request: Request):
    """Transkrip final push-to-talk dari prompter (FR-7, STT di browser)."""
    engine = require_engine(request)
    if not isinstance(engine, HumanLedEngine):
        raise HTTPException(409, "PTT hanya untuk mode A")
    if engine.state != ShowState.LIVE:
        raise HTTPException(409, "Siaran sedang pause")
    return await engine.human_turn(req.text, req.stt_ms, req.speech_ms) or {}


@router.get("/api/voices")
async def voices(request: Request):
    """Daftar suara terkurasi + suara aktif per persona (untuk pilihan operator sebelum live)."""
    tts = request.app.state.tts
    return {
        "provider": tts.primary.name,
        "voices": load_voice_catalog(),
        "current": {p: tts.voice_for(p) for p in load_personas()},
    }


SAMPLE_TEXT = "Halo Sobat Hits, gue {name}. Yuk ngobrol santai bareng gue hari ini!"


@router.post("/api/voices/sample")
async def voice_sample(req: VoiceSampleRequest, request: Request):
    """Contoh suara untuk tombol "Dengar" sebelum live (PRD v2.7 FR-6). Tidak tersedia saat siaran berjalan."""
    running = current(request)
    if running is not None and running.state != ShowState.ENDED:
        raise HTTPException(409, "Contoh suara hanya bisa diputar sebelum live")
    personas = load_personas()
    if req.persona not in personas:
        raise HTTPException(422, f"Persona {req.persona!r} tidak dikenal")
    tts = request.app.state.tts
    try:
        tts.set_voices({req.persona: req.voice_id} if req.voice_id else {}, list(DEFAULT_AI_IDS))
        result = await tts.synthesize(SAMPLE_TEXT.format(name=personas[req.persona].name), req.persona)
    except TTSError as e:
        raise HTTPException(422, str(e)[:300])
    name = f"sample_{req.persona}_{hashlib.sha1(result.voice.encode()).hexdigest()[:10]}.{result.ext}"
    path = audio_dir(request) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.audio)
    # fallback=True: suara utama gagal, yang terdengar adalah suara cadangan (bukan suara yang dipilih).
    return {"audio_url": f"/audio/{name}", "voice": result.voice.split("|")[0], "provider": result.provider, "fallback": result.fallback_used}


@router.post("/api/precheck")
async def precheck(request: Request, req: Optional[PrecheckRequest] = None):
    """Cek pra-live (§5.1): model terisi, TTS dipanaskan (cold start suara library)."""
    app = request.app
    running = current(request)
    if req is not None and (running is None or running.state == ShowState.ENDED):
        try:  # panaskan suara yang dipilih (kosong = bawaan); tidak menyentuh pilihan selama siaran berjalan
            app.state.tts.set_voices(req.voices, list(DEFAULT_AI_IDS))
        except TTSError as e:
            raise HTTPException(422, str(e))
    s = app.state.settings
    personas = load_personas()
    result = {
        "llm_mode": s.LLM_MODE,
        "models": {r: s.model_for(r) for r in ("persona", "supervisor", "showrunner")},
        "models_ok": s.LLM_MODE == "mock" or all(s.model_for(r) for r in ("persona", "showrunner")) and (s.SUPERVISOR_MODE != "full" or bool(s.model_for("supervisor"))),
        "output": app.state.ws.output_status(),
    }
    try:
        result["tts_warmup_ms"] = await app.state.tts.warm_up(list(personas))
        result["tts_ok"] = True
    except Exception as e:
        result["tts_ok"], result["tts_error"] = False, str(e)[:300]
    result["tts"] = app.state.tts.status()
    return result


@router.get("/audio/{filename}")
async def serve_audio(filename: str, request: Request):
    path = audio_dir(request) / filename
    if not _SAFE_NAME.match(filename) or not path.exists():
        raise HTTPException(404, "Audio tidak ditemukan")
    return FileResponse(path, media_type="audio/mpeg" if filename.endswith(".mp3") else "audio/wav")


@router.get("/api/logs")
async def list_logs(request: Request):
    log_dir = Path(request.app.state.settings.LOG_DIR)
    return [{"session_id": f.stem, "size_bytes": f.stat().st_size} for f in sorted(log_dir.glob("show_*.jsonl"), reverse=True)]


@router.get("/api/logs/{session_id}")
async def get_log(session_id: str, request: Request):
    path = Path(request.app.state.settings.LOG_DIR) / f"{session_id}.jsonl"
    if not _SAFE_NAME.match(session_id) or not path.exists():
        raise HTTPException(404, "Log tidak ditemukan")
    return list(read_log(path))


@router.websocket("/ws/session")
async def ws_session(ws: WebSocket, role: str = "console"):
    manager: ConnectionManager = ws.app.state.ws
    previous_owner = manager.audio_owner()
    await manager.connect(ws, role)
    try:
        engine: Optional[ShowEngine] = ws.app.state.engine
        await manager.send(ws, "state", engine.snapshot() if engine else {"state": ShowState.IDLE.value})
        await _routing_changed(ws.app, previous_owner)
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except ValueError:
                continue
            action, data = msg.get("action"), msg.get("data") or {}
            engine = ws.app.state.engine
            if action == "ping":
                await manager.send(ws, "pong", {})
            elif action == "playback" and ws is manager.audio_owner() and engine:
                engine.playback_feedback(data)
                if data.get("status") == "started":
                    await manager.broadcast("speaking", {"persona": data.get("persona")})
            elif action == "stt_partial":
                # Transkrip sementara dari prompter, diteruskan ke konsol (FR-7)
                await manager.broadcast("stt_partial", {"text": str(data.get("text", ""))[:500], "final": bool(data.get("final")), "active": data.get("active")})
            elif action == "audio_state":
                blocked = bool(data.get("blocked"))
                (manager.audio_blocked.add if blocked else manager.audio_blocked.discard)(ws)
                if "ready" in data:
                    (manager.audio_ready.add if data.get("ready") else manager.audio_ready.discard)(ws)
                await manager.broadcast_output_status()
            elif action == "mic_state" and manager.clients.get(ws) == "prompter":
                # Prompter memantau mic studio (PRD v2.7 FR-7); konsol menampilkan peringatan merah bila putus.
                state = {"down": bool(data.get("down")), "reason": str(data.get("reason", ""))[:20]}
                if manager.mic.get(ws) != state:
                    manager.mic[ws] = state
                    await manager.broadcast_output_status()
            elif action == "level" and ws is manager.audio_owner():
                # Level audio dari stage (pemilik audio) diteruskan ke konsol/prompter (indikator bicara).
                try:
                    lv = max(0.0, min(1.0, float(data.get("level", 0))))
                except (TypeError, ValueError):
                    continue
                await manager.broadcast("level", {"persona": data.get("persona"), "level": round(lv, 2)})
    except WebSocketDisconnect:
        pass
    finally:
        previous_owner = manager.audio_owner()
        manager.disconnect(ws)
        await _routing_changed(ws.app, previous_owner)


async def _routing_changed(app, previous_owner) -> None:
    manager: ConnectionManager = app.state.ws
    if manager.audio_owner() is not previous_owner and app.state.engine:
        app.state.engine.release_playback()
    await manager.broadcast_output_status()
