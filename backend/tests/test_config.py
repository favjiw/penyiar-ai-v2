from app.config import REPO_ROOT, Settings


def test_env_example_loads_as_is():
    s = Settings(_env_file=str(REPO_ROOT / ".env.example"))
    assert s.LLM_MODE == "mock" and s.TTS_MODE == "mock"
    assert s.GEMINI_RPM_PERSONA == 0 and s.rpm_for("persona") == s.GEMINI_RPM_DEFAULT
    assert s.GEMINI_MODEL_PERSONA_FALLBACK == "compat:gemini-3.8-flash"
    assert s.OPENAI_COMPAT_BASE_URL.startswith("https://") and s.OPENAI_COMPAT_API_KEY == ""
