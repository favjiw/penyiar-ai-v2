import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        LLM_MODE="mock", TTS_MODE="mock", DATA_DIR=str(tmp_path / "data"), LOG_DIR=str(tmp_path / "logs"),
        CACHE_DIR=str(tmp_path / "cache"), POINT_TIME_LIMIT_S=0, _env_file=None,  # tes API lama: Showrunner per topik
    )
    with TestClient(build_app(settings)) as c:
        c.log_dir = tmp_path / "logs"
        yield c


def chosen_variant(client, tema="Kopi"):
    """Alur operator: buat materi, lalu simpan yang dipilih (generate sendiri tidak menyimpan)."""
    v = client.post("/api/blocker/generate", json={"tema": tema, "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    return client.post("/api/blockers", json=v).json()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["llm_mode"] == "mock" and body["tts"]["primary"] == "mock"


def test_generate_validates_input(client):
    assert client.post("/api/blocker/generate", json={"tema": ""}).status_code == 422
    assert client.post("/api/blocker/generate", json={"tema": "x" * 61}).status_code == 422
    assert client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_varian": 4}).status_code == 422


def test_full_blocker_flow(client):
    resp = client.post("/api/blocker/generate", json={"tema": "Kopi", "catatan": "buat maba", "jumlah_topik": 2})
    assert resp.status_code == 200
    variants = resp.json()["variants"]
    assert len(variants) == 3
    chosen = variants[1]

    # Generate tidak menyimpan apa pun; operator memilih yang disimpan.
    assert client.get("/api/blockers").json() == []
    assert client.get(f"/api/blocker/{chosen['id']}").status_code == 404
    assert client.put(f"/api/blocker/{chosen['id']}", json=chosen).status_code == 404  # edit butuh materi yang sudah disimpan

    chosen["locked"] = True  # klien tidak bisa menyimpan sebagai terkunci
    assert client.post("/api/blockers", json=chosen).status_code == 201
    assert [b["id"] for b in client.get("/api/blockers").json()] == [chosen["id"]]
    assert client.get(f"/api/blocker/{chosen['id']}").json()["locked"] is False
    assert client.post("/api/blockers", json=chosen).status_code == 201  # simpan ulang aman
    assert len(client.get("/api/blockers").json()) == 1

    chosen["topics"][0]["judul"] = "Judul diedit"
    chosen["topics"][0]["poin"].append({"text": "poin tambahan"})
    saved = client.put(f"/api/blocker/{chosen['id']}", json=chosen).json()
    assert saved["topics"][0]["judul"] == "Judul diedit"
    assert saved["topics"][0]["poin"][-1]["id"] == f"t1p{len(saved['topics'][0]['poin'])}"

    # Buat ulang varian yang belum disimpan: hasilnya juga belum disimpan.
    regen = client.post("/api/blocker/regenerate", json={"blocker": variants[0], "hindari": [chosen["variant_label"]]})
    assert regen.status_code == 200
    assert regen.json()["variant"]["variant_label"] not in {variants[0]["variant_label"], chosen["variant_label"]}
    assert len(client.get("/api/blockers").json()) == 1

    locked = client.post(f"/api/blocker/{chosen['id']}/lock").json()
    assert locked["locked"]
    assert client.put(f"/api/blocker/{chosen['id']}", json=locked).status_code == 409
    assert client.post("/api/blockers", json=locked).status_code == 409
    assert client.post("/api/blocker/regenerate", json={"blocker": locked}).status_code == 409

    v2 = client.post(f"/api/blocker/{chosen['id']}/version").json()
    assert v2["versi"] == 2 and v2["parent_id"] == chosen["id"]

    log_lines = (client.log_dir / "blocker_generations.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["type"] for l in log_lines] == ["generate", "regenerate"]


def test_unknown_and_malformed_ids(client):
    assert client.get("/api/blocker/blk_tidak_ada").status_code == 404
    assert client.get("/api/blocker/..%2Fsecret").status_code == 404


def test_frontend_is_served_with_spa_fallback_and_never_shadows_the_api(tmp_path):
    """Hosting: satu proses menyajikan halaman; rute klien dijawab index.html, path API yang salah tetap 404."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import build_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "logo.png").write_bytes(b"png")
    settings = Settings(
        _env_file=None, LLM_MODE="mock", TTS_MODE="mock", FRONTEND_DIST=str(dist), DATA_DIR=str(tmp_path / "data"),
        LOG_DIR=str(tmp_path / "logs"), CACHE_DIR=str(tmp_path / "cache"),
    )
    with TestClient(build_app(settings)) as c:
        assert "shell" in c.get("/").text and "shell" in c.get("/stage").text and "shell" in c.get("/prompter").text
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/logo.png").content == b"png"
        assert c.get("/api/health").json()["llm_mode"] == "mock"  # API tidak tertimpa
        assert c.get("/api/tidak-ada").status_code == 404 and c.get("/audio/tidak-ada.mp3").status_code == 404
        (tmp_path / "secret.txt").write_text("RAHASIA", encoding="utf-8")
        for attempt in ("/..%2fsecret.txt", "/%2e%2e/secret.txt", "/../secret.txt"):
            assert "RAHASIA" not in c.get(attempt).text  # tidak boleh keluar dari folder dist
