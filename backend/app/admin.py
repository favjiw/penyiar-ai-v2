"""API halaman admin: setelan (kunci API, model, suara, Simli), katalog suara, katalog wajah Simli.

Semua rute hanya untuk admin. Nilai kunci API tidak pernah dikirim balik (hanya "••••" + 4 karakter terakhir).
"""

from __future__ import annotations

import logging
import re
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import User, require_role
from app.config import Settings
from app.content import content
from app.faces import Face, FaceCatalog, FaceError
from app.schemas import PersonaCard
from app.runtime_config import ConfigError, RuntimeConfig, apply_if_idle, show_is_live
from app.tts.catalog import VoiceError, VoiceOption, catalog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")
admin = Depends(require_role("admin"))

VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")  # juga dipakai sebagai bagian URL ke ElevenLabs: tanpa / atau ..
ELEVEN_BASE = "https://api.elevenlabs.io"
SIMLI_TOKEN_URL = "https://api.simli.ai/compose/token"
HTTP_TIMEOUT = 10.0


def _cfg(request: Request) -> RuntimeConfig:
    cfg = getattr(request.app.state, "runtime_config", None)
    if cfg is None:
        raise HTTPException(404, "Halaman admin butuh database (DATABASE_URL atau AUTH_REQUIRED)")
    return cfg


def _faces(request: Request) -> FaceCatalog:
    faces = getattr(request.app.state, "faces", None)
    if faces is None:
        raise HTTPException(404, "Halaman admin butuh database (DATABASE_URL atau AUTH_REQUIRED)")
    return faces


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


async def _test_compat(s: Settings) -> dict:
    if not (s.OPENAI_COMPAT_BASE_URL and s.OPENAI_COMPAT_API_KEY):
        return _result(False, "Alamat API dan kunci LLM cadangan belum diisi.")
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(s.OPENAI_COMPAT_BASE_URL.rstrip("/") + "/models", headers={"Authorization": f"Bearer {s.OPENAI_COMPAT_API_KEY}"})
    except httpx.HTTPError as e:
        return _result(False, f"Tidak bisa menghubungi {s.OPENAI_COMPAT_BASE_URL}: {type(e).__name__}")
    if r.status_code == 200:
        return _result(True, "Terhubung; kunci diterima.")
    return _result(False, f"Server menjawab {r.status_code}: {r.text[:150]}")


def _eleven_status(r: httpx.Response) -> str:
    try:
        detail = r.json().get("detail")
        return str(detail.get("status", "")) if isinstance(detail, dict) else str(detail or "")
    except ValueError:
        return ""


async def _test_elevenlabs(s: Settings) -> dict:
    if not s.ELEVENLABS_API_KEY:
        return _result(False, "Kunci API ElevenLabs belum diisi.")
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{ELEVEN_BASE}/v1/user/subscription", headers={"xi-api-key": s.ELEVENLABS_API_KEY})
    except httpx.HTTPError as e:
        return _result(False, f"Tidak bisa menghubungi ElevenLabs: {type(e).__name__}")
    if r.status_code == 200:
        d = r.json()
        left = int(float(d["character_limit"]) - float(d["character_count"]))
        return _result(True, f"Kunci diterima. Sisa ±{left:,} dari {int(d['character_limit']):,} kredit.".replace(",", "."))
    status = _eleven_status(r)
    if r.status_code in (401, 403) and "permission" in status:
        return _result(True, "Kunci diterima, tetapi tanpa izin user_read: sisa kredit tidak bisa dibaca (suara tetap bisa dibuat).")
    return _result(False, f"ElevenLabs menolak ({r.status_code}{', ' + status if status else ''}).")


async def _test_simli(s: Settings) -> dict:
    key = (s.SIMLI_API_KEY or "").strip()
    if not key:
        return _result(False, "Kunci API Simli belum diisi.")
    face = s.simli_face_for("raka")
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(SIMLI_TOKEN_URL, headers={"x-simli-api-key": key}, json={"faceId": face, "handleSilence": True, "maxSessionLength": 60, "maxIdleTime": 30})
    except httpx.HTTPError as e:
        return _result(False, f"Tidak bisa menghubungi Simli: {type(e).__name__}")
    if r.status_code == 200:
        return _result(True, "Kunci diterima dan wajah Raka bisa dipakai.")
    return _result(False, f"Simli menolak ({r.status_code}): {r.text[:150]}")


TESTS = {"gemini": _test_gemini, "compat": _test_compat, "elevenlabs": _test_elevenlabs, "simli": _test_simli}


@router.post("/test/{service}")
async def test_service(service: Literal["gemini", "compat", "elevenlabs", "simli"], request: Request, _: User = admin):
    """Uji dengan setelan yang TERSIMPAN (termasuk yang menunggu siaran selesai), bukan yang sedang berjalan."""
    cfg = _cfg(request)
    s = request.app.state.settings.model_copy(update=cfg.effective())
    return await TESTS[service](s)


# ── Katalog suara ────────────────────────────────────────────────────────────
class VoiceCreate(BaseModel):
    id: str
    provider: Literal["elevenlabs", "edge"]
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


async def _verify_elevenlabs_voice(key: str, voice_id: str) -> tuple[Optional[dict], Optional[str]]:
    """(data suara, peringatan). data None + peringatan None tidak terjadi; 404 -> HTTPException di pemanggil."""
    if not key:
        return None, "Kunci ElevenLabs belum diisi, jadi ID suara belum bisa diperiksa."
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{ELEVEN_BASE}/v1/voices/{voice_id}", headers={"xi-api-key": key})
    except httpx.HTTPError:
        return None, "ElevenLabs tidak bisa dihubungi, jadi ID suara belum diperiksa."
    if r.status_code == 200:
        return r.json(), None
    if r.status_code in (400, 404, 422):
        raise HTTPException(422, "ID suara tidak ditemukan di akun ElevenLabs. Tambahkan dulu suara itu ke My Voices di ElevenLabs, lalu coba lagi.")
    return None, f"ElevenLabs menjawab {r.status_code}, jadi ID suara belum diperiksa (kunci mungkin tanpa izin voices_read)."


@router.post("/voices", status_code=201)
async def add_voice(body: VoiceCreate, request: Request, _: User = admin):
    cfg = _cfg(request)
    if not VOICE_ID_RE.match(body.id.strip()):
        raise HTTPException(422, "ID suara hanya boleh huruf, angka, strip, dan garis bawah (4-80 karakter)")
    warning: Optional[str] = None
    name, notes = body.name.strip(), body.notes.strip()
    if body.provider == "elevenlabs":
        data, warning = await _verify_elevenlabs_voice(cfg.effective().get("ELEVENLABS_API_KEY") or "", body.id.strip())
        if data:
            name = name or str(data.get("name", ""))
            notes = notes or str(data.get("description") or "")[:500]
    try:
        voice = catalog.add(VoiceOption(id=body.id, provider=body.provider, name=name, gender=body.gender, notes=notes))
    except VoiceError as e:
        raise HTTPException(422, str(e)) from e
    return {"voice": voice, "warning": warning}


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


# ── Katalog wajah Simli ──────────────────────────────────────────────────────
@router.get("/faces")
def list_faces(request: Request, _: User = admin):
    return _faces(request).all()


@router.post("/faces", status_code=201)
def add_face(body: Face, request: Request, _: User = admin):
    try:
        return _faces(request).add(body)
    except FaceError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/faces/{face_id}")
def delete_face(face_id: str, request: Request, _: User = admin):
    cfg = _cfg(request)
    in_use = [k for k in ("SIMLI_FACE_ID_RAKA", "SIMLI_FACE_ID_SALSA", "SIMLI_FACE_ID") if cfg.effective().get(k) == face_id]
    if in_use:
        raise HTTPException(409, "Wajah ini sedang dipilih untuk penyiar atau sebagai bawaan; pilih wajah lain dulu.")
    try:
        _faces(request).remove(face_id)
    except KeyError:
        raise HTTPException(404, "Wajah tidak ditemukan") from None
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
