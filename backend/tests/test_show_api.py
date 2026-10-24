from fastapi.testclient import TestClient

from tests.test_api import client  # noqa: F401  (fixture)


def locked_blocker(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    return client.post(f"/api/blocker/{v['id']}/lock").json()


def test_start_requires_locked_blocker(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    assert client.post("/api/show/start", json={"blocker_id": v["id"]}).status_code == 422
    assert client.post("/api/show/pause").status_code == 409


def test_stage_plays_whole_show_over_websocket(client):
    blocker = locked_blocker(client)
    with client.websocket_connect("/ws/session?role=stage") as stage:
        assert stage.receive_json()["type"] == "state"
        started = client.post("/api/show/start", json={"blocker_id": blocker["id"], "seed": 3})
        assert started.status_code == 200
        assert client.post("/api/show/start", json={"blocker_id": blocker["id"]}).status_code == 409

        seen, turns = set(), []
        while True:
            msg = stage.receive_json()
            seen.add(msg["type"])
            if msg["type"] == "turn":
                turns.append(msg["data"])
                audio = client.get(msg["data"]["audio_url"])
                assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
                stage.send_json({"action": "playback", "data": {"playback_id": msg["data"]["playback_id"], "status": "started", "persona": msg["data"]["persona"]}})
                stage.send_json({"action": "playback", "data": {"playback_id": msg["data"]["playback_id"], "status": "ended"}})
            if msg["type"] == "state" and msg["data"]["state"] == "ended":
                break
        assert {"topic_change", "showrunner", "speaking", "output_status"} <= seen
        assert "supervisor" not in seen  # event Supervisor hanya untuk konsol
        assert turns[0]["segment"] == "opening" and turns[-1]["segment"] == "closing"

    session_id = started.json()["session_id"]
    assert session_id in [l["session_id"] for l in client.get("/api/logs").json()]
    log = client.get(f"/api/logs/{session_id}").json()
    assert log[-1]["type"] == "session_end" and log[-1]["reason"] == "completed"


def test_precheck_and_stop(client):
    pre = client.post("/api/precheck").json()
    assert pre["tts_ok"] and pre["models_ok"]
    blocker = locked_blocker(client)
    client.post("/api/show/start", json={"blocker_id": blocker["id"]})
    assert client.post("/api/show/pause").json()["state"] == "paused"
    assert client.post("/api/show/stop").json()["state"] == "ended"
    assert client.get("/api/show").json()["state"] == "ended"
