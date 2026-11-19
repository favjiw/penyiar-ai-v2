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
    kind: str = "text"  # text | secret | number | bool | choice | face
    help: str = ""
    choices: tuple[str, ...] = ()


GROUPS: list[tuple[str, str, list[Field_]]] = [
    (
        "gemini",
        "Otak AI (Gemini Gratis)",
        [
            Field_("GEMINI_API_KEY", "Kunci API Gemini", "secret", "Dari Google AI Studio (free tier)."),
            Field_("GEMINI_MODEL_PERSONA", "Model penyiar AI", help="ID model yang menulis ucapan Raka dan Salsa."),
            Field_("GEMINI_MODEL_SHOWRUNNER", "Model pengarah acara", help="Menilai kapan pindah poin/topik."),
            Field_("GEMINI_MODEL_BLOCKER", "Model pembuat materi", help="Menyusun materi dari tema."),
            Field_("GEMINI_MODEL_SUPERVISOR", "Model Supervisor", help="Hanya dipakai bila Supervisor dinyalakan."),
            Field_("GEMINI_MODEL_PERSONA_FALLBACK", "Model cadangan penyiar", help="Model Gemini gratis lain bila kuota harian model utama habis."),
        ],
    ),
    (
        "tts",
        "Suara AI (Edge TTS & gTTS Gratis)",
        [
            Field_("TTS_FALLBACK", "Cadangan suara", help="Urutan cadangan gratis dipisah koma: gtts, atau none untuk tanpa cadangan."),
            Field_("EDGE_VOICE_RAKA", "Suara Edge Raka", help="Kosong = bawaan persona/gender (id-ID-ArdiNeural)."),
            Field_("EDGE_RATE_RAKA", "Kecepatan Raka", help="Format Edge: +4%, -5%."),
            Field_("EDGE_PITCH_RAKA", "Nada (pitch) Raka", help="Format Edge: -2Hz, +3Hz."),
            Field_("VOICE_GAIN_DB_RAKA", "Volume Raka (dB)", "number", "-12 sampai 9. Menyamakan kenyaringan di layar OBS."),
            Field_("EDGE_VOICE_SALSA", "Suara Edge Salsa", help="Kosong = bawaan persona/gender (id-ID-GadisNeural)."),
            Field_("EDGE_RATE_SALSA", "Kecepatan Salsa", help="Format Edge: +6%, -5%."),
            Field_("EDGE_PITCH_SALSA", "Nada (pitch) Salsa", help="Format Edge: +2Hz, -2Hz."),
            Field_("VOICE_GAIN_DB_SALSA", "Volume Salsa (dB)", "number", "-12 sampai 9."),
        ],
    ),
    (
        "show",
        "Alur siaran",
        [
            Field_("POINT_TIME_LIMIT_S", "Batas waktu satu poin (detik)", "number", "Mode AI + AI. 0 = tanpa batas waktu per poin."),
            Field_("POINT_WRAP_S", "Mulai menutup poin (detik sebelum habis)", "number", "Harus lebih kecil dari batas waktu poin."),
            Field_("POINT_MIN_TURNS", "Giliran minimal sebelum poin boleh ditutup dini", "number", ""),
            Field_("POINT_LIMIT_FROM_TOPIC", "Batas poin dari menit topik", "bool", "Ya: batas = menit topik dibagi jumlah poin (minimal batas di atas)."),
            Field_("POINT_TRIM_FACTOR", "Faktor perapian teks", "number", "Teks dirapikan bila lebih dari sekian kali anggaran kata."),
            Field_("TTS_WORDS_PER_SEC", "Kata per detik suara", "number", "Mengubah sisa waktu jadi anggaran kata (ElevenLabs belum terukur)."),
            Field_("OPENING_CLOSING_TARGET_S", "Durasi Opening dan Closing (detik)", "number", "Tiap bagian."),
            Field_("OPENING_CLOSING_MAX_TURNS", "Giliran maksimal Opening/Closing", "number", ""),
            Field_("SHOWRUNNER_POLICY", "Kebijakan pengarah acara", "choice", "llm = dinilai model; lainnya untuk pembanding riset.", ('llm', 'fixed_turns', 'coverage_only')),
            Field_("SHOWRUNNER_EVERY_K", "Pengarah acara menilai tiap … giliran", "number", ""),
            Field_("MIN_TURNS_PER_TOPIC", "Giliran minimal per topik", "number", ""),
            Field_("MAX_TURNS_PER_TOPIC", "Giliran maksimal per topik", "number", "Batas keras; lewat ini topik dipindah paksa."),
            Field_("SHOWRUNNER_TIMEOUT_MS", "Batas waktu pengarah acara (ms)", "number", ""),
            Field_("MODE_A_NUDGE_AFTER_S", "Kode halus pindah topik setelah (detik)", "number", "Mode penyiar + AI. 0 = mati."),
            Field_("VOICE_TOPIC_SWITCH", "Pindah topik dari ucapan penyiar", "bool", "Mode penyiar + AI."),
            Field_("VOICE_SWITCH_UNDO_S", "Jendela batal pindah topik (detik)", "number", ""),
            Field_("VOICE_SWITCH_TRANSITION_OVERLAP", "Deteksi: kemiripan kalimat pindah topik", "number", "0 sampai 1."),
            Field_("VOICE_SWITCH_TRANSITION_MIN_WORDS", "Deteksi: kata minimal kalimat pindah topik", "number", ""),
            Field_("VOICE_SWITCH_TITLE_OVERLAP", "Deteksi: kemiripan judul topik berikutnya", "number", "0 sampai 1."),
            Field_("VOICE_SWITCH_TITLE_MIN_WORDS", "Deteksi: kata minimal judul topik", "number", ""),
            Field_("PIPELINE_DEPTH", "Kedalaman antrean giliran (pipelining)", "number", ""),
            Field_("PLAYBACK_GRACE_SEC", "Toleransi laporan selesai-putar (detik)", "number", ""),
            Field_("SUMMARY_EVERY_TURNS", "Ringkasan obrolan tiap … giliran", "number", "0 = mati."),
            Field_("SUMMARY_MAX_CHARS", "Panjang ringkasan maksimal (karakter)", "number", ""),
            Field_("SESSION_TARGET_MIN", "Petunjuk durasi total (menit)", "number", "Petunjuk lunak untuk pengarah acara; 0 = tanpa."),
            Field_("HUMAN_HOST_NAME", "Nama penyiar manusia bawaan", "text", ""),
        ],
    ),
    (
        "persona",
        "Gaya penyiar AI",
        [
            Field_("PERSONA_TEMPERATURE", "Temperature", "number", "Makin tinggi makin bervariasi (0 sampai 2)."),
            Field_("HISTORY_TURNS", "Riwayat obrolan di prompt (giliran)", "number", ""),
            Field_("CATCHPHRASE_PROBABILITY", "Peluang catchphrase", "number", "0 sampai 1, per giliran setelah jeda."),
            Field_("CATCHPHRASE_COOLDOWN_TURNS", "Jeda catchphrase (giliran)", "number", ""),
            Field_("ANTI_REPETITION_WINDOW", "Jendela anti-pembuka-berulang (giliran)", "number", ""),
            Field_("TRIGRAM_REPEAT_LIMIT", "Batas pengulangan tiga kata", "number", ""),
            Field_("TRIGRAM_HISTORY_WINDOW", "Jendela pengulangan tiga kata (giliran)", "number", ""),
            Field_("GREETING_EVERY_TURNS", "Menyapa Sobat Hits tiap … giliran", "number", ""),
            Field_("PERSONA_TIMEOUT_MS", "Batas waktu penyiar AI (ms)", "number", "Lewat ini diganti kalimat aman."),
            Field_("PERSONA_FAILURES_BEFORE_WRAP", "Gagal beruntun sebelum menutup siaran", "number", ""),
            Field_("PERSONA_FAILURE_WRAP_SEC", "Lama gagal sebelum menutup siaran (detik)", "number", ""),
        ],
    ),
    (
        "supervisor",
        "Supervisor",
        [
            Field_("SUPERVISOR_MODE", "Mode Supervisor", "choice", "off = tanpa Supervisor (produk KP); rules = aturan saja; full = aturan + model.", ('off', 'rules', 'full')),
            Field_("PILOT_CONDITION", "Kondisi pilot riset", "choice", "D memaksa Supervisor penuh. Untuk eksperimen, bukan siaran biasa.", ('A', 'B', 'C', 'D')),
            Field_("SUPERVISOR_MAX_REGEN", "Buat ulang maksimal", "number", ""),
            Field_("SUPERVISOR_TIMEOUT_MS", "Batas waktu Supervisor, mode AI + AI (ms)", "number", ""),
            Field_("SUPERVISOR_TIMEOUT_MS_MODE_A", "Batas waktu Supervisor, mode penyiar + AI (ms)", "number", ""),
            Field_("SUPERVISOR_MAX_WORDS", "Ucapan terlalu panjang (kata)", "number", ""),
            Field_("SUPERVISOR_REPEAT_WINDOW", "Jendela pengulangan persis (giliran)", "number", ""),
        ],
    ),
    (
        "kuota",
        "Kuota, kesiapan, dan batas teknis",
        [
            Field_("GEMINI_RPM_DEFAULT", "Batas permintaan per menit (bawaan)", "number", ""),
            Field_("GEMINI_RPD_DEFAULT", "Kuota harian per model (bawaan)", "number", ""),
            Field_("AI_TURNS_PER_MIN_A", "Laju awal giliran AI per menit, penyiar + AI", "number", "Dipakai sampai ada log sesi."),
            Field_("AI_TURNS_PER_MIN_B", "Laju awal giliran AI per menit, AI + AI", "number", ""),
            Field_("TTS_TIMEOUT_SEC", "Batas waktu suara (detik)", "number", ""),
            Field_("TTS_RETRIES", "Ulang suara utama sebelum cadangan", "number", ""),
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
            if spec.kind == "bool":
                raw = raw.strip().lower()
                if raw not in ("true", "false"):
                    raise ConfigError(f"{spec.label}: pilih Ya atau Tidak")
            if spec.kind == "choice" and raw not in spec.choices:
                raise ConfigError(f"{spec.label}: pilih salah satu dari {', '.join(spec.choices)}")
            plan.append((key, raw))
        merged = self.effective()
        for key, raw in plan:
            if raw is None:
                merged[key] = self._base[key]
            elif SPEC[key].kind != "secret":
                merged[key] = validate_value(key, raw)
        try:
            Settings(_env_file=None, **{k: v for k, v in merged.items() if v is not None})
        except ValidationError as e:
            raise ConfigError("; ".join(err["msg"] for err in e.errors())) from e
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
                    item["value"] = str(bool(current)).lower() if f.kind == "bool" else _text(current)
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
