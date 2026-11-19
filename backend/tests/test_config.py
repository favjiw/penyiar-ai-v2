from app.config import REPO_ROOT, Settings


def test_env_example_loads_as_is():
    s = Settings(_env_file=str(REPO_ROOT / ".env.example"))
    assert s.LLM_MODE == "mock" and s.TTS_MODE == "mock"
    assert s.TTS_PROVIDER == "edge" and s.tts_fallbacks() == ["gtts"]
    assert s.GEMINI_RPM_PERSONA == 0 and s.rpm_for("persona") == s.GEMINI_RPM_DEFAULT
    assert s.GEMINI_MODEL_PERSONA_FALLBACK == ""


def test_elevenlabs_env_coerces_to_free_edge():
    s = Settings(_env_file=None, TTS_PROVIDER="elevenlabs", TTS_FALLBACK="elevenlabs,gtts")
    assert s.TTS_PROVIDER == "edge" and s.tts_fallbacks() == ["gtts"]


def test_pilot_condition_default_and_override():
    assert Settings(_env_file=None).PILOT_CONDITION == "A"
    assert Settings(_env_file=None, PILOT_CONDITION="D").PILOT_CONDITION == "D"


def test_voice_gain_db_to_linear_and_snapshot_default():
    s = Settings(_env_file=None, VOICE_GAIN_DB_RAKA=6, VOICE_GAIN_DB_SALSA=-6)
    assert s.voice_gain("raka") == 1.9953 and s.voice_gain("salsa") == 0.5012
    assert Settings(_env_file=None).voice_gain("raka") == 1.0  # tidak diatur = tanpa perubahan
    assert Settings(_env_file=None).voice_gain("tidak-ada") == 1.0
