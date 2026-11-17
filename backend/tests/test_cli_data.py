"""Pemindahan data berkas lama ke database dan ekspor log untuk riset."""

import json

from app import cli
from app.blocker import BlockerStore
from app.db import database_for
from app.config import Settings
from app.session_log import SessionLogger
from app.show.turnlog import read_turns
from tests.test_persona import make_blocker


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_import_files_moves_blockers_logs_turns_once(tmp_path, monkeypatch, capsys):
    data, logs, sessions = tmp_path / "olddata", tmp_path / "oldlogs", tmp_path / "oldsessions"
    b = make_blocker(2)
    (data / "blockers").mkdir(parents=True)
    (data / "blockers" / f"{b.id}.json").write_text(b.model_dump_json(), encoding="utf-8")  # terkunci: harus tetap terkunci
    write_jsonl(logs / "blocker_generations.jsonl", [{"ts": "2026-11-01T10:00:00+07:00", "tema": "Kopi"}])
    write_jsonl(logs / "show_20261101_100000_ab12.jsonl", [{"type": "session_start", "ts": "t1", "mode": "B"}, {"type": "session_end", "ts": "t2"}])
    write_jsonl(sessions / "show_20261101_100000_ab12" / "turns.jsonl", [{"turn_idx": 0, "text": "halo"}, {"turn_idx": 1, "text": "hai"}])
    (sessions / "show_20261101_100000_ab12" / "blocker.json").write_text(b.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "app"))

    args = ["import-files", "--data-dir", str(data), "--log-dir", str(logs), "--sessions-dir", str(sessions)]
    cli.main(args)
    cli.main(args)  # ulang aman
    out = capsys.readouterr().out
    assert "1 disalin, 0 sudah ada" in out and "0 disalin, 1 sudah ada" in out
    assert "1 sesi disalin, 0 sudah ada" in out and "0 sesi disalin, 1 sudah ada" in out

    db = database_for(Settings(_env_file=None))
    assert BlockerStore(db).get(b.id).locked is True
    assert [e["type"] for e in SessionLogger("show_20261101_100000_ab12", db).events()] == ["session_start", "session_end"]
    assert [t["text"] for t in read_turns(db, "show_20261101_100000_ab12")] == ["halo", "hai"]


def test_export_session_writes_the_files_research_scripts_read(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "app"))
    db = database_for(Settings(_env_file=None))
    log = SessionLogger("show_20261102_a", db)
    log.event("session_start", mode="A")
    log.event("session_end", reason="stopped")
    out = tmp_path / "ekspor"
    cli.main(["export-session", "show_20261102_a", "--out", str(out)])
    folder = out / "show_20261102_a"
    lines = [json.loads(l) for l in (folder / "show_20261102_a.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["type"] for l in lines] == ["session_start", "session_end"]
    assert (folder / "turns.jsonl").exists()
    try:
        cli.main(["export-session", "tidak_ada", "--out", str(out)])
    except SystemExit as e:
        assert "tidak punya log" in str(e)
    else:
        raise AssertionError("sesi tak dikenal harus ditolak")
