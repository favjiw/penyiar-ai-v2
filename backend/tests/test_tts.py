import asyncio

import pytest

from app.config import Settings
from app.tts import AudioCache, FailoverTTS, MockTTSProvider, TTSError, TTSProvider, TTSResult, create_tts


class _Failing(TTSProvider):
    name = "failing"

    def __init__(self):
        self.calls = 0

    def voice_for(self, gender, voices=None):
        return (voices or {}).get(self.name) or f"f-{gender}"

    async def synthesize(self, text, voice):
        self.calls += 1
        raise TTSError("simulasi")


class _Slow(_Failing):
    name = "slow"

    async def synthesize(self, text, voice):
        await asyncio.sleep(1)
        return TTSResult(b"x", "audio/mpeg", self.name, voice, 1.0)


async def test_mock_duration_scales_with_text():
    tts = FailoverTTS(MockTTSProvider(delay_sec=0))
    short = await tts.synthesize("Halo", "male")
    long = await tts.synthesize("Halo " * 40, "female")
    assert short.mime == "audio/wav" and short.provider == "mock"
    assert long.duration_s > short.duration_s


async def test_failover_uses_fallback_and_records_reason():
    tts = FailoverTTS(_Failing(), MockTTSProvider(delay_sec=0))
    result = await tts.synthesize("Halo", "male")
    assert result.provider == "mock"
    assert "simulasi" in result.fallback_reason


async def test_breaker_skips_primary_after_threshold():
    primary = _Failing()
    tts = FailoverTTS(primary, MockTTSProvider(delay_sec=0), breaker_threshold=2, breaker_cooldown_sec=60)
    for _ in range(4):
        await tts.synthesize("Halo", "female")
    assert primary.calls == 2
    assert tts.breaker_open
    assert (await tts.synthesize("Halo", "female")).fallback_reason == "breaker terbuka"


async def test_timeout_triggers_fallback():
    tts = FailoverTTS(_Slow(), MockTTSProvider(delay_sec=0), timeout_sec=0.05)
    assert (await tts.synthesize("Halo", "male")).provider == "mock"


async def test_no_fallback_raises():
    with pytest.raises(TTSError):
        await FailoverTTS(_Failing()).synthesize("Halo", "male")


async def test_persona_voice_overrides_default():
    provider = _Failing()
    assert provider.voice_for("male", {"failing": "pratama"}) == "pratama"
    assert provider.voice_for("male", {"edge": "x"}) == "f-male"


async def test_cache_returns_stored_audio(tmp_path):
    cache = AudioCache(tmp_path)
    tts = FailoverTTS(MockTTSProvider(delay_sec=0), cache=cache)
    first = await tts.synthesize("Halo Sobat Hits", "male")
    second = await tts.synthesize("Halo Sobat Hits", "male")
    assert not first.cached and second.cached
    assert second.audio == first.audio


def test_factory_mock_and_live_wiring(tmp_path):
    mock = create_tts(Settings(TTS_MODE="mock", CACHE_DIR=str(tmp_path), _env_file=None))
    assert mock.primary.name == "mock" and mock.fallback is None
    live = create_tts(
        Settings(
            TTS_MODE="live",
            TTS_PRIMARY="elevenlabs",
            ELEVENLABS_API_KEY="k",
            ELEVENLABS_MODEL="m",
            ELEVENLABS_VOICE_MALE="vm",
            ELEVENLABS_VOICE_FEMALE="vf",
            CACHE_DIR=str(tmp_path),
            _env_file=None,
        )
    )
    assert live.primary.name == "elevenlabs" and live.fallback.name == "edge"
    assert live.fallback.voice_for("female") == "id-ID-GadisNeural"
