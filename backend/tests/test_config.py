from app.config import REPO_ROOT, Settings


def test_env_example_loads_as_is():
    s = Settings(_env_file=str(REPO_ROOT / ".env.example"))
    assert s.LLM_MODE == "mock" and s.TTS_MODE == "mock"
    assert s.GEMINI_RPM_PERSONA == 0 and s.rpm_for("persona") == s.GEMINI_RPM_DEFAULT
    assert s.GEMINI_MODEL_PERSONA_FALLBACK == "compat:gemini-3.8-flash"
    assert s.OPENAI_COMPAT_BASE_URL.startswith("https://") and s.OPENAI_COMPAT_API_KEY == ""


def test_pilot_condition_default_and_override():
    assert Settings(_env_file=None).PILOT_CONDITION == "A"
    assert Settings(_env_file=None, PILOT_CONDITION="D").PILOT_CONDITION == "D"


def test_simli_face_falls_back_to_default_face():
    s = Settings(_env_file=None, SIMLI_FACE_ID="default-face", SIMLI_FACE_ID_RAKA="raka-face")
    assert s.simli_face_for("raka") == "raka-face"
    assert s.simli_face_for("salsa") == "default-face"
    assert s.simli_face_for() == "default-face"


def test_voice_gain_db_to_linear_and_snapshot_default():
    s = Settings(_env_file=None, VOICE_GAIN_DB_RAKA=6, VOICE_GAIN_DB_SALSA=-6)
    assert s.voice_gain("raka") == 1.9953 and s.voice_gain("salsa") == 0.5012
    assert Settings(_env_file=None).voice_gain("raka") == 1.0  # tidak diatur = tanpa perubahan
    assert Settings(_env_file=None).voice_gain("tidak-ada") == 1.0
