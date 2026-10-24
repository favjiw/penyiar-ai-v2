"""REST + WebSocket untuk live (PRD §6.3–6.4): start/next/pause/resume/stop, audio, log."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.data.personas import load_personas
from app.schemas import ShowState, StartShowRequest
from app.session_log import read_log
from app.show.engine import ShowEngine
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
    blocker = app.state.store.get(req.blocker_id)
    if not blocker.locked:
        raise HTTPException(422, "Kunci blocker dulu sebelum live")
    if req.mode != "B":
        raise HTTPException(422, "Mode A dikerjakan di Tahap 4")
    ws: ConnectionManager = app.state.ws
    engine = ShowEngine(
        app.state.settings,
        app.state.llm,
        app.state.tts,
        blocker,
        load_personas(),
        ws.broadcast,
        audio_dir(request),
        mode=req.mode,
        seed=req.seed,
        has_audio_owner=lambda: ws.audio_owner() is not None,
    )
    app.state.engine = engine
    engine.start()
    return engine.snapshot()


@router.get("/api/show")
async def show_state(request: Request):
    engine = current(request)
    return engine.snapshot() if engine else {"state": ShowState.IDLE.value}


@router.post("/api/show/{action}")
async def control(action: str, request: Request):
    engine = require_engine(request)
    handlers = {"pause": engine.pause, "resume": engine.resume, "next": engine.skip, "skip": engine.skip, "stop": engine.stop}
    if action not in handlers:
        raise HTTPException(404, f"Aksi {action} tidak dikenal")
    await handlers[action]()
    return engine.snapshot()


@router.post("/api/precheck")
async def precheck(request: Request):
    """Cek pra-live (§5.1): model terisi, TTS dipanaskan (cold start suara library), stage tersambung."""
    app = request.app
    s = app.state.settings
    personas = load_personas()
    result = {
        "llm_mode": s.LLM_MODE,
        "models": {r: s.model_for(r) for r in ("persona", "supervisor", "showrunner")},
        "models_ok": s.LLM_MODE == "mock" or all(s.model_for(r) for r in ("persona", "showrunner")) and (s.SUPERVISOR_MODE != "full" or bool(s.model_for("supervisor"))),
        "output": app.state.ws.output_status(),
    }
    try:
        result["tts_warmup_ms"] = await app.state.tts.warm_up({p.gender: p.voices for p in personas.values()})
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
            elif action == "audio_state":
                blocked = bool(data.get("blocked"))
                (manager.audio_blocked.add if blocked else manager.audio_blocked.discard)(ws)
                await manager.broadcast_output_status()
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
