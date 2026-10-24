import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        LLM_MODE="mock", TTS_MODE="mock", DATA_DIR=str(tmp_path / "data"), LOG_DIR=str(tmp_path / "logs"),
        CACHE_DIR=str(tmp_path / "cache"), AVATAR_DIR=str(tmp_path / "avatar"), _env_file=None,
    )
    with TestClient(build_app(settings)) as c:
        c.log_dir = tmp_path / "logs"
        yield c


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

    listed = client.get("/api/blockers", params={"generation_id": chosen["generation_id"]}).json()
    assert {b["id"] for b in listed} == {v["id"] for v in variants}

    chosen["topics"][0]["judul"] = "Judul diedit"
    chosen["topics"][0]["poin"].append({"text": "poin tambahan"})
    saved = client.put(f"/api/blocker/{chosen['id']}", json=chosen).json()
    assert saved["topics"][0]["judul"] == "Judul diedit"
    assert saved["topics"][0]["poin"][-1]["id"] == f"t1p{len(saved['topics'][0]['poin'])}"

    regen = client.post(f"/api/blocker/{variants[0]['id']}/regenerate", json={"hindari": [chosen["variant_label"]]})
    assert regen.status_code == 200
    assert regen.json()["variant"]["variant_label"] not in {variants[0]["variant_label"], chosen["variant_label"]}

    locked = client.post(f"/api/blocker/{chosen['id']}/lock").json()
    assert locked["locked"]
    assert client.put(f"/api/blocker/{chosen['id']}", json=locked).status_code == 409
    assert client.post(f"/api/blocker/{chosen['id']}/regenerate", json={}).status_code == 409

    v2 = client.post(f"/api/blocker/{chosen['id']}/version").json()
    assert v2["versi"] == 2 and v2["parent_id"] == chosen["id"]

    log_lines = (client.log_dir / "blocker_generations.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["type"] for l in log_lines] == ["generate", "regenerate"]


def test_unknown_and_malformed_ids(client):
    assert client.get("/api/blocker/blk_tidak_ada").status_code == 404
    assert client.get("/api/blocker/..%2Fsecret").status_code == 404


def test_avatar_assets_are_served(client, tmp_path):
    folder = tmp_path / "avatar" / "raka"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"persona": "raka", "clips": []}', encoding="utf-8")
    assert client.get("/avatar-assets/raka/manifest.json").json()["persona"] == "raka"
    assert client.get("/avatar-assets/salsa/manifest.json").status_code == 404
