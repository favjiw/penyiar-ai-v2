"""Antarmuka TTS (FR-6): semua pemanggilan suara di engine lewat `TTSProvider.synthesize(text, persona)`.

Provider dipilih lewat `.env` (`TTS_PROVIDER`, `TTS_FALLBACK`); engine tidak pernah memanggil
ElevenLabs, Edge, atau gTTS secara langsung.
"""

from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass

SAMPLE_RATE = 24000


@dataclass
class AudioResult:
    """Hasil satu sintesis: bytes audio, format, dan durasi."""

    audio: bytes
    mime: str  # audio/mpeg | audio/wav
    provider: str
    voice: str
    duration_s: float
    latency_ms: int = 0
    first_byte_ms: int = 0
    credit_cost: int = 0
    cached: bool = False
    fallback_reason: str = ""  # tidak kosong bila hasil ini berasal dari cadangan

    @property
    def ext(self) -> str:
        return "mp3" if self.mime == "audio/mpeg" else "wav"

    @property
    def fallback_used(self) -> bool:
        return bool(self.fallback_reason)


# Nama lama dipertahankan untuk kode yang sudah ada.
TTSResult = AudioResult


class TTSError(RuntimeError):
    pass


class TTSProvider(ABC):
    name: str = ""

    @abstractmethod
    def cache_key(self, persona: str) -> str:
        """Kunci suara untuk cache audio: voice ID ditambah rate/pitch, supaya perubahan config tidak memutar audio lama."""

    @abstractmethod
    async def synthesize(self, text: str, persona: str) -> AudioResult:
        """Sintesis satu ucapan persona (`raka`, `salsa`, ...). Galat atau audio kosong harus berupa exception."""


def silence_wav(duration_ms: int, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(sample_rate * duration_ms / 1000))
    return buf.getvalue()


def wav_duration(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def cbr_mp3_duration(audio: bytes, kbps: int) -> float:
    return len(audio) * 8 / (kbps * 1000)


_BITRATE_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_BITRATE_V2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}  # kunci: versi MPEG


def mp3_duration(audio: bytes) -> float:
    """Durasi MP3 Layer III dengan menjumlah frame (CBR maupun VBR). 0.0 bila tidak ada frame yang valid."""
    n = len(audio)
    i = 0
    if audio[:3] == b"ID3" and n >= 10:
        i = 10 + ((audio[6] & 0x7F) << 21 | (audio[7] & 0x7F) << 14 | (audio[8] & 0x7F) << 7 | (audio[9] & 0x7F))
    seconds = 0.0
    while i + 4 <= n:
        b1, b2 = audio[i + 1], audio[i + 2]
        if audio[i] == 0xFF and (b1 & 0xE0) == 0xE0:
            version, layer = (b1 >> 3) & 3, (b1 >> 1) & 3
            bitrate_idx, rate_idx, pad = (b2 >> 4) & 15, (b2 >> 2) & 3, (b2 >> 1) & 1
            if version in _SAMPLE_RATES and layer == 1 and bitrate_idx not in (0, 15) and rate_idx != 3:
                v1 = version == 3
                bitrate = (_BITRATE_V1_L3 if v1 else _BITRATE_V2_L3)[bitrate_idx] * 1000
                rate = _SAMPLE_RATES[version][rate_idx]
                length = (144 if v1 else 72) * bitrate // rate + pad
                seconds += (1152 if v1 else 576) / rate
                i += max(length, 4)
                continue
        i += 1
    return seconds
