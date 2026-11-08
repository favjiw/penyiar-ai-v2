import pytest

from app.config import Settings
from app.data.personas import load_personas
from app.tts import FailoverTTS, MockTTSProvider, TTSError, VoiceBook
from app.tts.provider import EdgeTTSProvider
from app.tts.catalog import find_voice, load_voice_catalog
from tests.test_api import client  # noqa: F401  (fixture)
from tests.test_show_api import locked_blocker


def test_catalog_ids_are_unique():
    ids = [v.id for v in load_voice_catalog()]
    assert len(ids) == len(set(ids))


def test_catalog_has_current_voices_and_valid_entries():
    catalog = load_voice_catalog()
    ids = {v.id: v for v in catalog}
    assert ids["q8qwd1jY2jS3AWOBeq25"].name == "Pratama" and ids["ffTJE9l3Kt2ipEM32UOc"].name == "Aita"
    assert ids["id-ID-ArdiNeural"].provider == "edge" and find_voice("tidak-ada") is None
    el_male = [v for v in catalog if v.provider == "elevenlabs" and v.gender == "male"]
    el_female = [v for v in catalog if v.provider == "elevenlabs" and v.gender == "female"]
    assert len(el_male) == 6 and len(el_female) == 6


def test_operator_selection_wins_over_defaults_and_resets():
    book = VoiceBook(Settings(_env_file=None), load_personas())
    default_raka, default_salsa = book.voice("edge", "raka"), book.voice("edge", "salsa")
    book.select({"raka": "id-ID-GadisNeural"})
    assert book.voice("edge", "raka") == "id-ID-GadisNeural" and book.voice("edge", "salsa") == default_salsa
    book.select({"salsa": "id-ID-ArdiNeural"})  # menggantikan pilihan sebelumnya, bukan menambah
    assert book.voice("edge", "raka") == default_raka and book.voice("edge", "salsa") == "id-ID-ArdiNeural"
    book.select({})
    assert (book.voice("edge", "raka"), book.voice("edge", "salsa")) == (default_raka, default_salsa)


def test_selection_is_per_provider_so_fallback_keeps_its_own_voice():
    book = VoiceBook(Settings(_env_file=None), load_personas())
    edge_default = book.voice("edge", "raka")
    book.select({"raka": "ffTJE9l3Kt2ipEM32UOc"})  # suara ElevenLabs
    assert book.voice("elevenlabs", "raka") == "ffTJE9l3Kt2ipEM32UOc" and book.voice("edge", "raka") == edge_default


def test_unknown_voice_is_rejected_even_with_mock_tts():
    tts = FailoverTTS(MockTTSProvider(delay_sec=0))
    with pytest.raises(TTSError):
        tts.set_voices({"raka": "suara-ngarang"}, ["raka"])
    tts.set_voices({"raka": "id-ID-ArdiNeural"}, ["raka"])  # valid: tidak ada efek di mock, tidak galat
    book = VoiceBook(Settings(_env_file=None), load_personas())
    with pytest.raises(TTSError):
        book.select({"tidak-ada": "id-ID-ArdiNeural"})


def test_voices_endpoint_lists_catalog(client):
    r = client.get("/api/voices").json()
    assert {v["name"] for v in r["voices"]} >= {"Pratama", "Aita", "Ardi", "Gadis"} and "provider" in r


def test_start_with_unknown_voice_is_422_and_does_not_lock(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    r = client.post("/api/show/start", json={"blocker_id": v["id"], "voices": {"raka": "suara-ngarang"}})
    assert r.status_code == 422 and client.get(f"/api/blocker/{v['id']}").json()["locked"] is False


def test_start_accepts_a_valid_voice_selection(client):
    blocker = locked_blocker(client)
    r = client.post("/api/show/start", json={"blocker_id": blocker["id"], "voices": {"raka": "id-ID-ArdiNeural", "salsa": "id-ID-GadisNeural"}})
    assert r.status_code == 200
    client.post("/api/show/stop")


async def test_filler_files_are_separate_per_voice(tmp_path):
    from app.tts import AudioCache
    from app.tts.filler import FillerBank

    class _Voiced(MockTTSProvider):
        voice = "v1"

        async def synthesize(self, text, persona):
            r = await super().synthesize(text, persona)
            return type(r)(r.audio, r.mime, r.provider, self.voice, r.duration_s)

        def cache_key(self, persona):
            return self.voice

    provider = _Voiced(delay_sec=0)
    tts = FailoverTTS(provider, cache=AudioCache(tmp_path / "tts"))
    persona = load_personas()["raka"]
    bank = FillerBank(tts, tmp_path / "audio")
    await bank.prepare(persona)
    first = {f.url for f in bank._bank["raka"]}
    provider.voice = "v2"
    await bank.prepare(persona)
    second = {f.url for f in bank._bank["raka"]}
    provider.voice = "v1"  # kembali ke suara lama: kena cache, tetap berkas milik v1
    await bank.prepare(persona)
    assert first.isdisjoint(second) and {f.url for f in bank._bank["raka"]} == first


def test_voice_of_another_provider_or_persona_outside_show_is_rejected():
    book = VoiceBook(Settings(_env_file=None), load_personas())
    tts = FailoverTTS(EdgeTTSProvider(book))
    tts.voice_book = book
    with pytest.raises(TTSError, match="tidak cocok"):
        tts.set_voices({"raka": "q8qwd1jY2jS3AWOBeq25"}, ["raka", "salsa"])  # suara ElevenLabs saat TTS aktif Edge
    with pytest.raises(TTSError, match="tidak ikut"):
        tts.set_voices({"salsa": "id-ID-GadisNeural"}, ["raka"])
    tts.set_voices({"raka": "id-ID-GadisNeural"}, ["raka", "salsa"])
    assert tts.voice_for("raka") == "id-ID-GadisNeural"  # id katalog, tanpa rate/pitch


def test_invalid_voice_does_not_change_previous_selection(client):
    ok = client.post("/api/precheck", json={"voices": {}})
    assert ok.status_code == 200
    assert client.post("/api/precheck", json={"voices": {"raka": "suara-ngarang"}}).status_code == 422


def test_start_with_persona_outside_the_show_is_422(client):
    blocker = locked_blocker(client)
    r = client.post("/api/show/start", json={"blocker_id": blocker["id"], "mode": "A", "ai_persona": "raka", "human_name": "D",
                                             "voices": {"salsa": "id-ID-GadisNeural"}})
    assert r.status_code == 422


def test_precheck_does_not_touch_voices_while_a_show_is_running(client):
    blocker = locked_blocker(client)
    assert client.post("/api/show/start", json={"blocker_id": blocker["id"], "voices": {"raka": "id-ID-ArdiNeural"}}).status_code == 200
    r = client.post("/api/precheck", json={"voices": {"raka": "suara-ngarang"}})
    assert r.status_code == 200  # diabaikan selama siaran, bukan galat
    client.post("/api/show/stop")


async def test_turns_jsonl_and_session_start_record_the_voice(tmp_path):
    import json

    from tests.test_session_features import make_a, settle

    engine, _ = make_a(tmp_path)
    engine.start()
    await settle(engine)
    await engine.human_turn("Raka, halo")
    await settle(engine)
    rows = [json.loads(l) for l in open(tmp_path / "sessions" / engine.session_id / "turns.jsonl", encoding="utf-8")]
    human, raka = rows
    assert human["tts_voice"] == "" and raka["tts_voice"] == "mock-raka"
    start = next(e for e in map(json.loads, open(engine.log.path, encoding="utf-8")) if e["type"] == "session_start")
    assert start["voices"] == {"raka": "mock-raka"}
