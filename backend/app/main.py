"""FastAPI: REST API generator blocker, health, dan router live (app/show/api.py).

Jalankan dari folder backend/: `uvicorn app.main:app --reload --port 8000`.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sqlalchemy import insert

from app.admin import router as admin_router
from app.auth import AuthService, require_role, user_from_conn
from app.auth import router as auth_router
from app.blocker import (
    BlockerGenerationError,
    BlockerGenerator,
    BlockerInvalid,
    BlockerLocked,
    BlockerNotFound,
    BlockerStore,
)
from app.blocker.store import now_iso
from app.config import REPO_ROOT, Settings, get_settings
from app.content import content
from app.db import database_for, generation_log
from app.llm import create_llm_client
from app.llm.quota import QuotaCounter
from app.runtime_config import RuntimeConfig
from app.schemas import Blocker, GenerateBlockerRequest, ShowState
from app.secretbox import SecretBox
from app.show.api import router as show_router
from app.tts import create_tts
from app.tuning import tuning
from app.tts.catalog import catalog as voice_catalog
from app.ws import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


class RegenerateRequest(BaseModel):
    blocker: Blocker = Field(description="varian yang dibuat ulang (boleh belum disimpan)")
    hindari: list[str] = Field(default_factory=list, description="variant_label varian lain yang sedang tampil")


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Semua data aplikasi ada di database (Postgres di hosting, SQLite lokal): pengguna, sesi login, materi, setelan
        # admin, persona, prompt, kata terlarang, kuota, dan log siaran. Berkas hanya untuk cache audio.
        db = database_for(settings)
        app.state.db = db
        app.state.quota = QuotaCounter(db, settings.rpd_for_model)
        app.state.auth = AuthService(db, settings)
        app.state.settings = settings
        app.state.engine = None
        # Konten (persona, prompt, kata terlarang) dan katalog suara dibaca dari database; data awal diisi sekali dari backend/seed.
        content.configure(db)
        voice_catalog.configure(db)
        tuning.configure(settings)
        # Setelan dari halaman admin menimpa .env; diterapkan SEBELUM klien LLM/TTS dibuat.
        app.state.runtime_config = RuntimeConfig(db, settings, SecretBox(settings.SECRETS_KEY))
        app.state.runtime_config.apply_to_settings()
        llm = create_llm_client(settings, quota=app.state.quota)
        app.state.llm = llm
        app.state.store = BlockerStore(db)
        app.state.generator = BlockerGenerator(llm, settings.model_for("blocker"))
        app.state.tts = create_tts(settings)
        app.state.ws = ConnectionManager()
        logger.info(
            "Siap: LLM_MODE=%s TTS_MODE=%s database=%s login=%s", settings.LLM_MODE, settings.TTS_MODE,
            db.dialect, "wajib" if settings.AUTH_REQUIRED else "MATI (hanya untuk pengembangan)",
        )
        yield
        if app.state.engine is not None:
            await app.state.engine.stop()
        # Kembali ke seed supaya modul-modul ini tidak menunjuk database aplikasi yang sudah berhenti (penting untuk tes).
        content.configure(None)
        voice_catalog.configure(None)
        tuning.configure(None)

    app = FastAPI(title="Penyiar AI v2", lifespan=lifespan)
    app.include_router(show_router)
    app.include_router(auth_router)
    app.include_router(admin_router)

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
        with app.state.db.engine.begin() as conn:
            conn.execute(insert(generation_log).values(ts=line["ts"], data=line))

    @app.get("/api/health")
    def health(request: Request):
        s: Settings = request.app.state.settings
        if user_from_conn(request) is None:
            # Cek kesehatan Docker dan deploy otomatis tanpa login: tanpa rincian model/kuota. `live` supaya
            # deploy tidak memulai ulang aplikasi di tengah siaran (restart = siaran berhenti).
            engine = request.app.state.engine
            return {"status": "ok", "live": engine is not None and engine.state in (ShowState.LIVE, ShowState.PAUSED)}
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
    async def generate(req: GenerateBlockerRequest, request: Request, _=Depends(require_role("operator"))):
        blockers, meta = await request.app.state.generator.generate(req)
        log_generation(request.app, "generate", req.tema, meta, blockers)
        return {"variants": blockers, "latency_ms": meta.latency_ms, "attempts": meta.attempts, "model": meta.model}

    @app.get("/api/blockers")
    async def list_blockers(request: Request, generation_id: str | None = None, locked: bool | None = None, _=Depends(require_role("operator"))):
        return request.app.state.store.list(generation_id=generation_id, locked=locked)

    @app.post("/api/blockers", status_code=201)
    async def save_chosen(blocker: Blocker, request: Request, _=Depends(require_role("operator"))) -> Blocker:
        """Simpan varian hasil generate yang dipilih operator. Aman diulang; yang sudah terkunci tidak ditimpa."""
        return request.app.state.store.create_draft(blocker)

    @app.get("/api/blocker/{blocker_id}")
    async def get_blocker(blocker_id: str, request: Request, _=Depends(require_role("operator"))) -> Blocker:
        return request.app.state.store.get(blocker_id)

    @app.put("/api/blocker/{blocker_id}")
    async def update_blocker(blocker_id: str, edited: Blocker, request: Request, _=Depends(require_role("operator"))) -> Blocker:
        return request.app.state.store.update(blocker_id, edited)

    @app.post("/api/blocker/{blocker_id}/lock")
    async def lock_blocker(blocker_id: str, request: Request, _=Depends(require_role("operator"))) -> Blocker:
        return request.app.state.store.lock(blocker_id)

    @app.post("/api/blocker/{blocker_id}/version")
    async def new_version(blocker_id: str, request: Request, _=Depends(require_role("operator"))) -> Blocker:
        return request.app.state.store.new_version(blocker_id)

    @app.post("/api/blocker/regenerate")
    async def regenerate(body: RegenerateRequest, request: Request, _=Depends(require_role("operator"))):
        if body.blocker.locked:
            raise HTTPException(409, "Blocker terkunci tidak dibuat ulang; buat versi baru")
        blocker, meta = await request.app.state.generator.regenerate_variant(body.blocker, body.hindari)
        log_generation(request.app, "regenerate", blocker.tema, meta, [blocker])
        return {"variant": blocker, "latency_ms": meta.latency_ms, "attempts": meta.attempts, "model": meta.model}

    _serve_frontend(app, settings)
    return app


API_PREFIXES = ("api/", "ws/", "audio/")


def _serve_frontend(app: FastAPI, settings: Settings) -> None:
    """Sajikan frontend hasil build (hosting: satu proses menyajikan API dan halaman).

    Rute klien (/, /stage, /prompter, ...) memakai riwayat browser, jadi path yang bukan berkas dijawab index.html.
    Path API tidak pernah ditimpa: yang tidak dikenal tetap 404. Tanpa build frontend (pengembangan) fungsi ini tidak
    melakukan apa pun; Vite yang menyajikan halaman.
    """
    dist = Path(settings.FRONTEND_DIST) if settings.FRONTEND_DIST else REPO_ROOT / "frontend" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith(API_PREFIXES):
            raise HTTPException(404, "Tidak ditemukan")
        target = (dist / path).resolve()
        if path and target.is_file() and root in target.parents:
            return FileResponse(target)
        return FileResponse(index)


app = build_app()
