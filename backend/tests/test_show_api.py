from fastapi.testclient import TestClient

from tests.test_api import client  # noqa: F401  (fixture)


def locked_blocker(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    return client.post(f"/api/blocker/{v['id']}/lock").json()


def test_start_locks_a_draft_blocker_automatically(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    assert not v["locked"]
    assert client.post("/api/show/start", json={"blocker_id": v["id"]}).status_code == 200
    assert client.get(f"/api/blocker/{v['id']}").json()["locked"] is True
    assert client.put(f"/api/blocker/{v['id']}", json=v).status_code == 409  # tidak bisa diubah selama/sesudah live
    client.post("/api/show/stop")


def test_start_rejects_draft_that_cannot_be_locked(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    v["topics"].append({**v["topics"][0], "poin": v["topics"][0]["poin"][:1]})  # topik manual baru, baru satu poin
    assert client.put(f"/api/blocker/{v['id']}", json=v).status_code == 200
    r = client.post("/api/show/start", json={"blocker_id": v["id"]})
    assert r.status_code == 422 and "bahan obrolan" in r.json()["detail"]
    assert client.get(f"/api/blocker/{v['id']}").json()["locked"] is False
    assert client.post("/api/show/pause").status_code == 409  # tidak ada siaran


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
        assert turns[0]["segment"] == "opening" and turns[-1]["segment"] == "closing"

    session_id = started.json()["session_id"]
    assert session_id in [l["session_id"] for l in client.get("/api/logs").json()]
    log = client.get(f"/api/logs/{session_id}").json()
    assert log[-1]["type"] == "session_end" and log[-1]["reason"] == "completed"


def _output_status(ws):
    while True:
        msg = ws.receive_json()
        if msg["type"] == "output_status":
            return msg["data"]


def test_only_first_stage_owns_audio_console_is_muted(client):
    """PRD v2.7 FR-10: /stage satu-satunya pemutar audio; konsol bisu; stage kedua tidak ikut memutar."""
    with client.websocket_connect("/ws/session?role=console") as console:
        console.receive_json()  # state
        st = _output_status(console)
        assert st["is_audio_owner"] is False and st["audio_owner_role"] is None
        with client.websocket_connect("/ws/session?role=stage") as stage:
            stage.receive_json()  # state
            assert _output_status(stage)["is_audio_owner"] is True
            st = _output_status(console)
            assert st["is_audio_owner"] is False and st["audio_owner_role"] == "stage" and st["clients"]["stage"] == 1
            with client.websocket_connect("/ws/session?role=stage") as second:
                second.receive_json()
                assert _output_status(second)["is_audio_owner"] is False
            # Stage pertama tetap pemilik setelah stage kedua pergi
        st = _output_status(console)
        for _ in range(5):
            if st["clients"]["stage"] == 0:
                break
            st = _output_status(console)
        assert st["clients"]["stage"] == 0 and st["audio_owner_role"] is None


def test_stage_audio_ready_and_level_relay(client):
    with client.websocket_connect("/ws/session?role=console") as console:
        console.receive_json()
        _output_status(console)
        with client.websocket_connect("/ws/session?role=stage") as stage:
            stage.receive_json()
            _output_status(stage)
            assert _output_status(console)["audio_ready"] is False
            stage.send_json({"action": "audio_state", "data": {"blocked": False, "ready": True}})
            assert _output_status(console)["audio_ready"] is True
            stage.send_json({"action": "level", "data": {"persona": "raka", "level": 3}})
            for _ in range(10):
                msg = console.receive_json()
                if msg["type"] == "level":
                    break
            assert msg["type"] == "level" and msg["data"] == {"persona": "raka", "level": 1.0}
        # konsol tidak boleh mengirim level atas nama stage
        console.send_json({"action": "level", "data": {"persona": "raka", "level": 0.5}})
        console.send_json({"action": "ping"})
        for _ in range(5):
            msg = console.receive_json()
            assert msg["type"] != "level"
            if msg["type"] == "pong":
                break


def test_precheck_and_stop(client):
    pre = client.post("/api/precheck").json()
    assert pre["tts_ok"] and pre["models_ok"]
    blocker = locked_blocker(client)
    client.post("/api/show/start", json={"blocker_id": blocker["id"]})
    assert client.post("/api/show/pause").json()["state"] == "paused"
    assert client.post("/api/show/stop").json()["state"] == "ended"
    assert client.get("/api/show").json()["state"] == "ended"


def test_mode_a_start_ptt_and_next(client):
    blocker = locked_blocker(client)
    assert client.post("/api/show/start", json={"blocker_id": blocker["id"], "mode": "A", "ai_persona": "budi"}).status_code == 422
    snap = client.post("/api/show/start", json={"blocker_id": blocker["id"], "mode": "A", "ai_persona": "raka", "human_name": "Kak Dimas"}).json()
    assert snap["mode"] == "A" and snap["human"]["name"] == "Kak Dimas" and snap["ai_persona"] == "raka"
    import time

    deadline = time.time() + 10
    while client.get("/api/show").json()["fillers_ready"] == 0 and time.time() < deadline:
        time.sleep(0.05)  # bank filler disiapkan di latar
    with client.websocket_connect("/ws/session?role=prompter") as prompter:
        prompter.receive_json()
        r = client.post("/api/ptt/turn", json={"text": "Raka, lo tim kopi atau teh?", "stt_ms": 300})
        assert r.status_code == 200
        seen = []
        while "turn" not in seen:
            seen.append(prompter.receive_json()["type"])
        assert "human_turn" in seen and "filler" in seen
    assert client.post("/api/show/next").json()["segment"] == "topic"
    assert client.post("/api/ptt/turn", json={"text": ""}).status_code == 422
    client.post("/api/show/stop")


def test_ptt_rejected_in_mode_b(client):
    blocker = locked_blocker(client)
    client.post("/api/show/start", json={"blocker_id": blocker["id"], "mode": "B"})
    assert client.post("/api/ptt/turn", json={"text": "halo"}).status_code == 409
    client.post("/api/show/stop")


def test_mode_c_is_rejected(client):
    blocker = locked_blocker(client)
    r = client.post("/api/show/start", json={"blocker_id": blocker["id"], "mode": "C"})
    assert r.status_code == 422


def test_invalid_ai_persona_does_not_lock_the_draft(client):
    v = client.post("/api/blocker/generate", json={"tema": "Kopi", "jumlah_topik": 1, "jumlah_varian": 2}).json()["variants"][0]
    r = client.post("/api/show/start", json={"blocker_id": v["id"], "mode": "A", "ai_persona": "tidak-ada"})
    assert r.status_code == 422 and client.get(f"/api/blocker/{v['id']}").json()["locked"] is False
