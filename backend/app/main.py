"""FastAPI: REST API generator blocker, health, dan router live (app/show/api.py).

Jalankan dari folder backend/: `uvicorn app.main:app --reload --port 8000`.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.blocker import (
    BlockerGenerationError,
    BlockerGenerator,
    BlockerInvalid,
    BlockerLocked,
    BlockerNotFound,
    BlockerStore,
)
from app.blocker.store import now_iso
from app.config import Settings, get_settings
from app.llm import create_llm_client
from app.schemas import Blocker, GenerateBlockerRequest
from app.show.api import router as show_router
from app.tts import create_tts
from app.ws import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


class RegenerateRequest(BaseModel):
    hindari: list[str] = Field(default_factory=list, description="variant_label varian lain yang sedang tampil")


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        llm = create_llm_client(settings)
        store = BlockerStore(settings.DATA_DIR)
        app.state.settings = settings
        app.state.llm = llm
        app.state.store = store
        app.state.generator = BlockerGenerator(llm, settings.model_for("blocker"), store)
        app.state.tts = create_tts(settings)
        app.state.ws = ConnectionManager()
        app.state.engine = None
        Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
        logger.info("Siap: LLM_MODE=%s TTS_MODE=%s", settings.LLM_MODE, settings.TTS_MODE)
        yield
        if app.state.engine is not None:
            await app.state.engine.stop()

    app = FastAPI(title="Penyiar AI v2", lifespan=lifespan)
    app.include_router(show_router)

    @app.exception_handler(BlockerNotFound)
    async def _not_found(_: Request, e: BlockerNotFound):
        return JSONResponse({"detail": f"Blocker {e.args[0]} tidak ditemukan"}, status_code=404)

    @app.exception_handler(BlockerLocked)
    async def _locked(_: Request, e: BlockerLocked):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(BlockerInvalid)
    async def _invalid(_: Request, e: BlockerInvalid):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(BlockerGenerationError)
    async def _gen_failed(_: Request, e: BlockerGenerationError):
        return JSONResponse({"detail": str(e), "issues": e.issues}, status_code=502)

    def log_generation(app: FastAPI, kind: str, tema: str, meta, blockers: list[Blocker]) -> None:
        line = {
            "ts": now_iso(),
            "type": kind,
            "tema": tema,
            "model": meta.model,
            "prompt_version": meta.prompt_version,
            "latency_ms": meta.latency_ms,
            "attempts": meta.attempts,
            "issues_first_attempt": meta.issues_first_attempt,
            "blocker_ids": [b.id for b in blockers],
        }
        with open(Path(app.state.settings.LOG_DIR) / "blocker_generations.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    @app.get("/api/health")
    async def health(request: Request):
        s: Settings = request.app.state.settings
        llm = request.app.state.llm
        limiters = getattr(llm, "limiters", None)
        return {
            "llm_mode": s.LLM_MODE,
            "tts_mode": s.TTS_MODE,
            "models": {role: s.model_for(role) for role in ("blocker", "persona", "showrunner", "supervisor")},
            "quota": limiters.status() if limiters else {},
            "tts": request.app.state.tts.status(),
            "show": request.app.state.engine.state.value if request.app.state.engine else "idle",
            "output": request.app.state.ws.output_status(),
        }

    @app.post("/api/blocker/generate")
    async def generate(req: GenerateBlockerRequest, request: Request):
        blockers, meta = await request.app.state.generator.generate(req)
        log_generation(request.app, "generate", req.tema, meta, blockers)
        return {"variants": blockers, "latency_ms": meta.latency_ms, "attempts": meta.attempts, "model": meta.model}

    @app.get("/api/blockers")
    async def list_blockers(request: Request, generation_id: str | None = None, locked: bool | None = None):
        return request.app.state.store.list(generation_id=generation_id, locked=locked)

    @app.get("/api/blocker/{blocker_id}")
    async def get_blocker(blocker_id: str, request: Request) -> Blocker:
        return request.app.state.store.get(blocker_id)

    @app.put("/api/blocker/{blocker_id}")
    async def update_blocker(blocker_id: str, edited: Blocker, request: Request) -> Blocker:
        return request.app.state.store.update(blocker_id, edited)

    @app.post("/api/blocker/{blocker_id}/lock")
    async def lock_blocker(blocker_id: str, request: Request) -> Blocker:
        return request.app.state.store.lock(blocker_id)

    @app.post("/api/blocker/{blocker_id}/version")
    async def new_version(blocker_id: str, request: Request) -> Blocker:
        return request.app.state.store.new_version(blocker_id)

    @app.post("/api/blocker/{blocker_id}/regenerate")
    async def regenerate(blocker_id: str, body: RegenerateRequest, request: Request):
        store: BlockerStore = request.app.state.store
        if store.get(blocker_id).locked:
            raise HTTPException(409, "Blocker terkunci tidak dibuat ulang; buat versi baru")
        blocker, meta = await request.app.state.generator.regenerate_variant(blocker_id, body.hindari)
        log_generation(request.app, "regenerate", blocker.tema, meta, [blocker])
        return {"variant": blocker, "latency_ms": meta.latency_ms, "attempts": meta.attempts, "model": meta.model}

    return app


app = build_app()
