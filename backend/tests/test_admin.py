import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import app_settings
from app.main import build_app
from app.secretbox import generate_key
from tests.test_auth import PASSWORD, as_user

SECRETS_KEY = generate_key()


def make_settings(tmp_path, **kw):
    return Settings(
        LLM_MODE="mock", TTS_MODE="mock", DATA_DIR=str(tmp_path / "data"),
        CACHE_DIR=str(tmp_path / "cache"), AUTH_REQUIRED=True, SECRETS_KEY=SECRETS_KEY,
        SIMLI_FACE_ID_RAKA="face-raka-0001", SIMLI_FACE_ID_SALSA="face-salsa-0001", _env_file=None, **kw,
    )


@pytest.fixture
def client(tmp_path):
    with TestClient(build_app(make_settings(tmp_path))) as c:
        auth = c.app.state.auth
        auth.create_user("admin", PASSWORD, "admin")
        auth.create_user("opa", PASSWORD, "operator")
        c.tmp_path = tmp_path
        yield c


def fields(cfg):
    return {f["key"]: f for g in cfg["groups"] for f in g["fields"]}


def put(client, **values):
    return client.put("/api/admin/config", json={"values": values})


# ── akses ────────────────────────────────────────────────────────────────────
def test_only_admin_reaches_admin_api(client):
    paths = ["/api/admin/config", "/api/admin/voices", "/api/admin/faces"]
    for p in paths:
        assert client.get(p).status_code == 401
    as_user(client, "opa")
    for p in paths:
        assert client.get(p).status_code == 403
    assert client.put("/api/admin/config", json={"values": {}}).status_code == 403
    assert client.post("/api/admin/test/gemini").status_code == 403


# ── setelan ──────────────────────────────────────────────────────────────────
def test_non_secret_setting_applies_without_restart_and_can_be_cleared(client):
    as_user(client, "admin")
    s = client.app.state.settings
    before = s.GEMINI_MODEL_PERSONA
    r = put(client, GEMINI_MODEL_PERSONA="model-baru-1")
    assert r.status_code == 200 and r.json()["applied"] is True and r.json()["pending"] is False
    assert s.GEMINI_MODEL_PERSONA == "model-baru-1"
    assert fields(r.json())["GEMINI_MODEL_PERSONA"]["source"] == "admin"
    r = put(client, GEMINI_MODEL_PERSONA=None)  # kembali ke .env
    assert s.GEMINI_MODEL_PERSONA == before and fields(r.json())["GEMINI_MODEL_PERSONA"]["source"] == "env"


def test_validation_is_atomic_and_uses_settings_rules(client):
    as_user(client, "admin")
    s = client.app.state.settings
    assert put(client, ELEVENLABS_STABILITY="2").status_code == 422  # di luar 0..1
    assert put(client, TTS_PROVIDER="suara-ngarang").status_code == 422
    assert put(client, BUKAN_SETELAN="x").status_code == 422
    r = put(client, GEMINI_MODEL_PERSONA="tidak-boleh-tersimpan", ELEVENLABS_STABILITY="2")
    assert r.status_code == 422 and s.GEMINI_MODEL_PERSONA != "tidak-boleh-tersimpan"
    assert put(client, ELEVENLABS_STABILITY="0.4", VOICE_GAIN_DB_RAKA="3").status_code == 200
    assert s.ELEVENLABS_STABILITY == 0.4 and s.VOICE_GAIN_DB_RAKA == 3
    assert put(client, ELEVENLABS_STABILITY="").status_code == 200  # angka kosong = hapus timpaan
    assert s.ELEVENLABS_STABILITY is None


def test_secrets_are_encrypted_masked_and_survive_restart(client):
    as_user(client, "admin")
    r = put(client, GEMINI_API_KEY="AIzaSy-rahasia-sekali-1234")
    assert r.status_code == 200
    assert "rahasia-sekali" not in r.text and fields(r.json())["GEMINI_API_KEY"]["masked"].endswith("1234")
    assert "rahasia-sekali" not in client.get("/api/admin/config").text
    with client.app.state.db.engine.connect() as conn:
        row = conn.execute(select(app_settings).where(app_settings.c.key == "GEMINI_API_KEY")).first()
    assert row.secret and row.value.startswith("enc:") and "rahasia-sekali" not in row.value
    assert client.app.state.settings.GEMINI_API_KEY == "AIzaSy-rahasia-sekali-1234"
    assert put(client, GEMINI_API_KEY="").status_code == 200  # kosong = biarkan
    assert client.app.state.settings.GEMINI_API_KEY == "AIzaSy-rahasia-sekali-1234"

    # Proses baru dengan database yang sama memuat kunci dari database, bukan dari .env.
    with TestClient(build_app(make_settings(client.tmp_path))) as again:
        assert again.app.state.settings.GEMINI_API_KEY == "AIzaSy-rahasia-sekali-1234"

    # Kunci induk berganti: nilai lama tidak terbaca dan diabaikan (kembali ke .env), bukan crash.
    with TestClient(build_app(make_settings(client.tmp_path).model_copy(update={"SECRETS_KEY": generate_key()}))) as other:
        assert other.app.state.settings.GEMINI_API_KEY == ""


def test_secret_needs_secrets_key(tmp_path):
    s = make_settings(tmp_path).model_copy(update={"SECRETS_KEY": ""})
    with TestClient(build_app(s)) as c:
        c.app.state.auth.create_user("admin", PASSWORD, "admin")
        as_user(c, "admin")
        assert c.get("/api/admin/config").json()["secrets_enabled"] is False
        r = put(c, GEMINI_API_KEY="x" * 20)
        assert r.status_code == 422 and "SECRETS_KEY" in r.json()["detail"]
        assert put(c, GEMINI_MODEL_PERSONA="boleh-tanpa-kunci-induk").status_code == 200


def test_changes_wait_for_the_show_to_end(client):
    as_user(client, "admin")
    s = client.app.state.settings
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    client.post("/api/blockers", json=v)
    assert client.post("/api/show/start", json={"blocker_id": v["id"], "mode": "B"}).status_code == 200
    before = s.GEMINI_MODEL_PERSONA
    r = put(client, GEMINI_MODEL_PERSONA="model-saat-live")
    assert r.status_code == 200 and r.json()["live"] is True and r.json()["pending"] is True and r.json()["applied"] is False
    assert s.GEMINI_MODEL_PERSONA == before  # siaran yang berjalan tidak berubah
    assert fields(r.json())["GEMINI_MODEL_PERSONA"]["value"] == "model-saat-live"  # tetapi tersimpan dan terlihat di halaman
    client.post("/api/show/stop")
    cfg = client.get("/api/admin/config").json()  # membuka halaman = menerapkan yang menunggu
    assert s.GEMINI_MODEL_PERSONA == "model-saat-live" and cfg["pending"] is False


def test_service_test_runs_with_saved_settings(client):
    as_user(client, "admin")
    r = client.post("/api/admin/test/gemini").json()
    assert r["ok"] is True and "mode uji" in r["message"]  # LLM_MODE=mock di tes
    assert client.post("/api/admin/test/elevenlabs").json() == {"ok": False, "message": "Kunci API ElevenLabs belum diisi."}
    assert client.post("/api/admin/test/simli").json()["ok"] is False
    assert client.post("/api/admin/test/lainnya").status_code == 422


# ── suara ────────────────────────────────────────────────────────────────────
def test_voice_catalog_is_seeded_then_managed_in_database(client):
    as_user(client, "admin")
    voices = client.get("/api/admin/voices").json()
    assert {"Pratama", "Aita", "Ardi", "Gadis"} <= {v["name"] for v in voices}
    r = client.post("/api/admin/voices", json={"id": "id-ID-NabillaNeural", "provider": "edge", "name": "Nabilla", "gender": "female"})
    assert r.status_code == 201
    assert client.post("/api/admin/voices", json={"id": "id-ID-NabillaNeural", "provider": "edge", "name": "x", "gender": "female"}).status_code == 422  # dobel
    assert client.post("/api/admin/voices", json={"id": "../etc", "provider": "elevenlabs", "name": "x", "gender": "male"}).status_code == 422  # bukan ID suara
    assert client.post("/api/admin/voices", json={"id": "kosong", "provider": "edge", "name": " ", "gender": "male"}).status_code == 422
    assert client.patch("/api/admin/voices/id-ID-NabillaNeural", json={"name": "Nabilla B", "notes": "ceria"}).json()["name"] == "Nabilla B"
    as_user(client, "opa")  # operator melihat daftar yang sama di pilihan sebelum live
    assert "Nabilla B" in {v["name"] for v in client.get("/api/voices").json()["voices"]}
    as_user(client, "admin")
    assert client.delete("/api/admin/voices/id-ID-NabillaNeural").status_code == 200
    assert client.delete("/api/admin/voices/id-ID-NabillaNeural").status_code == 404
    # Menghapus semua tidak mengisi ulang dari file (sudah diisi satu kali).
    for v in client.get("/api/admin/voices").json():
        client.delete(f"/api/admin/voices/{v['id']}")
    assert client.get("/api/admin/voices").json() == []
    with TestClient(build_app(make_settings(client.tmp_path))) as again:
        as_user(again, "admin")
        assert again.get("/api/admin/voices").json() == []


def test_adding_elevenlabs_voice_without_key_warns_but_saves(client):
    as_user(client, "admin")
    r = client.post("/api/admin/voices", json={"id": "AbCdEf123456", "provider": "elevenlabs", "name": "Suara Baru", "gender": "male"})
    assert r.status_code == 201 and "belum diisi" in r.json()["warning"]


# ── wajah Simli ──────────────────────────────────────────────────────────────
def test_faces_seeded_from_env_chosen_per_persona_and_protected_while_used(client):
    as_user(client, "admin")
    faces = client.get("/api/admin/faces").json()
    assert {f["id"] for f in faces} >= {"face-raka-0001", "face-salsa-0001"}
    assert client.post("/api/admin/faces", json={"id": "bad id!", "name": "x"}).status_code == 422
    assert client.post("/api/admin/faces", json={"id": "face-baru-0001", "name": "Wajah baru"}).status_code == 201
    assert client.post("/api/admin/faces", json={"id": "face-baru-0001", "name": "dobel"}).status_code == 422
    assert client.delete("/api/admin/faces/face-raka-0001").status_code == 409  # sedang dipilih untuk Raka
    assert put(client, SIMLI_FACE_ID_RAKA="face-baru-0001").status_code == 200
    assert client.app.state.settings.simli_face_for("raka") == "face-baru-0001"  # dipakai /api/simli/token
    assert client.delete("/api/admin/faces/face-raka-0001").status_code == 200


# ── konten: persona, prompt, teks, Supervisor ────────────────────────────────
def test_content_endpoints_are_admin_only(client):
    paths = ["/api/admin/personas", "/api/admin/prompts", "/api/admin/snippets", "/api/admin/supervisor"]
    as_user(client, "opa")
    assert all(client.get(p).status_code == 403 for p in paths)
    as_user(client, "admin")
    assert all(client.get(p).status_code == 200 for p in paths)


def test_persona_edits_reach_the_next_show_prompt(client):
    from app.agents.persona import PersonaAgent
    from app.data.personas import load_personas
    import random

    as_user(client, "admin")
    cards = {c["id"]: c for c in client.get("/api/admin/personas").json()}
    assert set(cards) == {"raka", "salsa"}
    raka = {**cards["raka"], "speaking_style": "gaya baru dari admin", "catchphrases": ["  ", "ciee dong"]}
    r = client.put("/api/admin/personas/raka", json=raka)
    assert r.status_code == 200 and r.json()["catchphrases"] == ["ciee dong"]  # baris kosong dibuang
    assert load_personas()["raka"].speaking_style == "gaya baru dari admin"
    assert "gaya baru dari admin" in PersonaAgent(None, "m", random.Random(1)).system_prompt(load_personas()["raka"])
    assert client.put("/api/admin/personas/raka", json={**raka, "id": "salsa"}).status_code == 422
    assert client.put("/api/admin/personas/lain", json={**raka, "id": "lain"}).status_code == 404
    assert client.put("/api/admin/personas/raka", json={**raka, "gender": "x"}).status_code == 422


def test_prompt_versions_validate_placeholders_and_switch_active(client):
    from app.prompts import load_prompt

    as_user(client, "admin")
    rows = client.get("/api/admin/prompts").json()
    persona_rows = [r for r in rows if r["name"] == "persona"]
    assert len(persona_rows) == 1 and persona_rows[0]["active"] and "name" in persona_rows[0]["placeholders"]
    old_version = persona_rows[0]["version"]
    body = client.get(f"/api/admin/prompts/persona/{old_version}").json()["body"]

    r = client.post("/api/admin/prompts/persona", json={"version": "persona-v100", "body": "Tanpa placeholder apa pun, terlalu pendek untuk dipakai."})
    assert r.status_code == 422 and "Placeholder hilang" in r.json()["detail"]
    assert client.post("/api/admin/prompts/persona", json={"version": "persona-v100", "body": body + "\n{tidak_dikenal}"}).status_code == 422
    assert client.post("/api/admin/prompts/persona", json={"version": "persona-v100", "body": body + "\nTambahan baris dari admin."}).status_code == 201
    assert load_prompt("persona").version == "persona-v100" and load_prompt("persona").text.endswith("Tambahan baris dari admin.")
    assert client.post("/api/admin/prompts/persona", json={"version": "persona-v100", "body": body}).status_code == 422  # versi tidak boleh ditimpa
    assert client.post("/api/admin/prompts/tidak-ada", json={"version": "v1", "body": "x" * 20}).status_code == 404
    assert client.post(f"/api/admin/prompts/persona/{old_version}/activate").status_code == 200
    assert load_prompt("persona").version == old_version  # riwayat tetap, bisa kembali


def test_snippets_are_editable_and_keep_their_placeholders(client):
    from app.content import content

    as_user(client, "admin")
    snippets = {s["key"]: s for s in client.get("/api/admin/snippets").json()}
    assert {"turn.tema", "style_guide", "dialog_act.anecdote", "sup.persona", "fallback_last_resort"} <= set(snippets)
    assert set(snippets["turn.tema"]["placeholders"]) == {"tema", "variant"}
    assert client.put("/api/admin/snippets/turn.tema", json={"text": "TOPIK: {tema}"}).status_code == 422  # {variant} hilang
    assert client.put("/api/admin/snippets/turn.tema", json={"text": "  "}).status_code == 422
    assert client.put("/api/admin/snippets/turn.tema", json={"text": "JUDUL SIARAN: {tema} / {variant}"}).status_code == 200
    assert content.text("turn.tema", tema="Kopi", variant="v1") == "JUDUL SIARAN: Kopi / v1"
    assert client.put("/api/admin/snippets/tidak.ada", json={"text": "x"}).status_code == 404


def test_supervisor_words_and_fallback_lines_are_managed(client):
    from app.agents.supervisor import banned_words, fallback_bank

    as_user(client, "admin")
    sup = client.get("/api/admin/supervisor").json()
    assert {"bangsat", "kasar_berat"} <= {(b["word"], b["category"])[i] for b in sup["banned"] for i in (0, 1)}
    assert client.post("/api/admin/supervisor/banned", json={"word": "  KataBaru ", "category": "uji"}).status_code == 201
    assert "katabaru" in banned_words()
    assert client.post("/api/admin/supervisor/banned", json={"word": "katabaru", "category": "uji"}).status_code == 422
    assert client.delete("/api/admin/supervisor/banned/katabaru").status_code == 200
    assert client.delete("/api/admin/supervisor/banned/katabaru").status_code == 404
    assert "katabaru" not in banned_words()

    assert client.post("/api/admin/supervisor/fallbacks", json={"persona": "lain", "kind": "topic", "text": "x"}).status_code == 422
    assert client.post("/api/admin/supervisor/fallbacks", json={"persona": "raka", "kind": "salah", "text": "x"}).status_code == 422
    assert client.post("/api/admin/supervisor/fallbacks", json={"persona": "raka", "kind": "topic", "text": "Kalimat aman baru."}).status_code == 201
    assert "Kalimat aman baru." in fallback_bank()["raka"]["topic"]
    line = next(f for f in client.get("/api/admin/supervisor").json()["fallbacks"] if f["text"] == "Kalimat aman baru.")
    assert client.delete(f"/api/admin/supervisor/fallbacks/{line['id']}").status_code == 200
    assert client.delete(f"/api/admin/supervisor/fallbacks/{line['id']}").status_code == 404


# ── parameter perilaku ───────────────────────────────────────────────────────
def test_behavior_parameters_are_editable_and_validated_together(client):
    from app.tuning import tuning

    as_user(client, "admin")
    keys = {f["key"] for g in client.get("/api/admin/config").json()["groups"] for f in g["fields"]}
    assert {"POINT_TIME_LIMIT_S", "HISTORY_TURNS", "CATCHPHRASE_PROBABILITY", "SUPERVISOR_MODE", "VOICE_TOPIC_SWITCH", "GEMINI_RPD_DEFAULT"} <= keys
    assert put(client, HISTORY_TURNS="5", CATCHPHRASE_PROBABILITY="0.5").status_code == 200
    assert tuning.HISTORY_TURNS == 5 and tuning.CATCHPHRASE_PROBABILITY == 0.5  # kode membaca nilai yang berlaku
    assert put(client, CATCHPHRASE_PROBABILITY="2").status_code == 422  # di luar 0..1
    assert put(client, VOICE_TOPIC_SWITCH="mungkin").status_code == 422  # bool hanya true/false
    assert put(client, VOICE_TOPIC_SWITCH="false").status_code == 200 and client.app.state.settings.VOICE_TOPIC_SWITCH is False
    # aturan antar-setelan: batas penutupan harus lebih kecil dari batas waktu poin
    r = put(client, POINT_WRAP_S="200")
    assert r.status_code == 422 and "POINT_WRAP_S" in r.json()["detail"]
    assert client.app.state.settings.POINT_WRAP_S != 200
