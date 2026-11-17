import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from starlette.websockets import WebSocketDisconnect

from app.auth import COOKIE, hash_password, verify_password
from app.config import Settings
from app.db import auth_sessions, generation_log
from app.main import build_app

PASSWORD = "sandi-uji-panjang"


def make_settings(tmp_path, **kw):
    return Settings(
        LLM_MODE="mock", TTS_MODE="mock", DATA_DIR=str(tmp_path / "data"), LOG_DIR=str(tmp_path / "logs"),
        CACHE_DIR=str(tmp_path / "cache"), AUTH_REQUIRED=True, _env_file=None, **kw,
    )


@pytest.fixture
def client(tmp_path):
    with TestClient(build_app(make_settings(tmp_path))) as c:
        auth = c.app.state.auth
        auth.create_user("admin", PASSWORD, "admin", "Admin")
        auth.create_user("opa", PASSWORD, "operator")
        auth.create_user("rani", PASSWORD, "penyiar")
        yield c


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def as_user(client, username):
    client.cookies.clear()
    assert login(client, username).status_code == 200
    return client


# ── kata sandi ───────────────────────────────────────────────────────────────
def test_password_hash_roundtrip():
    h = hash_password("rahasia-panjang")
    assert h != hash_password("rahasia-panjang")  # garam acak
    assert verify_password("rahasia-panjang", h)
    assert not verify_password("salah", h)
    assert not verify_password("x", "bukan-hash")


# ── gerbang login ────────────────────────────────────────────────────────────
def test_everything_but_login_and_minimal_health_needs_login(client):
    assert client.get("/api/health").json() == {"status": "ok"}  # cek Docker tanpa rincian
    for method, path in [("get", "/api/blockers"), ("get", "/api/show"), ("get", "/api/voices"), ("get", "/api/logs"),
                         ("get", "/api/auth/me"), ("get", "/api/users"), ("get", "/audio/x.mp3"),
                         ("post", "/api/ptt/turn"), ("post", "/api/blocker/generate"), ("post", "/api/simli/token")]:
        assert getattr(client, method)(path).status_code == 401, path


def test_login_sets_httponly_cookie_and_me_works(client):
    r = login(client, "opa")
    assert r.status_code == 200 and r.json()["user"]["role"] == "operator"
    set_cookie = r.headers["set-cookie"].lower()
    assert COOKIE in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
    me = client.get("/api/auth/me").json()
    assert me["user"]["username"] == "opa" and me["auth_required"] is True
    assert "password" not in str(me).lower()
    assert "models" in client.get("/api/health").json()  # sudah masuk: rincian lengkap


def test_wrong_password_and_unknown_user_look_the_same(client):
    a = login(client, "opa", "salah-salah-salah")
    b = login(client, "tidak-ada")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_logout_revokes_session(client):
    as_user(client, "opa")
    token = client.cookies.get(COOKIE)
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(COOKIE, token)  # token lama tidak berlaku lagi di server
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client):
    as_user(client, "opa")
    with client.app.state.db.engine.begin() as conn:
        conn.execute(update(auth_sessions).values(expires_at=int(time.time()) - 1))
    assert client.get("/api/auth/me").status_code == 401


def test_session_slides_forward_when_half_used(client):
    as_user(client, "opa")
    life = client.app.state.auth.lifetime_s
    soon = int(time.time()) + life // 4
    with client.app.state.db.engine.begin() as conn:
        conn.execute(update(auth_sessions).values(expires_at=soon))
    assert client.get("/api/auth/me").status_code == 200
    with client.app.state.db.engine.connect() as conn:
        new = conn.execute(auth_sessions.select()).first().expires_at
    assert new > soon + life // 2


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert login(client, "rani", "salah-salah-salah").status_code == 401
    r = login(client, "rani")  # sandi benar pun ditolak selama diblokir
    assert r.status_code == 429 and "Retry-After" in r.headers


# ── peran ────────────────────────────────────────────────────────────────────
def test_penyiar_only_gets_broadcaster_endpoints(client):
    as_user(client, "rani")
    assert client.get("/api/show").status_code == 200
    assert client.post("/api/show/next").status_code == 409  # lolos peran; hanya tidak ada siaran
    assert client.post("/api/show/undo-topic").status_code == 409
    assert client.post("/api/ptt/turn", json={"text": "halo"}).status_code == 409
    for path in ("/api/show/stop", "/api/show/pause", "/api/show/resume"):
        assert client.post(path).status_code == 403, path
    assert client.get("/api/blockers").status_code == 403
    assert client.get("/api/voices").status_code == 403
    assert client.post("/api/show/start", json={"blocker_id": "blk_x", "mode": "B"}).status_code == 403
    assert client.get("/api/users").status_code == 403


def test_operator_runs_the_show_but_cannot_manage_users(client):
    as_user(client, "opa")
    assert client.get("/api/blockers").status_code == 200
    assert client.post("/api/show/stop").status_code == 409
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"username": "baru", "password": PASSWORD}).status_code == 403


def test_blocker_flow_persists_in_database(client):
    as_user(client, "opa")
    variants = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 2}).json()["variants"]
    assert len(variants) == 3
    first = variants[0]
    assert client.get("/api/blockers").json() == []  # belum ada yang disimpan
    assert client.post("/api/blockers", json=first).status_code == 201  # yang dipilih operator
    assert client.get(f"/api/blocker/{first['id']}").json()["tema"] == "Kopi"
    assert client.post(f"/api/blocker/{first['id']}/lock").json()["locked"] is True
    assert [b["id"] for b in client.get("/api/blockers").json()] == [first["id"]]
    assert not (Path(client.app.state.settings.DATA_DIR) / "blockers").exists()  # materi ada di database, bukan file
    with client.app.state.db.engine.connect() as conn:  # catatan pembuatan materi juga di database, bukan file
        rows = conn.execute(generation_log.select()).all()
    assert len(rows) == 1 and rows[0].data["tema"] == "Kopi" and len(rows[0].data["blocker_ids"]) == 3
    assert not (Path(client.app.state.settings.LOG_DIR) / "blocker_generations.jsonl").exists()


# ── WebSocket ────────────────────────────────────────────────────────────────
def test_websocket_requires_login_and_role(client):
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/session?role=prompter"):
            pass
    as_user(client, "rani")
    cookie = {"cookie": f"{COOKIE}={client.cookies.get(COOKIE)}"}
    with client.websocket_connect("/ws/session?role=prompter", headers=cookie) as ws:
        assert ws.receive_json()["type"] == "state"
    for role in ("console", "stage"):  # penyiar tidak boleh
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/session?role={role}", headers=cookie):
                pass
    as_user(client, "opa")
    cookie = {"cookie": f"{COOKIE}={client.cookies.get(COOKIE)}"}
    with client.websocket_connect("/ws/session?role=console", headers=cookie) as ws:
        assert ws.receive_json()["type"] == "state"


def test_websocket_rejects_foreign_origin(client):
    as_user(client, "opa")
    headers = {"cookie": f"{COOKIE}={client.cookies.get(COOKIE)}", "origin": "https://situs-jahat.example"}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/session?role=console", headers=headers):
            pass


# ── kelola pengguna ──────────────────────────────────────────────────────────
def test_admin_manages_users(client):
    as_user(client, "admin")
    r = client.post("/api/users", json={"username": "Budi", "password": PASSWORD, "role": "operator", "display_name": "Budi"})
    assert r.status_code == 201 and r.json()["username"] == "budi"  # dinormalkan ke huruf kecil
    assert client.post("/api/users", json={"username": "budi", "password": PASSWORD}).status_code == 409
    assert client.post("/api/users", json={"username": "x", "password": PASSWORD}).status_code == 422  # nama terlalu pendek
    assert client.post("/api/users", json={"username": "pendek1", "password": "pendek"}).status_code == 422
    assert client.post("/api/users", json={"username": "peran1", "password": PASSWORD, "role": "dewa"}).status_code == 422
    users = client.get("/api/users").json()
    assert {u["username"] for u in users} >= {"admin", "opa", "rani", "budi"}
    assert all("password" not in u and "password_hash" not in u for u in users)


def test_deactivating_user_kills_their_session(client):
    other = TestClient(client.app)
    assert login(other, "rani").status_code == 200
    assert other.get("/api/show").status_code == 200
    as_user(client, "admin")
    rani = next(u for u in client.get("/api/users").json() if u["username"] == "rani")
    assert client.patch(f"/api/users/{rani['id']}", json={"active": False}).status_code == 200
    assert other.get("/api/show").status_code == 401
    assert login(other, "rani").status_code == 401


def test_cannot_remove_last_admin_or_demote_self(client):
    as_user(client, "admin")
    me = client.get("/api/auth/me").json()["user"]
    r = client.patch(f"/api/users/{me['id']}", json={"role": "operator"})
    assert r.status_code == 422
    r = client.patch(f"/api/users/{me['id']}", json={"active": False})
    assert r.status_code == 422
    assert client.patch("/api/users/9999", json={"active": False}).status_code == 404


def test_change_own_password(client):
    as_user(client, "opa")
    assert client.post("/api/auth/password", json={"current": "salah-salah", "new": "sandi-baru-panjang"}).status_code == 403
    assert client.post("/api/auth/password", json={"current": PASSWORD, "new": "pendek"}).status_code == 422
    assert client.post("/api/auth/password", json={"current": PASSWORD, "new": "sandi-baru-panjang"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401  # sesi dicabut, masuk ulang
    assert login(client, "opa").status_code == 401
    assert login(client, "opa", "sandi-baru-panjang").status_code == 200


# ── mode pengembangan ────────────────────────────────────────────────────────
def test_auth_off_keeps_everything_open_and_uses_files(tmp_path):
    s = Settings(LLM_MODE="mock", TTS_MODE="mock", DATA_DIR=str(tmp_path / "data"), LOG_DIR=str(tmp_path / "logs"),
                 CACHE_DIR=str(tmp_path / "cache"), _env_file=None)
    with TestClient(build_app(s)) as c:
        assert c.app.state.db is None
        assert c.get("/api/blockers").status_code == 200
        me = c.get("/api/auth/me").json()
        assert me["auth_required"] is False and me["user"]["role"] == "admin"
        assert c.get("/api/users").status_code == 404  # tanpa login tidak ada pengguna untuk dikelola
