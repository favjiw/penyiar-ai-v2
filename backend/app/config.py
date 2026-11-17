"""Konfigurasi aplikasi dari environment (.env di root repo).

Model ID, kuota, dan voice ID tidak di-hard-code (PRD §0 aturan 3); semuanya
dibaca dari .env. Lihat .env.example untuk daftar lengkap (PRD Lampiran B).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


class Settings(BaseSettings):
    # Mode
    LLM_MODE: Literal["live", "mock"] = "mock"
    TTS_MODE: Literal["live", "mock"] = "mock"
    PILOT_CONDITION: Literal["A", "B", "C", "D"] = "A"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_BLOCKER: str = ""
    GEMINI_MODEL_PERSONA: str = ""
    GEMINI_MODEL_PERSONA_FALLBACK: str = ""  # dipakai bila kuota harian model persona habis
    GEMINI_MODEL_SHOWRUNNER: str = ""
    GEMINI_MODEL_SUPERVISOR: str = ""
    GEMINI_MODEL_TTS: str = ""
    GEMINI_MODEL_JUDGE: str = ""
    GEMINI_RPM_BLOCKER: int = 0  # 0 = pakai GEMINI_RPM_DEFAULT
    GEMINI_RPM_PERSONA: int = 0
    GEMINI_RPM_SUPERVISOR: int = 0
    GEMINI_RPM_SHOWRUNNER: int = 0
    GEMINI_RPM_TTS: int = 0
    GEMINI_RPM_DEFAULT: int = 15
    # Kuota harian per model (RPD) untuk cek kesiapan (PRD v2.7 §8). Free tier terukur 500/hari/model (Tahap 2).
    GEMINI_RPD_DEFAULT: int = 500
    GEMINI_RPD_BLOCKER: int = 0  # 0 = pakai GEMINI_RPD_DEFAULT
    GEMINI_RPD_PERSONA: int = 0
    GEMINI_RPD_SUPERVISOR: int = 0
    GEMINI_RPD_SHOWRUNNER: int = 0
    QUOTA_FILE: str = ""  # kosong = <DATA_DIR>/quota.json
    # Laju bawaan untuk perkiraan menit aman bila log sesi belum cukup (diganti otomatis dari log).
    AI_TURNS_PER_MIN_A: float = 4.0
    AI_TURNS_PER_MIN_B: float = 7.0
    TTS_CREDITS_PER_MIN: float = 200.0  # ElevenLabs flash: ±4 rb kredit per 20 menit mode B (Tahap 0)
    TTS_QUOTA_ALERT_MIN: int = 5  # peringatan kuning saat perkiraan sisa suara ≤ sekian menit

    # Endpoint kompatibel OpenAI (opsional): dipakai lewat model `compat:<nama>` di GEMINI_MODEL_*
    OPENAI_COMPAT_BASE_URL: str = ""
    OPENAI_COMPAT_API_KEY: str = ""
    OPENAI_COMPAT_REASONING_EFFORT: str = "none"  # kosong = default endpoint

    # TTS
    TTS_PROVIDER: Literal["edge", "elevenlabs"] = "edge"  # Edge (gratis) untuk pengembangan; elevenlabs untuk demo
    TTS_FALLBACK: str = "gtts"  # cadangan berurutan, dipisah koma: edge | gtts | elevenlabs | none
    TTS_RETRIES: int = 1  # ulang provider utama sebelum pindah ke cadangan
    TTS_TIMEOUT_SEC: float = 12.0  # Edge dari laptop ini sering 3-8 s per kalimat; pindah suara di tengah siaran lebih buruk daripada menunggu
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_MODEL: str = ""
    # Pengaturan suara ElevenLabs (voice_settings), sama dengan slider di studio web. Kosong = tidak dikirim,
    # jadi ElevenLabs memakai pengaturan tersimpan milik suara itu. Kecepatan 0,7-1,2.
    ELEVENLABS_STABILITY: Optional[float] = Field(default=None, ge=0, le=1)
    ELEVENLABS_SIMILARITY: Optional[float] = Field(default=None, ge=0, le=1)
    ELEVENLABS_STYLE: Optional[float] = Field(default=None, ge=0, le=1)
    ELEVENLABS_SPEED: Optional[float] = Field(default=None, ge=0.7, le=1.2)
    ELEVENLABS_SPEAKER_BOOST: Optional[bool] = None
    ELEVENLABS_VOICE_MALE: str = ""
    ELEVENLABS_VOICE_FEMALE: str = ""
    ELEVENLABS_VOICE_RAKA: str = ""  # opsional: menimpa voice di kartu persona
    ELEVENLABS_VOICE_SALSA: str = ""
    EDGE_VOICE_MALE: str = "id-ID-ArdiNeural"
    EDGE_VOICE_FEMALE: str = "id-ID-GadisNeural"
    EDGE_VOICE_RAKA: str = ""
    EDGE_VOICE_SALSA: str = ""
    # Kecepatan dan nada Edge per persona (format Edge: "+5%", "-3Hz"). Titik awal; stel dengan didengar.
    EDGE_RATE_RAKA: str = "+4%"
    EDGE_PITCH_RAKA: str = "-2Hz"
    EDGE_RATE_SALSA: str = "+6%"
    EDGE_PITCH_SALSA: str = "+2Hz"

    # STT (mode A)
    STT_PROVIDER: Literal["webspeech", "faster_whisper", "gemini"] = "webspeech"
    FASTER_WHISPER_URL: str = ""

    # Agen
    SHOWRUNNER_POLICY: Literal["llm", "fixed_turns", "coverage_only"] = "llm"
    SHOWRUNNER_EVERY_K: int = 3
    MIN_TURNS_PER_TOPIC: int = 6
    MAX_TURNS_PER_TOPIC: int = 60  # batas keras; 40 membatasi sesi tiga topik ke ±34 menit (uji 30 Okt), padahal target 40+ menit
    FIXED_TURNS_PER_TOPIC: int = 0
    SUPERVISOR_MODE: Literal["off", "rules", "full"] = "off"  # hook supervisor.check: nonaktif (pass-through) kecuali dinyalakan
    SUPERVISOR_MAX_REGEN: int = 1
    SUPERVISOR_TIMEOUT_MS: int = 5000
    SUPERVISOR_TIMEOUT_MS_MODE_A: int = 2500  # mode A lebih ketat: penyiar menunggu jawaban
    PERSONA_TIMEOUT_MS: int = 20000  # lewat batas → kalimat aman, supaya tidak ada siaran hening panjang. Sesi 28 menit dengan 10 s: 21 dari 127 giliran jadi kalimat kaleng
    SHOWRUNNER_TIMEOUT_MS: int = 6000  # lewat batas → keputusan fixed_turns
    PERSONA_FAILURES_BEFORE_WRAP: int = 3  # persona gagal beruntun sebanyak ini...
    PERSONA_FAILURE_WRAP_SEC: int = 90  # ...dan selama ini (detik) → ke Closing; gangguan jaringan sesaat tidak menutup siaran
    PIPELINE_DEPTH: int = 2
    OPENING_TURNS: int = 2  # batas lunak Opening (mode B)
    CLOSING_TURNS: int = 2
    POINT_TIME_LIMIT_S: int = 60  # batas satu obrolan (satu poin) untuk kedua penyiar; 0 = mati (mode lama: Showrunner per topik). Rencana uji: 90
    POINT_WRAP_S: int = 15  # sisa waktu ≤ ini → giliran berikutnya menutup poin secara natural
    # Mode B (PRD v2.7, keputusan Favian 8 Nov 2026): batas per poin = menit topik ÷ jumlah poin
    # (POINT_TIME_LIMIT_S tetap batas bawah dan sakelar timer; 0 = timer mati untuk baseline eksperimen).
    POINT_LIMIT_FROM_TOPIC: bool = True
    # Mode A (PRD v2.7): tidak ada pindah otomatis; AI memberi kode halus satu kali per topik saat
    # topik lewat waktu sekian detik. 0 = kode halus mati.
    MODE_A_NUDGE_AFTER_S: int = 120
    # Mode A: pindah topik dari ucapan penyiar (deteksi aturan, app/show/intent.py) dan jendela batal (detik).
    VOICE_TOPIC_SWITCH: bool = True
    VOICE_SWITCH_UNDO_S: int = Field(default=10, ge=0)
    POINT_MIN_TURNS: int = 3  # Showrunner baru boleh menutup poin lebih awal setelah sekian giliran (mode B)
    TTS_WORDS_PER_SEC: float = 2.0  # konversi sisa waktu → anggaran kata (Edge 2,3; gTTS 1,9; ElevenLabs belum terukur)
    SESSION_TARGET_MIN: int = 0  # petunjuk lunak durasi total untuk Showrunner; 0 = tanpa
    PERSONA_TEMPERATURE: float = 0.9
    SUMMARY_EVERY_TURNS: int = 10  # ringkasan obrolan diperbarui tiap sekian giliran yang keluar dari jendela riwayat; 0 = mati
    HUMAN_HOST_NAME: str = ""  # mode A (Tahap 4); keputusan terbuka PRD §15.2 #2

    # Penyeimbang volume antarpenyiar, dalam dB, diterapkan di layar OBS (suara lokal dan jalur Simli). 0 = tanpa perubahan.
    # Provider dan model suara punya kenyaringan berbeda; ukur dari rekaman OBS lalu samakan (sekitar -17 dB rata-rata).
    VOICE_GAIN_DB_RAKA: float = Field(default=0.0, ge=-12, le=9)
    VOICE_GAIN_DB_SALSA: float = Field(default=0.0, ge=-12, le=9)

    # Simli (avatar video realistis di /stage menggantikan karakter 2D; 2D tetap jadi cadangan otomatis)
    SIMLI_API_KEY: str = ""
    SIMLI_FACE_ID: str = "bf13113a-355a-4d97-8b90-4edccd1da7b2"  # wajah bawaan bila wajah per persona kosong
    SIMLI_FACE_ID_RAKA: str = ""  # wajah per persona; kosong = SIMLI_FACE_ID
    SIMLI_FACE_ID_SALSA: str = ""
    SIMLI_MAX_SESSION_S: int = 3600  # batas satu sambungan Simli; layar OBS menyambung ulang sendiri setelahnya
    SIMLI_MAX_IDLE_S: int = 300  # Simli memutus sambungan yang sepi sekian detik; menyambung ulang otomatis

    # Uji: "llm" dan/atau "tts" untuk mensimulasikan galat
    FAIL_INJECT: str = ""

    # Hosting: folder hasil build frontend yang disajikan backend (kosong = frontend/dist di repo, bila ada).
    FRONTEND_DIST: str = ""

    # Penyimpanan
    DATA_DIR: str = str(BACKEND_ROOT / "data")
    LOG_DIR: str = str(BACKEND_ROOT / "logs")
    SESSIONS_DIR: str = ""  # kosong = folder `sessions` di samping LOG_DIR; isi per sesi: sessions/<session_id>/
    CACHE_DIR: str = str(BACKEND_ROOT / "cache")

    # Database: pengguna, sesi login, dan materi. Contoh Postgres: postgresql+psycopg://user:sandi@host:5432/nama.
    # Kosong = materi tetap file di DATA_DIR; bila AUTH_REQUIRED, dipakai SQLite <DATA_DIR>/app.db (pengembangan).
    DATABASE_URL: str = ""

    # Login aplikasi. Mati (bawaan) = tanpa login, untuk pengembangan lokal dan tes; hosting WAJIB menyalakannya.
    AUTH_REQUIRED: bool = False
    AUTH_SESSION_HOURS: int = Field(default=168, ge=1)  # lama sesi login; diperpanjang otomatis selama dipakai
    AUTH_COOKIE_SECURE: bool = False  # true di belakang HTTPS (cookie hanya dikirim lewat HTTPS)
    AUTH_MAX_FAILURES: int = Field(default=5, ge=1)  # gagal login beruntun (per pengguna) sebelum diblokir sementara
    AUTH_LOCKOUT_MIN: int = Field(default=15, ge=1)

    # Variabel kosong (mis. `GEMINI_RPM_PERSONA=` di .env.example) berarti pakai default.
    model_config = {"env_file": str(REPO_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}

    @model_validator(mode="after")
    def _point_timer_is_consistent(self):
        if self.POINT_TIME_LIMIT_S > 0 and self.POINT_WRAP_S >= self.POINT_TIME_LIMIT_S:
            raise ValueError("POINT_WRAP_S harus lebih kecil dari POINT_TIME_LIMIT_S (kalau tidak, setiap giliran menutup poin)")
        return self

    @property
    def sessions_path(self) -> Path:
        return Path(self.SESSIONS_DIR) if self.SESSIONS_DIR else Path(self.LOG_DIR).parent / "sessions"

    @property
    def database_url(self) -> str:
        """URL database yang berlaku; kosong berarti tanpa database (materi disimpan sebagai file)."""
        url = self.DATABASE_URL.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):  # tanpa driver eksplisit: pakai psycopg 3
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if not url and self.AUTH_REQUIRED:
            url = "sqlite:///" + (Path(self.DATA_DIR) / "app.db").as_posix()
        return url

    def tts_fallbacks(self) -> list[str]:
        """Daftar cadangan TTS dari TTS_FALLBACK; 'none' atau kosong berarti tanpa cadangan."""
        names = [n.strip().lower() for n in self.TTS_FALLBACK.split(",") if n.strip()]
        unknown = [n for n in names if n not in ("edge", "gtts", "elevenlabs", "none")]
        if unknown:
            raise ValueError(f"TTS_FALLBACK memuat provider tidak dikenal: {', '.join(unknown)}")
        return [n for n in names if n != "none"]

    def voice_gain(self, persona: str) -> float:
        """Pengali volume (linear) untuk satu persona dari VOICE_GAIN_DB_<PERSONA>; 1.0 bila tidak diatur."""
        db = getattr(self, f"VOICE_GAIN_DB_{persona.upper()}", 0.0)
        return round(10 ** (db / 20), 4)

    def elevenlabs_voice_settings(self) -> dict[str, float | bool]:
        """voice_settings untuk permintaan ElevenLabs; hanya yang diisi di .env."""
        pairs = {
            "stability": self.ELEVENLABS_STABILITY,
            "similarity_boost": self.ELEVENLABS_SIMILARITY,
            "style": self.ELEVENLABS_STYLE,
            "speed": self.ELEVENLABS_SPEED,
            "use_speaker_boost": self.ELEVENLABS_SPEAKER_BOOST,
        }
        return {k: v for k, v in pairs.items() if v is not None}

    def simli_face_for(self, persona: str = "") -> str:
        """Wajah Simli untuk satu persona (raka | salsa); jatuh ke SIMLI_FACE_ID bila belum diatur."""
        per_persona = getattr(self, f"SIMLI_FACE_ID_{persona.upper()}", "") if persona else ""
        return (per_persona or self.SIMLI_FACE_ID).strip().strip("'\"")

    def rpd_for_model(self, model: str) -> int:
        """Kuota harian sebuah model: yang paling ketat di antara peran yang memakainya (kuota Google per model)."""
        limits = [getattr(self, f"GEMINI_RPD_{r.upper()}", 0) or self.GEMINI_RPD_DEFAULT
                  for r in ("blocker", "persona", "supervisor", "showrunner") if self.model_for(r) == model]
        return min(limits) if limits else self.GEMINI_RPD_DEFAULT

    @property
    def quota_path(self) -> Path:
        return Path(self.QUOTA_FILE) if self.QUOTA_FILE else Path(self.DATA_DIR) / "quota.json"

    def rpm_for(self, role: str) -> int:
        """RPM untuk satu peran (blocker, persona, ...); 0 berarti pakai default."""
        return getattr(self, f"GEMINI_RPM_{role.upper()}", 0) or self.GEMINI_RPM_DEFAULT

    def model_for(self, role: str) -> str:
        return getattr(self, f"GEMINI_MODEL_{role.upper()}", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
