"""TTS (FR-6): provider yang bisa diganti lewat `.env`, cache file, retry, dan cadangan.

Default selama pengembangan: Edge TTS (gratis). ElevenLabs dipakai untuk demo cukup dengan
`TTS_PROVIDER=elevenlabs`. gTTS menjadi cadangan terakhir (`TTS_FALLBACK=gtts`).

Diadaptasi dari repo lama (conversational-ai@v1-format-clock). Catatan:
- ElevenLabs memakai endpoint streaming (byte pertama ±0,45 s di Tahap 0) dan mencatat header
  `character-cost` untuk pemantauan kredit;
- Edge memakai resolver DNS sistem (aiodns menggantung di laptop streaming) dan rate/pitch per persona;
- provider utama diulang sekali bila gagal, lalu cadangan berurutan; breaker melewati provider yang
  gagal beruntun supaya giliran berikutnya tidak menunggu timeout lagi;
- audio kosong atau berdurasi 0 dianggap gagal, bukan siaran bisu.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from app.tts.base import (
    AudioResult,
    TTSError,
    TTSProvider,
    TTSResult,
    cbr_mp3_duration,
    mp3_duration,
    silence_wav,
    wav_duration,
)
from app.tts.voices import VoiceBook

logger = logging.getLogger(__name__)

__all__ = [
    "AudioCache",
    "AudioResult",
    "EdgeTTSProvider",
    "ElevenLabsTTSProvider",
    "FailoverTTS",
    "GTTSProvider",
    "MockTTSProvider",
    "TTSError",
    "TTSProvider",
    "TTSResult",
    "create_tts",
    "provider_label",
]

PROVIDER_LABELS = {"edge": "Edge (gratis)", "elevenlabs": "ElevenLabs", "gtts": "gTTS (gratis)", "mock": "mock (hening)"}


def provider_label(name: str) -> str:
    return PROVIDER_LABELS.get(name, name)


# ── Mock ─────────────────────────────────────────────────────────────────────


class MockTTSProvider(TTSProvider):
    """Keheningan sepanjang ±60 ms per karakter (TTS_MODE=mock)."""

    name = "mock"

    def __init__(self, delay_sec: float = 0.05):
        self._delay = delay_sec

    def cache_key(self, persona: str) -> str:
        return f"mock-{persona}"

    async def synthesize(self, text, persona):
        await asyncio.sleep(self._delay)
        audio = silence_wav(max(500, len(text) * 60))
        return AudioResult(audio, "audio/wav", self.name, self.cache_key(persona), wav_duration(audio), latency_ms=int(self._delay * 1000))


# ── ElevenLabs ───────────────────────────────────────────────────────────────


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"
    OUTPUT_FORMAT = "mp3_44100_128"
    KBPS = 128

    def __init__(self, api_key: str, model: str, voices: VoiceBook, timeout_sec: float = 15.0):
        if not (api_key and model):
            raise ValueError("ELEVENLABS_API_KEY dan ELEVENLABS_MODEL wajib untuk TTS ElevenLabs")
        self._key, self._model = api_key, model
        self._voices = voices
        self._timeout = timeout_sec

    def cache_key(self, persona: str) -> str:
        return self._voices.voice(self.name, persona)

    async def synthesize(self, text, persona):
        import httpx

        voice = self._voices.voice(self.name, persona)
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
        return AudioResult(
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
    """Edge TTS (pustaka tidak resmi `edge-tts`), gratis tanpa API key; keluaran MP3 48 kbps CBR."""

    name = "edge"
    KBPS = 48

    def __init__(self, voices: VoiceBook):
        self._voices = voices

    def cache_key(self, persona: str) -> str:
        rate, pitch = self._voices.prosody(persona)
        return f"{self._voices.voice(self.name, persona)}|{rate}|{pitch}"

    async def synthesize(self, text, persona):
        import aiohttp
        import edge_tts

        voice = self._voices.voice(self.name, persona)
        rate, pitch = self._voices.prosody(persona)
        start = time.perf_counter()
        first = None
        chunks: list[bytes] = []
        # aiodns (bila terpasang) menggantung ±20 s di laptop ini; pakai resolver sistem.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, connector=connector).stream():
            if chunk["type"] == "audio":
                if first is None:
                    first = time.perf_counter() - start
                chunks.append(chunk["data"])
        audio = b"".join(chunks)
        if not audio:
            raise TTSError(f"Edge TTS mengembalikan audio kosong untuk {voice}")
        return AudioResult(
            audio,
            "audio/mpeg",
            self.name,
            voice,
            cbr_mp3_duration(audio, self.KBPS),
            latency_ms=int((time.perf_counter() - start) * 1000),
            first_byte_ms=int((first or 0) * 1000),
        )


# ── gTTS (cadangan) ──────────────────────────────────────────────────────────


class GTTSProvider(TTSProvider):
    """gTTS bahasa Indonesia (Google Translate TTS), gratis; satu suara untuk semua persona."""

    name = "gtts"

    def __init__(self, lang: str = "id"):
        self._lang = lang

    def cache_key(self, persona: str) -> str:
        return f"gtts-{self._lang}"

    async def synthesize(self, text, persona):
        from gtts import gTTS

        def run() -> bytes:
            buf = io.BytesIO()
            gTTS(text=text, lang=self._lang).write_to_fp(buf)
            return buf.getvalue()

        start = time.perf_counter()
        audio = await asyncio.to_thread(run)
        if not audio:
            raise TTSError("gTTS mengembalikan audio kosong")
        return AudioResult(
            audio, "audio/mpeg", self.name, self.cache_key(persona), mp3_duration(audio), latency_ms=int((time.perf_counter() - start) * 1000)
        )


# ── Cache ────────────────────────────────────────────────────────────────────


def _audio_duration(audio: bytes, ext: str, provider: str) -> float:
    if ext == "wav":
        return wav_duration(audio)
    if provider == "edge":
        return cbr_mp3_duration(audio, EdgeTTSProvider.KBPS)
    if provider == "elevenlabs":
        return cbr_mp3_duration(audio, ElevenLabsTTSProvider.KBPS)
    return mp3_duration(audio)


class AudioCache:
    """Cache file berkunci hash(provider, kunci suara, teks). Dipakai untuk filler dan teks berulang."""

    def __init__(self, cache_dir: str | Path):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _stem(self, provider: str, voice: str, text: str) -> str:
        return hashlib.sha256(f"{provider}:{voice}:{text}".encode()).hexdigest()[:20]

    def get(self, provider: str, voice: str, text: str) -> AudioResult | None:
        stem = self._stem(provider, voice, text)
        for ext, mime in (("mp3", "audio/mpeg"), ("wav", "audio/wav")):
            path = self._dir / f"{stem}.{ext}"
            if path.exists():
                audio = path.read_bytes()
                dur = _audio_duration(audio, ext, provider)
                if audio and dur > 0:
                    return AudioResult(audio, mime, provider, voice, dur, cached=True)
        return None

    def put(self, voice_key: str, text: str, result: AudioResult) -> Path:
        path = self._dir / f"{self._stem(result.provider, voice_key, text)}.{result.ext}"
        path.write_bytes(result.audio)
        return path


# ── Retry + cadangan + breaker ───────────────────────────────────────────────


class FailoverTTS:
    """Pintu masuk TTS untuk Show Engine: provider utama (diulang sekali) → cadangan berurutan.

    Provider yang gagal beruntun `breaker_threshold` kali dilewati selama `breaker_cooldown_sec`.
    Bila semuanya gagal, `synthesize` melempar `TTSError`; pemanggil wajib memberi tahu operator
    (siaran tidak boleh bisu tanpa kabar).
    """

    def __init__(
        self,
        primary: TTSProvider,
        fallback: TTSProvider | Sequence[TTSProvider] | None = None,
        cache: AudioCache | None = None,
        timeout_sec: float = 8.0,
        breaker_threshold: int = 2,
        breaker_cooldown_sec: float = 60.0,
        retries: int = 1,
        retry_delay_sec: float = 0.3,
        warnings: Sequence[str] = (),
    ):
        self.primary = primary
        if fallback is None:
            self.fallbacks: list[TTSProvider] = []
        elif isinstance(fallback, TTSProvider):
            self.fallbacks = [fallback]
        else:
            self.fallbacks = list(fallback)
        self.cache = cache
        self._timeout = timeout_sec
        self._threshold, self._cooldown = breaker_threshold, breaker_cooldown_sec
        self._retries, self._retry_delay = retries, retry_delay_sec
        self._failures = 0
        self._open_until = 0.0
        self.credits_used = 0
        self.fallback_uses = 0
        self.last_provider = ""
        self.warnings: list[str] = list(warnings)

    @property
    def fallback(self) -> TTSProvider | None:
        return self.fallbacks[0] if self.fallbacks else None

    @property
    def breaker_open(self) -> bool:
        return time.monotonic() < self._open_until

    def status(self) -> dict:
        return {
            "primary": self.primary.name,
            "fallback": self.fallback.name if self.fallback else None,
            "fallbacks": [f.name for f in self.fallbacks],
            "breaker_open": self.breaker_open,
            "consecutive_failures": self._failures,
            "credits_used": self.credits_used,
            "fallback_uses": self.fallback_uses,
            "last_provider": self.last_provider or None,
            "warnings": list(self.warnings),
        }

    async def _attempt(self, provider: TTSProvider, text: str, persona: str) -> AudioResult:
        key = provider.cache_key(persona)
        if self.cache and (hit := self.cache.get(provider.name, key, text)):
            return hit
        result = await asyncio.wait_for(provider.synthesize(text, persona), self._timeout)
        if not result.audio or result.duration_s <= 0:
            raise TTSError(f"{provider.name} mengembalikan audio kosong atau berdurasi 0")
        if self.cache:
            self.cache.put(key, text, result)
        return result

    async def synthesize(self, text: str, persona: str) -> AudioResult:
        reason = ""
        if not self.breaker_open:
            for attempt in range(1 + self._retries):
                try:
                    result = await self._attempt(self.primary, text, persona)
                    self._failures = 0
                    self.credits_used += result.credit_cost
                    self.last_provider = result.provider
                    return result
                except Exception as e:
                    reason = f"{type(e).__name__}: {e}"[:300]
                    self._failures += 1
                    logger.warning("TTS %s gagal (percobaan %d/%d): %s", self.primary.name, attempt + 1, 1 + self._retries, reason)
                    if self._failures >= self._threshold:
                        self._open_until = time.monotonic() + self._cooldown
                        logger.warning("TTS %s gagal %d kali; breaker terbuka %.0fs", self.primary.name, self._failures, self._cooldown)
                        break
                    if attempt < self._retries:
                        await asyncio.sleep(self._retry_delay)
        else:
            reason = "breaker terbuka"
        errors = [f"{self.primary.name}: {reason}"]
        for provider in self.fallbacks:
            try:
                result = await self._attempt(provider, text, persona)
            except Exception as e:
                errors.append(f"{provider.name}: {type(e).__name__}: {e}"[:300])
                logger.warning("TTS cadangan %s gagal: %s", provider.name, errors[-1])
                continue
            self.fallback_uses += 1
            self.last_provider = result.provider
            self.credits_used += result.credit_cost
            return replace(result, fallback_reason=reason)
        raise TTSError("Semua TTS gagal: " + " | ".join(errors))

    async def warm_up(self, personas: Sequence[str]) -> dict[str, int]:
        """Cek pra-live: request pendek ke tiap suara provider utama (cold start 15–20 s di ElevenLabs, Tahap 0)."""
        out = {}
        for persona in personas:
            start = time.perf_counter()
            result = await self.primary.synthesize("Halo.", persona)
            self.credits_used += result.credit_cost
            out[result.voice] = int((time.perf_counter() - start) * 1000)
        return out


def _build(name: str, settings, voices: VoiceBook, warnings: list[str]) -> TTSProvider | None:
    if name == "edge":
        return EdgeTTSProvider(voices)
    if name == "gtts":
        try:
            import gtts  # noqa: F401
        except ImportError:
            warnings.append("Pustaka gTTS belum terpasang (pip install gTTS); cadangan gTTS dilewati.")
            return None
        return GTTSProvider()
    if name == "elevenlabs":
        if not (settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_MODEL):
            return None
        return ElevenLabsTTSProvider(settings.ELEVENLABS_API_KEY, settings.ELEVENLABS_MODEL, voices)
    raise ValueError(f"TTS provider {name!r} tidak dikenal")


def create_tts(settings, personas: dict | None = None) -> FailoverTTS:
    if settings.TTS_MODE == "mock":
        return FailoverTTS(MockTTSProvider(), cache=None)
    if personas is None:
        from app.data.personas import load_personas

        personas = load_personas()
    voices = VoiceBook(settings, personas)
    cache = AudioCache(Path(settings.CACHE_DIR) / "tts")
    warnings: list[str] = []

    name = settings.TTS_PROVIDER
    primary = _build(name, settings, voices, warnings)
    if primary is None:  # ElevenLabs diminta tetapi key kosong: jangan crash, pakai Edge dan beri tahu operator.
        warnings.append(f"TTS_PROVIDER={name} tetapi ELEVENLABS_API_KEY atau ELEVENLABS_MODEL kosong; memakai Edge TTS (gratis).")
        name, primary = "edge", EdgeTTSProvider(voices)

    fallbacks: list[TTSProvider] = []
    for fb in settings.tts_fallbacks():
        if fb == name or any(f.name == fb for f in fallbacks):
            continue
        provider = _build(fb, settings, voices, warnings)
        if provider is not None:
            fallbacks.append(provider)
    return FailoverTTS(
        primary,
        fallbacks,
        cache,
        timeout_sec=settings.TTS_TIMEOUT_SEC,
        retries=settings.TTS_RETRIES,
        warnings=warnings,
    )
