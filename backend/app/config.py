"""Konfigurasi aplikasi dari environment (.env di root repo).

Model ID, kuota, dan voice ID tidak di-hard-code (PRD §0 aturan 3); semuanya
dibaca dari .env. Lihat .env.example untuk daftar lengkap (PRD Lampiran B).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


class Settings(BaseSettings):
    # Mode
    LLM_MODE: Literal["live", "mock"] = "mock"
    TTS_MODE: Literal["live", "mock"] = "mock"

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
    GEMINI_RPM_DEFAULT: int = 5

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
    PIPELINE_DEPTH: int = 1
    OPENING_TURNS: int = 2  # batas lunak Opening (mode B)
    CLOSING_TURNS: int = 2
    SESSION_TARGET_MIN: int = 0  # petunjuk lunak durasi total untuk Showrunner; 0 = tanpa
    PERSONA_TEMPERATURE: float = 0.9
    MODE_C_MAX_AI_STREAK: int = 2  # giliran AI berturut-turut sebelum giliran wajib kembali ke manusia (mode C)
    MODE_C_CHIME_PROBABILITY: float = 0.6  # peluang AI lain menimpali setelah AI pertama menjawab (mode C)
    SUMMARY_EVERY_TURNS: int = 10  # ringkasan obrolan diperbarui tiap sekian giliran yang keluar dari jendela riwayat; 0 = mati
    HUMAN_HOST_NAME: str = ""  # mode A (Tahap 4); keputusan terbuka PRD §15.2 #2

    # Uji: "llm" dan/atau "tts" untuk mensimulasikan galat
    FAIL_INJECT: str = ""

    # Penyimpanan
    DATA_DIR: str = str(BACKEND_ROOT / "data")
    LOG_DIR: str = str(BACKEND_ROOT / "logs")
    SESSIONS_DIR: str = ""  # kosong = folder `sessions` di samping LOG_DIR; isi per sesi: sessions/<session_id>/
    CACHE_DIR: str = str(BACKEND_ROOT / "cache")

    # Variabel kosong (mis. `GEMINI_RPM_PERSONA=` di .env.example) berarti pakai default.
    model_config = {"env_file": str(REPO_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}

    @property
    def sessions_path(self) -> Path:
        return Path(self.SESSIONS_DIR) if self.SESSIONS_DIR else Path(self.LOG_DIR).parent / "sessions"

    def tts_fallbacks(self) -> list[str]:
        """Daftar cadangan TTS dari TTS_FALLBACK; 'none' atau kosong berarti tanpa cadangan."""
        names = [n.strip().lower() for n in self.TTS_FALLBACK.split(",") if n.strip()]
        unknown = [n for n in names if n not in ("edge", "gtts", "elevenlabs", "none")]
        if unknown:
            raise ValueError(f"TTS_FALLBACK memuat provider tidak dikenal: {', '.join(unknown)}")
        return [n for n in names if n != "none"]

    def rpm_for(self, role: str) -> int:
        """RPM untuk satu peran (blocker, persona, ...); 0 berarti pakai default."""
        return getattr(self, f"GEMINI_RPM_{role.upper()}", 0) or self.GEMINI_RPM_DEFAULT

    def model_for(self, role: str) -> str:
        return getattr(self, f"GEMINI_MODEL_{role.upper()}", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
