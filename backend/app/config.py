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

    # TTS
    TTS_PRIMARY: Literal["elevenlabs", "edge", "gemini"] = "elevenlabs"
    TTS_FALLBACK: Literal["edge", "none"] = "edge"
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_MODEL: str = ""
    ELEVENLABS_VOICE_MALE: str = ""
    ELEVENLABS_VOICE_FEMALE: str = ""
    GEMINI_VOICE_MALE: str = ""
    GEMINI_VOICE_FEMALE: str = ""
    EDGE_VOICE_MALE: str = "id-ID-ArdiNeural"
    EDGE_VOICE_FEMALE: str = "id-ID-GadisNeural"

    # STT (mode A)
    STT_PROVIDER: Literal["webspeech", "faster_whisper", "gemini"] = "webspeech"
    FASTER_WHISPER_URL: str = ""

    # Agen
    SHOWRUNNER_POLICY: Literal["llm", "fixed_turns", "coverage_only"] = "llm"
    SHOWRUNNER_EVERY_K: int = 3
    MIN_TURNS_PER_TOPIC: int = 6
    MAX_TURNS_PER_TOPIC: int = 40
    FIXED_TURNS_PER_TOPIC: int = 0
    SUPERVISOR_MODE: Literal["off", "rules", "full"] = "full"
    SUPERVISOR_MAX_REGEN: int = 1
    SUPERVISOR_TIMEOUT_MS: int = 5000
    PERSONA_TIMEOUT_MS: int = 10000  # lewat batas → kalimat aman, supaya tidak ada siaran hening panjang
    SHOWRUNNER_TIMEOUT_MS: int = 6000  # lewat batas → keputusan fixed_turns
    PIPELINE_DEPTH: int = 1
    OPENING_TURNS: int = 2  # batas lunak Opening (mode B)
    CLOSING_TURNS: int = 2
    SESSION_TARGET_MIN: int = 0  # petunjuk lunak durasi total untuk Showrunner; 0 = tanpa
    PERSONA_TEMPERATURE: float = 0.9
    HUMAN_HOST_NAME: str = ""  # mode A (Tahap 4); keputusan terbuka PRD §15.2 #2

    # Avatar
    AVATAR_TIER: Literal["t1", "t2"] = "t1"
    AVATAR_WORKER_URL: str = ""

    # Skripsi
    COMMENTS_ENABLED: bool = False
    TIKTOK_USERNAME: str = ""

    # Uji: "llm" dan/atau "tts" untuk mensimulasikan galat
    FAIL_INJECT: str = ""

    # Penyimpanan
    DATA_DIR: str = str(BACKEND_ROOT / "data")
    LOG_DIR: str = str(BACKEND_ROOT / "logs")
    CACHE_DIR: str = str(BACKEND_ROOT / "cache")

    model_config = {"env_file": str(REPO_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    def rpm_for(self, role: str) -> int:
        """RPM untuk satu peran (blocker, persona, ...); 0 berarti pakai default."""
        return getattr(self, f"GEMINI_RPM_{role.upper()}", 0) or self.GEMINI_RPM_DEFAULT

    def model_for(self, role: str) -> str:
        return getattr(self, f"GEMINI_MODEL_{role.upper()}", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
