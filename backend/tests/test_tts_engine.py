from app.session_log import read_log
from app.tts import FailoverTTS, MockTTSProvider
from tests.test_mode_a import make, settle
from tests.test_tts import _Failing, fast


async def _run_one_exchange(tts, tmp_path):
    engine, events = make(tmp_path, tts=tts)
    engine.start()
    await settle(engine)
    await engine.human_turn("Salsa, lo tim teh atau kopi?")
    await settle(engine)
    return engine, events


async def test_fallback_is_logged_and_operator_is_told_once(tmp_path):
    tts = fast(_Failing(), MockTTSProvider(delay_sec=0))
    engine, events = await _run_one_exchange(tts, tmp_path)
    turn = next(l for l in read_log(engine.log.path) if l["type"] == "turn")
    assert turn["tts_fallback_used"] is True and turn["tts_provider"] == "mock"
    alerts = [d for t, d in events if t == "alert" and d["stage"] == "tts"]
    assert alerts and "memakai mock" in alerts[0]["message"]
    assert len([a for a in alerts if "memakai mock" in a["message"]]) == 1  # sekali per provider, bukan tiap kalimat


async def test_total_tts_failure_alerts_instead_of_going_silent(tmp_path):
    tts = fast(_Failing())  # tanpa cadangan
    engine, events = await _run_one_exchange(tts, tmp_path)
    alerts = [d["message"] for t, d in events if t == "alert" and d["stage"] == "tts"]
    assert any("tanpa suara" in m for m in alerts)
    log = list(read_log(engine.log.path))
    assert any(l["type"] == "error" and l["stage"] == "tts" for l in log)
    turn = next(l for l in log if l["type"] == "turn")
    assert turn["tts_fallback_used"] is False


async def test_healthy_provider_logs_no_fallback(tmp_path):
    engine, events = await _run_one_exchange(FailoverTTS(MockTTSProvider(delay_sec=0)), tmp_path)
    turn = next(l for l in read_log(engine.log.path) if l["type"] == "turn")
    assert turn["tts_fallback_used"] is False and turn["tts_provider"] == "mock"
    assert not [d for t, d in events if t == "alert" and d["stage"] == "tts"]


async def test_startup_warnings_reach_the_operator(tmp_path):
    tts = FailoverTTS(MockTTSProvider(delay_sec=0), warnings=["TTS_PROVIDER=elevenlabs tetapi ELEVENLABS_API_KEY kosong; memakai Edge TTS (gratis)."])
    _, events = await _run_one_exchange(tts, tmp_path)
    assert any(t == "alert" and "ELEVENLABS_API_KEY" in d["message"] for t, d in events)
