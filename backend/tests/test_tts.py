import asyncio
import sys
import types

import pytest

from app.config import Settings
from app.data.personas import load_personas
from app.tts import (
    AudioCache,
    AudioResult,
    EdgeTTSProvider,
    FailoverTTS,
    GTTSProvider,
    MockTTSProvider,
    TTSError,
    TTSProvider,
    VoiceBook,
    create_tts,
)
from app.tts.base import mp3_duration


class _Failing(TTSProvider):
    name = "failing"

    def __init__(self):
        self.calls = 0

    def cache_key(self, persona):
        return f"f-{persona}"

    async def synthesize(self, text, persona):
        self.calls += 1
        raise TTSError("simulasi")


class _Slow(_Failing):
    name = "slow"

    async def synthesize(self, text, persona):
        await asyncio.sleep(1)
        return AudioResult(b"x", "audio/mpeg", self.name, persona, 1.0)


class _FlakyOnce(_Failing):
    """Gagal sekali, lalu berhasil."""

    name = "flaky"

    async def synthesize(self, text, persona):
        self.calls += 1
        if self.calls == 1:
            raise TTSError("gangguan sesaat")
        return AudioResult(b"audio", "audio/mpeg", self.name, persona, 1.0)


class _Empty(_Failing):
    name = "empty"

    async def synthesize(self, text, persona):
        self.calls += 1
        return AudioResult(b"", "audio/mpeg", self.name, persona, 0.0)


def fast(primary, fallback=None, **kw):
    return FailoverTTS(primary, fallback, retry_delay_sec=0, **kw)


async def test_mock_duration_scales_with_text():
    tts = FailoverTTS(MockTTSProvider(delay_sec=0))
    short = await tts.synthesize("Halo", "raka")
    long = await tts.synthesize("Halo " * 40, "salsa")
    assert short.mime == "audio/wav" and short.provider == "mock"
    assert long.duration_s > short.duration_s


async def test_primary_is_retried_once_then_fallback_with_reason():
    primary = _Failing()
    result = await fast(primary, MockTTSProvider(delay_sec=0)).synthesize("Halo", "raka")
    assert primary.calls == 2  # percobaan awal + 1 ulang
    assert result.provider == "mock" and result.fallback_used and "simulasi" in result.fallback_reason


async def test_retry_succeeds_without_fallback():
    primary = _FlakyOnce()
    result = await fast(primary, MockTTSProvider(delay_sec=0), breaker_threshold=5).synthesize("Halo", "raka")
    assert primary.calls == 2 and result.provider == "flaky" and not result.fallback_used


async def test_breaker_skips_primary_after_threshold():
    primary = _Failing()
    tts = fast(primary, MockTTSProvider(delay_sec=0), breaker_threshold=2, breaker_cooldown_sec=60)
    for _ in range(4):
        await tts.synthesize("Halo", "salsa")
    assert primary.calls == 2 and tts.breaker_open
    assert (await tts.synthesize("Halo", "salsa")).fallback_reason == "breaker terbuka"


async def test_timeout_triggers_fallback():
    tts = fast(_Slow(), MockTTSProvider(delay_sec=0), timeout_sec=0.05, retries=0)
    assert (await tts.synthesize("Halo", "raka")).provider == "mock"


async def test_empty_audio_counts_as_failure():
    result = await fast(_Empty(), MockTTSProvider(delay_sec=0)).synthesize("Halo", "raka")
    assert result.provider == "mock" and "kosong" in result.fallback_reason


async def test_fallbacks_are_tried_in_order_and_all_failing_raises():
    result = await fast(_Failing(), [_Failing(), MockTTSProvider(delay_sec=0)]).synthesize("Halo", "raka")
    assert result.provider == "mock"
    with pytest.raises(TTSError, match="Semua TTS gagal"):
        await fast(_Failing(), [_Failing()]).synthesize("Halo", "raka")


async def test_no_fallback_raises():
    with pytest.raises(TTSError):
        await fast(_Failing()).synthesize("Halo", "raka")


async def test_cache_returns_stored_audio(tmp_path):
    tts = FailoverTTS(MockTTSProvider(delay_sec=0), cache=AudioCache(tmp_path))
    first = await tts.synthesize("Halo Sobat Hits", "raka")
    second = await tts.synthesize("Halo Sobat Hits", "raka")
    assert not first.cached and second.cached and second.audio == first.audio


def settings(**kw):
    return Settings(_env_file=None, **kw)


def test_voice_priority_env_then_card_then_gender_default():
    personas = load_personas()
    assert VoiceBook(settings(), personas).voice("edge", "raka") == personas["raka"].voices["edge"]
    assert VoiceBook(settings(EDGE_VOICE_RAKA="id-ID-Lain"), personas).voice("edge", "raka") == "id-ID-Lain"
    personas["raka"].voices.pop("edge")
    assert VoiceBook(settings(EDGE_VOICE_MALE="id-ID-Pria"), personas).voice("edge", "raka") == "id-ID-Pria"
    with pytest.raises(TTSError):
        VoiceBook(settings(), personas).voice("edge", "tidak-ada")


def test_prosody_per_persona_from_env():
    book = VoiceBook(settings(EDGE_RATE_RAKA="+10%", EDGE_PITCH_SALSA="+5Hz"), load_personas())
    assert book.prosody("raka") == ("+10%", "-2Hz")
    assert book.prosody("salsa") == ("+6%", "+5Hz")


async def test_edge_provider_passes_voice_rate_and_pitch(monkeypatch):
    seen = {}

    class FakeCommunicate:
        def __init__(self, text, voice, **kw):
            seen.update(text=text, voice=voice, **kw)

        async def stream(self):
            yield {"type": "WordBoundary"}
            yield {"type": "audio", "data": b"\xff\xfb" * 3000}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    provider = EdgeTTSProvider(VoiceBook(settings(), load_personas()))
    result = await provider.synthesize("Halo", "salsa")
    assert (seen["voice"], seen["rate"], seen["pitch"]) == ("id-ID-GadisNeural", "+6%", "+2Hz")
    assert result.provider == "edge" and result.duration_s > 0
    # Kunci cache memuat prosodi: mengubah rate/pitch tidak memutar audio lama.
    other = EdgeTTSProvider(VoiceBook(settings(EDGE_RATE_SALSA="+20%"), load_personas()))
    assert provider.cache_key("salsa") != other.cache_key("salsa")
    assert provider.cache_key("raka") != provider.cache_key("salsa")


def _mp3(frames: int) -> bytes:
    return (b"\xff\xfb\x90\x00" + b"\x00" * 413) * frames  # MPEG1 L3 128 kbps 44,1 kHz: 417 byte per frame


def test_mp3_duration_sums_frames():
    assert mp3_duration(_mp3(10)) == pytest.approx(10 * 1152 / 44100, rel=1e-3)
    assert mp3_duration(b"bukan mp3") == 0.0
    assert mp3_duration(b"ID3\x04\x00\x00\x00\x00\x00\x05abcde" + _mp3(2)) == pytest.approx(2 * 1152 / 44100, rel=1e-3)


async def test_gtts_provider_wraps_library(monkeypatch):
    class FakeGTTS:
        def __init__(self, text, lang):
            self.lang = lang

        def write_to_fp(self, fp):
            fp.write(_mp3(20))

    monkeypatch.setitem(sys.modules, "gtts", types.SimpleNamespace(gTTS=FakeGTTS))
    result = await GTTSProvider().synthesize("Halo", "raka")
    assert result.provider == "gtts" and result.mime == "audio/mpeg"
    assert result.duration_s == pytest.approx(20 * 1152 / 44100, rel=1e-3)


def test_factory_defaults_to_edge_with_gtts_fallback(tmp_path):
    tts = create_tts(settings(TTS_MODE="live", CACHE_DIR=str(tmp_path)))
    assert tts.primary.name == "edge" and [f.name for f in tts.fallbacks] == ["gtts"] and tts.warnings == []
    assert tts.status()["primary"] == "edge"


def test_factory_mock(tmp_path):
    mock = create_tts(settings(TTS_MODE="mock", CACHE_DIR=str(tmp_path)))
    assert mock.primary.name == "mock" and mock.fallback is None


def test_factory_elevenlabs_with_key_and_fallback_chain(tmp_path):
    tts = create_tts(
        settings(TTS_MODE="live", TTS_PROVIDER="elevenlabs", TTS_FALLBACK="edge,gtts", ELEVENLABS_API_KEY="k", ELEVENLABS_MODEL="m", CACHE_DIR=str(tmp_path))
    )
    assert tts.primary.name == "elevenlabs" and [f.name for f in tts.fallbacks] == ["edge", "gtts"] and tts.warnings == []
    assert tts.primary.cache_key("raka") == load_personas()["raka"].voices["elevenlabs"]


def test_factory_elevenlabs_without_key_falls_back_to_edge_with_warning(tmp_path):
    tts = create_tts(settings(TTS_MODE="live", TTS_PROVIDER="elevenlabs", TTS_FALLBACK="edge,gtts", CACHE_DIR=str(tmp_path)))
    assert tts.primary.name == "edge"
    assert [f.name for f in tts.fallbacks] == ["gtts"]  # edge sudah jadi utama
    assert any("ELEVENLABS_API_KEY" in w for w in tts.status()["warnings"])


def test_factory_fallback_none_and_unknown(tmp_path):
    assert create_tts(settings(TTS_MODE="live", TTS_FALLBACK="none", CACHE_DIR=str(tmp_path))).fallbacks == []
    with pytest.raises(ValueError, match="tidak dikenal"):
        create_tts(settings(TTS_MODE="live", TTS_FALLBACK="festival", CACHE_DIR=str(tmp_path)))
