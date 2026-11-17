"""Setelan yang diatur admin lewat halaman admin: kunci API, model, suara, Simli.

Nilai efektif = nilai di database (kalau admin pernah mengaturnya) atau, bila tidak ada, nilai dari .env/bawaan.
`.env` tetap berlaku sebagai bawaan; halaman admin menimpanya tanpa restart server. Kunci API disimpan
terenkripsi (SECRETS_KEY) dan tidak pernah dikirim balik ke browser (hanya "••••" + 4 karakter terakhir).

Menerapkan setelan membuat ulang klien LLM dan TTS. Itu tidak dilakukan saat ada siaran live/jeda: setelan
disimpan dan baru berlaku setelah siaran selesai (`pending`), supaya siaran yang berjalan tidak berubah di tengah jalan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.sql import insert

from app.blocker.store import now_iso
from app.config import Settings
from app.db import Database, app_settings
from app.secretbox import SecretBox

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Field_:
    key: str
    label: str
    kind: str = "text"  # text | secret | number | choice | face
    help: str = ""
    choices: tuple[str, ...] = ()


GROUPS: list[tuple[str, str, list[Field_]]] = [
    (
        "gemini",
        "Otak AI (Gemini)",
        [
            Field_("GEMINI_API_KEY", "Kunci API Gemini", "secret", "Dari Google AI Studio."),
            Field_("GEMINI_MODEL_PERSONA", "Model penyiar AI", help="ID model yang menulis ucapan Raka dan Salsa."),
            Field_("GEMINI_MODEL_SHOWRUNNER", "Model pengarah acara", help="Menilai kapan pindah poin/topik."),
            Field_("GEMINI_MODEL_BLOCKER", "Model pembuat materi", help="Menyusun materi dari tema."),
            Field_("GEMINI_MODEL_SUPERVISOR", "Model Supervisor", help="Hanya dipakai bila Supervisor dinyalakan."),
            Field_("GEMINI_MODEL_PERSONA_FALLBACK", "Model cadangan penyiar", help="Dipakai bila kuota harian model penyiar habis. Awalan compat: = LLM cadangan di bawah."),
        ],
    ),
    (
        "compat",
        "LLM cadangan (kompatibel OpenAI)",
        [
            Field_("OPENAI_COMPAT_BASE_URL", "Alamat API", help="Mis. https://api.cosmoshub.tech/v1"),
            Field_("OPENAI_COMPAT_API_KEY", "Kunci API", "secret"),
        ],
    ),
    (
        "tts",
        "Suara AI",
        [
            Field_("TTS_PROVIDER", "Penyedia suara utama", "choice", "ElevenLabs untuk siaran, Edge gratis untuk uji.", ("elevenlabs", "edge")),
            Field_("TTS_FALLBACK", "Cadangan suara", help="Urutan cadangan dipisah koma: edge, gtts. Kosongkan lalu isi none untuk tanpa cadangan."),
            Field_("ELEVENLABS_API_KEY", "Kunci API ElevenLabs", "secret", "Butuh izin text-to-speech; izin user_read untuk membaca sisa kredit."),
            Field_("ELEVENLABS_MODEL", "Model ElevenLabs", help="Mis. eleven_v4 atau eleven_flash_v2_5."),
            Field_("ELEVENLABS_STABILITY", "Stability", "number", "0 sampai 1. Kosong = pengaturan tersimpan milik suara itu."),
            Field_("ELEVENLABS_SIMILARITY", "Similarity", "number", "0 sampai 1."),
            Field_("ELEVENLABS_STYLE", "Style", "number", "0 sampai 1."),
            Field_("ELEVENLABS_SPEED", "Kecepatan", "number", "0,7 sampai 1,2."),
            Field_("VOICE_GAIN_DB_RAKA", "Volume Raka (dB)", "number", "-12 sampai 9. Menyamakan kenyaringan di layar OBS."),
            Field_("VOICE_GAIN_DB_SALSA", "Volume Salsa (dB)", "number", "-12 sampai 9."),
        ],
    ),
    (
        "simli",
        "Avatar (Simli)",
        [
            Field_("SIMLI_API_KEY", "Kunci API Simli", "secret"),
            Field_("SIMLI_FACE_ID_RAKA", "Wajah Raka", "face", "Pilih dari daftar wajah di bawah."),
            Field_("SIMLI_FACE_ID_SALSA", "Wajah Salsa", "face"),
            Field_("SIMLI_FACE_ID", "Wajah bawaan", "face", "Dipakai bila wajah penyiar belum dipilih."),
        ],
    ),
]
SPEC: dict[str, Field_] = {f.key: f for _, _, fields in GROUPS for f in fields}


class ConfigError(ValueError):
    pass


def validate_value(key: str, raw: str) -> Any:
    """Nilai terkonversi menurut aturan Settings (tipe, rentang, pilihan); ConfigError bila ditolak."""
    try:
        return getattr(Settings(_env_file=None, **{key: raw}), key)
    except ValidationError as e:
        msg = "; ".join(err["msg"] for err in e.errors())
        raise ConfigError(f"{SPEC[key].label}: {msg}") from e


def _mask(value: str) -> str:
    return "••••" + value[-4:] if len(value) > 8 else ("••••" if value else "")


def _text(v: Any) -> str:
    return "" if v is None else str(v)


@dataclass
class RuntimeConfig:
    db: Database
    settings: Settings
    box: SecretBox
    pending: bool = False
    _base: dict[str, Any] = field(default_factory=dict)  # nilai dari .env/bawaan, sebelum ditimpa admin

    def __post_init__(self) -> None:
        self._base = {k: getattr(self.settings, k) for k in SPEC}

    # penyimpanan ---------------------------------------------------------------
    def _rows(self) -> dict[str, tuple[str, bool]]:
        with self.db.engine.connect() as conn:
            rows = conn.execute(select(app_settings).where(~app_settings.c.key.like("meta.%"))).all()
        return {r.key: (r.value, bool(r.secret)) for r in rows if r.key in SPEC}

    def overrides(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, (value, secret) in self._rows().items():
            if secret:
                plain = self.box.decrypt(value)
                if plain is None:
                    logger.warning("Kunci %s tersimpan tetapi tidak terbaca (SECRETS_KEY berganti/hilang); memakai nilai .env", key)
                    continue
                value = plain
            out[key] = value
        return out

    def _upsert(self, conn, key: str, value: str, secret: bool, by: str) -> None:
        conn.execute(delete(app_settings).where(app_settings.c.key == key))
        conn.execute(insert(app_settings).values(key=key, value=value, secret=secret, updated_at=now_iso(), updated_by=by[:64]))

    # penerapan ------------------------------------------------------------------
    def effective(self) -> dict[str, Any]:
        over = self.overrides()
        out = dict(self._base)
        for key, raw in over.items():
            try:
                out[key] = validate_value(key, raw)
            except ConfigError as e:
                logger.warning("Setelan tersimpan %s ditolak (%s); memakai nilai .env", key, e)
        return out

    def apply_to_settings(self) -> dict[str, Any]:
        """Tulis nilai efektif ke objek Settings; mengembalikan nilai sebelumnya (untuk dibatalkan)."""
        previous = {k: getattr(self.settings, k) for k in SPEC}
        for key, value in self.effective().items():
            setattr(self.settings, key, value)
        return previous

    def restore(self, previous: dict[str, Any]) -> None:
        for key, value in previous.items():
            setattr(self.settings, key, value)

    # perubahan oleh admin ------------------------------------------------------
    def set_values(self, values: dict[str, str | None], by: str) -> list[str]:
        """Simpan. `None` = hapus timpaan (kembali ke .env); kunci rahasia "" = biarkan; angka "" = hapus timpaan.
        Semua divalidasi lebih dulu; satu yang salah membatalkan semuanya. Mengembalikan kunci yang berubah."""
        plan: list[tuple[str, str | None]] = []
        for key, raw in values.items():
            if key not in SPEC:
                raise ConfigError(f"Setelan tidak dikenal: {key}")
            spec = SPEC[key]
            if raw is None or (raw == "" and spec.kind == "number"):
                plan.append((key, None))
                continue
            if spec.kind == "secret":
                if raw == "":
                    continue
                if not self.box.enabled:
                    raise ConfigError("SECRETS_KEY belum diatur di server; kunci API belum bisa disimpan dari halaman ini")
            raw = raw.strip() if spec.kind in ("secret", "face") else raw
            validate_value(key, raw)
            if spec.kind == "choice" and raw not in spec.choices:
                raise ConfigError(f"{spec.label}: pilih salah satu dari {', '.join(spec.choices)}")
            plan.append((key, raw))
        with self.db.engine.begin() as conn:
            for key, raw in plan:
                if raw is None:
                    conn.execute(delete(app_settings).where(app_settings.c.key == key))
                elif SPEC[key].kind == "secret":
                    self._upsert(conn, key, self.box.encrypt(raw), True, by)
                else:
                    self._upsert(conn, key, raw, False, by)
        changed = [k for k, _ in plan]
        if changed:
            self.pending = True
            logger.info("Setelan diubah oleh %s: %s", by, ", ".join(changed))  # hanya nama kunci, tidak nilainya
        return changed

    # tampilan ---------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        rows = self._rows()
        saved = self.effective()  # yang tersimpan (bisa belum berlaku bila `pending`)
        groups = []
        for gid, label, fields in GROUPS:
            items = []
            for f in fields:
                current = saved[f.key]
                item: dict[str, Any] = {
                    "key": f.key, "label": f.label, "kind": f.kind, "help": f.help, "choices": list(f.choices),
                    "source": "admin" if f.key in rows else "env",
                }
                if f.kind == "secret":
                    item["is_set"] = bool(current)
                    item["masked"] = _mask(str(current or ""))
                else:
                    item["value"] = _text(current)
                items.append(item)
            groups.append({"id": gid, "label": label, "fields": items})
        return {"groups": groups, "secrets_enabled": self.box.enabled, "pending": self.pending}


# ── Penerapan ke aplikasi yang berjalan ──────────────────────────────────────

def show_is_live(app) -> bool:
    from app.schemas import ShowState

    engine = app.state.engine
    return engine is not None and engine.state in (ShowState.LIVE, ShowState.PAUSED)


def rebuild_services(app) -> None:
    """Buat ulang klien LLM, generator materi, dan TTS dari Settings sekarang."""
    from app.blocker import BlockerGenerator
    from app.llm import create_llm_client
    from app.tts import create_tts

    s = app.state.settings
    llm = create_llm_client(s, quota=app.state.quota)
    tts = create_tts(s)
    app.state.llm, app.state.tts = llm, tts
    app.state.generator = BlockerGenerator(llm, s.model_for("blocker"))


def apply_if_idle(app) -> str | None:
    """Terapkan setelan yang menunggu bila tidak ada siaran. None = beres (atau tidak ada yang menunggu);
    selain itu pesan galat (setelan lama tetap dipakai)."""
    cfg: RuntimeConfig | None = getattr(app.state, "runtime_config", None)
    if cfg is None or not cfg.pending or show_is_live(app):
        return None
    previous = cfg.apply_to_settings()
    try:
        rebuild_services(app)
    except Exception as e:  # noqa: BLE001 - kunci/model salah menggagalkan pembuatan klien
        cfg.restore(previous)
        logger.error("Setelan baru tidak bisa diterapkan: %s", e)
        return str(e)
    cfg.pending = False
    logger.info("Setelan admin diterapkan")
    return None
