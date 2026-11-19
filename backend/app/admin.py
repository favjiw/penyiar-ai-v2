"""API halaman admin: setelan (kunci Gemini, model, suara Edge TTS) dan katalog suara gratis.

Semua rute hanya untuk admin. Nilai kunci API tidak pernah dikirim balik (hanya "••••" + 4 karakter terakhir).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import User, require_role
from app.config import Settings
from app.content import content
from app.schemas import PersonaCard
from app.session_log import read_events, session_detail, session_page
from app.runtime_config import ConfigError, RuntimeConfig, apply_if_idle, show_is_live
from app.tts.catalog import VoiceError, VoiceOption, catalog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")
admin = Depends(require_role("admin"))

VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def _cfg(request: Request) -> RuntimeConfig:
    cfg = getattr(request.app.state, "runtime_config", None)
    if cfg is None:
        raise HTTPException(404, "Halaman admin butuh database (DATABASE_URL atau AUTH_REQUIRED)")
    return cfg


# ── Setelan ──────────────────────────────────────────────────────────────────
def _config_response(request: Request, **extra) -> dict:
    cfg = _cfg(request)
    return {**cfg.describe(), "live": show_is_live(request.app), **extra}


@router.get("/config")
def get_config(request: Request, _: User = admin):
    apply_if_idle(request.app)  # setelan yang menunggu siaran selesai
    return _config_response(request)


class ConfigUpdate(BaseModel):
    # kunci -> nilai baru; null = hapus timpaan (kembali ke .env); kunci rahasia "" = biarkan
    values: dict[str, Optional[str]] = Field(default_factory=dict)


@router.put("/config")
def put_config(body: ConfigUpdate, request: Request, user: User = admin):
    cfg = _cfg(request)
    try:
        changed = cfg.set_values(body.values, by=user.username)
    except ConfigError as e:
        raise HTTPException(422, str(e)) from e
    error = apply_if_idle(request.app)
    live = show_is_live(request.app)
    return _config_response(request, changed=changed, applied=bool(changed) and not cfg.pending, apply_error=error, live=live)


# ── Uji koneksi ──────────────────────────────────────────────────────────────
def _result(ok: bool, message: str) -> dict:
    return {"ok": ok, "message": message}


async def _test_gemini(s: Settings) -> dict:
    from app.llm import create_llm_client

    if s.LLM_MODE == "mock":
        return _result(True, "Server berjalan dalam mode uji (LLM_MODE=mock): kunci tidak dipakai.")
    if not s.GEMINI_API_KEY:
        return _result(False, "Kunci API Gemini belum diisi.")
    model = s.model_for("persona")
    if not model:
        return _result(False, "Model penyiar AI belum diisi.")
    try:
        llm = create_llm_client(s)
        resp = await llm.generate("Balas dengan satu kata: ok", model=model, temperature=0.0)
    except Exception as e:  # noqa: BLE001 - pesan galat provider ditampilkan apa adanya (dipotong)
        return _result(False, f"Gagal memanggil {model}: {str(e)[:200]}")
    return _result(True, f"Berhasil memanggil {model} ({len(resp.raw)} karakter jawaban). Memakai 1 permintaan kuota.")


async def _test_edge(s: Settings) -> dict:
    from app.data.personas import load_personas
    from app.tts.provider import EdgeTTSProvider
    from app.tts.voices import VoiceBook

    if s.TTS_MODE == "mock":
        return _result(True, "Server berjalan dalam mode uji (TTS_MODE=mock): Edge TTS tidak dipanggil.")
    try:
        res = await EdgeTTSProvider(VoiceBook(s, load_personas())).synthesize("Halo, ini tes Edge TTS.", "raka")
    except Exception as e:  # noqa: BLE001
        return _result(False, f"Gagal menghubungi Edge TTS: {str(e)[:200]}")
    return _result(True, f"Edge TTS aktif ({res.voice}, {res.latency_ms} ms).")


TESTS = {"gemini": _test_gemini, "edge": _test_edge}


@router.post("/test/{service}")
async def test_service(service: Literal["gemini", "edge"], request: Request, _: User = admin):
    """Uji dengan setelan yang TERSIMPAN (termasuk yang menunggu siaran selesai), bukan yang sedang berjalan."""
    cfg = _cfg(request)
    s = request.app.state.settings.model_copy(update=cfg.effective())
    return await TESTS[service](s)


# ── Katalog suara ────────────────────────────────────────────────────────────
class VoiceCreate(BaseModel):
    id: str
    provider: Literal["edge"] = "edge"
    name: str = ""
    gender: Literal["male", "female"]
    notes: str = ""


class VoicePatch(BaseModel):
    name: Optional[str] = None
    gender: Optional[Literal["male", "female"]] = None
    notes: Optional[str] = None


@router.get("/voices")
def list_voices(_: User = admin):
    return catalog.all()


@router.post("/voices", status_code=201)
async def add_voice(body: VoiceCreate, _: User = admin):
    if not VOICE_ID_RE.match(body.id.strip()):
        raise HTTPException(422, "ID suara hanya boleh huruf, angka, strip, dan garis bawah (4-80 karakter)")
    name, notes = body.name.strip(), body.notes.strip()
    try:
        voice = catalog.add(VoiceOption(id=body.id, provider="edge", name=name, gender=body.gender, notes=notes))
    except VoiceError as e:
        raise HTTPException(422, str(e)) from e
    return {"voice": voice, "warning": None}


@router.patch("/voices/{voice_id}")
def patch_voice(voice_id: str, body: VoicePatch, _: User = admin):
    try:
        return catalog.update(voice_id, name=body.name, gender=body.gender, notes=body.notes)
    except KeyError:
        raise HTTPException(404, "Suara tidak ditemukan") from None
    except VoiceError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/voices/{voice_id}")
def delete_voice(voice_id: str, _: User = admin):
    try:
        catalog.remove(voice_id)
    except KeyError:
        raise HTTPException(404, "Suara tidak ditemukan") from None
    except VoiceError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


# ── Persona ──────────────────────────────────────────────────────────────────
@router.get("/personas")
def list_personas(_: User = admin):
    return list(content.personas().values())


@router.put("/personas/{persona_id}")
def put_persona(persona_id: str, card: PersonaCard, _: User = admin):
    """Ubah kartu persona. Yang berubah dipakai siaran berikutnya (hash persona dicatat di log sesi)."""
    if persona_id not in content.personas():
        raise HTTPException(404, "Persona tidak ditemukan")
    if card.id != persona_id:
        raise HTTPException(422, "ID persona tidak boleh diubah")
    if not card.name.strip():
        raise HTTPException(422, "Nama wajib diisi")
    cleaned = card.model_copy(update={k: [x.strip() for x in getattr(card, k) if x.strip()] for k in ("catchphrases", "topic_limits", "background_facts", "do_not", "opinions")})
    content.save_persona(persona_id, cleaned)
    return cleaned


# ── Prompt berversi ──────────────────────────────────────────────────────────
class PromptVersion(BaseModel):
    version: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    body: str = Field(min_length=10)
    activate: bool = True


@router.get("/prompts")
def list_prompts(_: User = admin):
    rows = content.list_prompts()
    for r in rows:
        r["placeholders"] = sorted(content.placeholders(content.prompt_body(r["name"], r["version"])))
    return rows


@router.get("/prompts/{name}/{version}")
def get_prompt(name: str, version: str, _: User = admin):
    try:
        return {"name": name, "version": version, "body": content.prompt_body(name, version)}
    except KeyError:
        raise HTTPException(404, "Prompt tidak ditemukan") from None


@router.post("/prompts/{name}", status_code=201)
def add_prompt_version(name: str, body: PromptVersion, user: User = admin):
    """Versi baru; riwayat lama tetap. Diaktifkan langsung bila `activate` (berlaku di siaran berikutnya)."""
    if not any(r["name"] == name for r in content.list_prompts()):
        raise HTTPException(404, "Prompt tidak ditemukan")
    try:
        content.check_prompt_placeholders(name, body.body)
        content.add_prompt_version(name, body.version, body.body, by=user.username, activate=body.activate)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


@router.post("/prompts/{name}/{version}/activate")
def activate_prompt(name: str, version: str, _: User = admin):
    try:
        content.activate_prompt(name, version)
    except KeyError:
        raise HTTPException(404, "Prompt tidak ditemukan") from None
    return {"ok": True}


# ── Potongan teks prompt ─────────────────────────────────────────────────────
class SnippetUpdate(BaseModel):
    text: str


@router.get("/snippets")
def list_snippets(_: User = admin):
    return content.all_snippets()


@router.put("/snippets/{key}")
def put_snippet(key: str, body: SnippetUpdate, user: User = admin):
    try:
        content.set_snippet(key, body.text, by=user.username)
    except KeyError:
        raise HTTPException(404, "Potongan teks tidak ditemukan") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


# ── Supervisor: kata terlarang dan kalimat aman ──────────────────────────────
class BannedWord(BaseModel):
    word: str
    category: str


class FallbackLine(BaseModel):
    persona: str
    kind: str
    text: str


@router.get("/supervisor")
def get_supervisor(_: User = admin):
    return {"banned": content.list_banned(), "fallbacks": content.list_fallbacks(), "kinds": list(content.FALLBACK_KINDS)}


@router.post("/supervisor/banned", status_code=201)
def add_banned(body: BannedWord, _: User = admin):
    try:
        content.add_banned(body.word, body.category)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


@router.delete("/supervisor/banned/{word}")
def remove_banned(word: str, _: User = admin):
    try:
        content.remove_banned(word)
    except KeyError:
        raise HTTPException(404, "Kata tidak ditemukan") from None
    return {"ok": True}


@router.post("/supervisor/fallbacks", status_code=201)
def add_fallback(body: FallbackLine, _: User = admin):
    try:
        content.add_fallback(body.persona, body.kind, body.text)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


@router.delete("/supervisor/fallbacks/{fallback_id}")
def remove_fallback(fallback_id: int, _: User = admin):
    try:
        content.remove_fallback(fallback_id)
    except KeyError:
        raise HTTPException(404, "Kalimat tidak ditemukan") from None
    return {"ok": True}


# ── Log semua siaran (termasuk yang lampau) ──────────────────────────────────
@router.get("/sessions")
def list_sessions_admin(request: Request, limit: int = 50, offset: int = 0, mode: Optional[Literal["A", "B"]] = None, q: Optional[str] = None, _: User = admin):
    """Riwayat siaran dari database, terbaru dulu. `live_session` = sesi yang sedang berjalan (bila ada)."""
    page = session_page(request.app.state.db, limit=max(1, min(200, limit)), offset=max(0, offset), mode=mode, q=q)
    engine = request.app.state.engine
    page["live_session"] = engine.session_id if engine is not None and show_is_live(request.app) else None
    return page


_SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


@router.get("/sessions/{session_id}")
def get_session_admin(session_id: str, request: Request, _: User = admin):
    detail = session_detail(request.app.state.db, session_id) if _SESSION_ID.match(session_id) else None
    if detail is None:
        raise HTTPException(404, "Log sesi tidak ditemukan")
    engine = request.app.state.engine
    detail["live"] = bool(engine is not None and show_is_live(request.app) and engine.session_id == session_id)
    return detail


@router.get("/sessions/{session_id}/export/{part}")
def export_session_admin(session_id: str, part: Literal["events", "turns"], request: Request, _: User = admin):
    """Unduh log sebagai JSONL (bentuk yang dibaca skrip riset)."""
    from fastapi.responses import Response

    from app.show.turnlog import read_turns

    if not _SESSION_ID.match(session_id):
        raise HTTPException(404, "Log sesi tidak ditemukan")
    db = request.app.state.db
    rows = read_events(db, session_id) if part == "events" else read_turns(db, session_id)
    if not rows:
        raise HTTPException(404, "Log sesi tidak ditemukan" if part == "events" else "Sesi ini tidak punya log giliran riset")
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    name = f"{session_id}.jsonl" if part == "events" else f"{session_id}.turns.jsonl"
    return Response(body, media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{name}"'})
