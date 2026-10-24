"""TTS (FR-6): ElevenLabs utama, Edge TTS failover, cache file, dan mock.

Diadaptasi dari repo lama (conversational-ai@v1-format-clock). Perubahan:
- ElevenLabs memakai endpoint streaming (byte pertama ±0,45 s di Tahap 0) dan
  mencatat header `character-cost` untuk pemantauan kredit;
- Edge memakai resolver DNS sistem (aiodns menggantung di laptop streaming);
- suara wanita Edge `id-ID-GadisNeural`, bukan `su-ID-TutiNeural`;
- failover dengan breaker: setelah primary gagal beruntun, primary dilewati
  selama masa jeda agar giliran berikutnya tidak menunggu timeout lagi.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Gender = Literal["male", "female"]
SAMPLE_RATE = 24000


@dataclass
class TTSResult:
    audio: bytes
    mime: str  # audio/mpeg | audio/wav
    provider: str
    voice: str
    duration_s: float
    latency_ms: int = 0
    first_byte_ms: int = 0
    credit_cost: int = 0
    cached: bool = False
    fallback_reason: str = ""

    @property
    def ext(self) -> str:
        return "mp3" if self.mime == "audio/mpeg" else "wav"


class TTSError(RuntimeError):
    pass


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


class TTSProvider(ABC):
    name: str = ""

    @abstractmethod
    def voice_for(self, gender: Gender, voices: dict[str, str] | None = None) -> str:
        """Voice ID provider ini untuk satu persona: dari kartu persona, lalu default .env."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str) -> TTSResult: ...


# ── Mock ─────────────────────────────────────────────────────────────────────


class MockTTSProvider(TTSProvider):
    """Keheningan sepanjang ±60 ms per karakter (TTS_MODE=mock)."""

    name = "mock"

    def __init__(self, delay_sec: float = 0.05):
        self._delay = delay_sec

    def voice_for(self, gender, voices=None):
        return f"mock-{gender}"

    async def synthesize(self, text, voice):
        await asyncio.sleep(self._delay)
        audio = silence_wav(max(500, len(text) * 60))
        return TTSResult(audio, "audio/wav", self.name, voice, wav_duration(audio), latency_ms=int(self._delay * 1000))


# ── ElevenLabs ───────────────────────────────────────────────────────────────


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"
    OUTPUT_FORMAT = "mp3_44100_128"
    KBPS = 128

    def __init__(self, api_key: str, model: str, voice_male: str, voice_female: str, timeout_sec: float = 15.0):
        if not (api_key and model):
            raise ValueError("ELEVENLABS_API_KEY dan ELEVENLABS_MODEL wajib untuk TTS ElevenLabs")
        self._key, self._model = api_key, model
        self._defaults = {"male": voice_male, "female": voice_female}
        self._timeout = timeout_sec

    def voice_for(self, gender, voices=None):
        voice = (voices or {}).get(self.name) or self._defaults[gender]
        if not voice:
            raise ValueError(f"Voice ElevenLabs untuk {gender} kosong; isi ELEVENLABS_VOICE_{gender.upper()}")
        return voice

    async def synthesize(self, text, voice):
        import httpx

        start = time.perf_counter()
        first = None
        chunks: list[bytes] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream",
                params={"output_format": self.OUTPUT_FORMAT},
                headers={"xi-api-key": self._key},
                json={"text": text, "model_id": self._model},
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")[:300]
                    raise TTSError(f"ElevenLabs HTTP {resp.status_code}: {body}")
                cost = int(resp.headers.get("character-cost", "0") or 0)
                async for chunk in resp.aiter_bytes():
                    if first is None:
                        first = time.perf_counter() - start
                    chunks.append(chunk)
        audio = b"".join(chunks)
        if not audio:
            raise TTSError("ElevenLabs mengembalikan audio kosong")
        return TTSResult(
            audio,
            "audio/mpeg",
            self.name,
            voice,
            cbr_mp3_duration(audio, self.KBPS),
            latency_ms=int((time.perf_counter() - start) * 1000),
            first_byte_ms=int((first or 0) * 1000),
            credit_cost=cost,
        )


# ── Edge TTS ─────────────────────────────────────────────────────────────────


class EdgeTTSProvider(TTSProvider):
    """Edge TTS (pustaka tidak resmi `edge-tts`), gratis; keluaran MP3 48 kbps CBR."""

    name = "edge"
    KBPS = 48

    def __init__(self, voice_male: str, voice_female: str):
        self._defaults = {"male": voice_male, "female": voice_female}

    def voice_for(self, gender, voices=None):
        return (voices or {}).get(self.name) or self._defaults[gender]

    async def synthesize(self, text, voice):
        import aiohttp
        import edge_tts

        start = time.perf_counter()
        first = None
        chunks: list[bytes] = []
        # aiodns (bila terpasang) menggantung ±20 s di laptop ini; pakai resolver sistem.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async for chunk in edge_tts.Communicate(text, voice, connector=connector).stream():
            if chunk["type"] == "audio":
                if first is None:
                    first = time.perf_counter() - start
                chunks.append(chunk["data"])
        audio = b"".join(chunks)
        if not audio:
            raise TTSError(f"Edge TTS mengembalikan audio kosong untuk {voice}")
        return TTSResult(
            audio,
            "audio/mpeg",
            self.name,
            voice,
            cbr_mp3_duration(audio, self.KBPS),
            latency_ms=int((time.perf_counter() - start) * 1000),
            first_byte_ms=int((first or 0) * 1000),
        )


# ── Cache ────────────────────────────────────────────────────────────────────


class AudioCache:
    """Cache file berkunci hash(provider, voice, teks). Dipakai untuk filler dan teks berulang."""

    def __init__(self, cache_dir: str | Path):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _stem(self, provider: str, voice: str, text: str) -> str:
        return hashlib.sha256(f"{provider}:{voice}:{text}".encode()).hexdigest()[:20]

    def get(self, provider: str, voice: str, text: str) -> TTSResult | None:
        stem = self._stem(provider, voice, text)
        for ext, mime in (("mp3", "audio/mpeg"), ("wav", "audio/wav")):
            path = self._dir / f"{stem}.{ext}"
            if path.exists():
                audio = path.read_bytes()
                kbps = EdgeTTSProvider.KBPS if provider == "edge" else ElevenLabsTTSProvider.KBPS
                dur = wav_duration(audio) if ext == "wav" else cbr_mp3_duration(audio, kbps)
                return TTSResult(audio, mime, provider, voice, dur, cached=True)
        return None

    def put(self, text: str, result: TTSResult) -> Path:
        path = self._dir / f"{self._stem(result.provider, result.voice, text)}.{result.ext}"
        path.write_bytes(result.audio)
        return path


# ── Failover + breaker ───────────────────────────────────────────────────────


class FailoverTTS:
    """Pintu masuk TTS untuk Show Engine: primary → fallback, dengan cache dan breaker."""

    def __init__(
        self,
        primary: TTSProvider,
        fallback: TTSProvider | None = None,
        cache: AudioCache | None = None,
        timeout_sec: float = 8.0,
        breaker_threshold: int = 2,
        breaker_cooldown_sec: float = 60.0,
    ):
        self.primary, self.fallback, self.cache = primary, fallback, cache
        self._timeout = timeout_sec
        self._threshold, self._cooldown = breaker_threshold, breaker_cooldown_sec
        self._failures = 0
        self._open_until = 0.0
        self.credits_used = 0

    @property
    def breaker_open(self) -> bool:
        return time.monotonic() < self._open_until

    def status(self) -> dict:
        return {
            "primary": self.primary.name,
            "fallback": self.fallback.name if self.fallback else None,
            "breaker_open": self.breaker_open,
            "consecutive_failures": self._failures,
            "credits_used": self.credits_used,
        }

    async def _run(self, provider: TTSProvider, text: str, gender: Gender, voices: dict | None) -> TTSResult:
        voice = provider.voice_for(gender, voices)
        if self.cache and (hit := self.cache.get(provider.name, voice, text)):
            return hit
        result = await asyncio.wait_for(provider.synthesize(text, voice), self._timeout)
        if self.cache:
            self.cache.put(text, result)
        return result

    async def synthesize(self, text: str, gender: Gender, voices: dict[str, str] | None = None) -> TTSResult:
        reason = ""
        if not self.breaker_open:
            try:
                result = await self._run(self.primary, text, gender, voices)
                self._failures = 0
                self.credits_used += result.credit_cost
                return result
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"[:300]
                self._failures += 1
                if self._failures >= self._threshold:
                    self._open_until = time.monotonic() + self._cooldown
                    logger.warning("TTS %s gagal %d kali; breaker terbuka %.0fs", self.primary.name, self._failures, self._cooldown)
                logger.warning("TTS %s gagal, pindah ke cadangan: %s", self.primary.name, reason)
        else:
            reason = "breaker terbuka"
        if not self.fallback:
            raise TTSError(f"TTS {self.primary.name} gagal dan tidak ada cadangan: {reason}")
        result = await self._run(self.fallback, text, gender, voices)
        return replace(result, fallback_reason=reason)

    async def warm_up(self, voices_by_gender: dict[Gender, dict[str, str] | None]) -> dict[str, int]:
        """Cek pra-live: request pendek ke tiap suara primary (cold start 15–20 s di Tahap 0)."""
        out = {}
        for gender, voices in voices_by_gender.items():
            voice = self.primary.voice_for(gender, voices)
            start = time.perf_counter()
            result = await self.primary.synthesize("Halo.", voice)
            self.credits_used += result.credit_cost
            out[voice] = int((time.perf_counter() - start) * 1000)
        return out


def create_tts(settings) -> FailoverTTS:
    cache = AudioCache(Path(settings.CACHE_DIR) / "tts")
    if settings.TTS_MODE == "mock":
        return FailoverTTS(MockTTSProvider(), cache=None)
    edge = EdgeTTSProvider(settings.EDGE_VOICE_MALE, settings.EDGE_VOICE_FEMALE)
    if settings.TTS_PRIMARY == "elevenlabs":
        primary: TTSProvider = ElevenLabsTTSProvider(
            settings.ELEVENLABS_API_KEY,
            settings.ELEVENLABS_MODEL,
            settings.ELEVENLABS_VOICE_MALE,
            settings.ELEVENLABS_VOICE_FEMALE,
        )
    elif settings.TTS_PRIMARY == "edge":
        primary = edge
    else:
        raise ValueError(f"TTS_PRIMARY={settings.TTS_PRIMARY} belum didukung di jalur live")
    fallback = edge if settings.TTS_FALLBACK == "edge" and primary is not edge else None
    return FailoverTTS(primary, fallback, cache)
