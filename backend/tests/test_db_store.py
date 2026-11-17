"""Materi di database (SQLite untuk tes; sama dengan Postgres lewat SQLAlchemy) berperilaku seperti versi file."""

import json

import pytest

from app import cli
from app.blocker import BlockerInvalid, BlockerLocked, BlockerNotFound, BlockerStore, DbBlockerStore
from app.db import Database
from app.schemas import BlockerPoint
from tests.test_persona import make_blocker


@pytest.fixture
def db(tmp_path):
    d = Database(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    d.create_all()
    yield d
    d.dispose()


@pytest.fixture
def store(db):
    return DbBlockerStore(db)


def _draft(store, n=2):
    b = make_blocker(n)
    b.locked = False
    return store.save(b)


def test_roundtrip_and_overwrite(store):
    b = _draft(store)
    assert store.get(b.id) == b
    edited = b.model_copy(deep=True)
    edited.opening.hook = "pembuka baru"
    saved = store.update(b.id, edited)
    assert store.get(b.id).opening.hook == "pembuka baru" and saved.id == b.id
    assert len(store.list()) == 1  # simpan ulang menimpa, bukan menambah


def test_unknown_and_malformed_ids(store):
    with pytest.raises(BlockerNotFound):
        store.get("blk_tidak_ada")
    with pytest.raises(BlockerNotFound):
        store.get("../etc/passwd")


def test_lock_rules_and_versions(store):
    b = _draft(store)
    locked = store.lock(b.id)
    assert locked.locked and store.get(b.id).locked
    with pytest.raises(BlockerLocked):
        store.update(b.id, b)
    v2 = store.new_version(b.id)
    assert v2.versi == 2 and v2.parent_id == b.id and not v2.locked and v2.id != b.id
    assert {x.id for x in store.list(locked=True)} == {b.id}
    assert {x.id for x in store.list(locked=False)} == {v2.id}


def test_lock_rejects_bad_draft(store):
    b = _draft(store)
    edited = b.model_copy(deep=True)
    edited.topics[0].poin = [BlockerPoint(text="satu")]
    store.update(b.id, edited)
    with pytest.raises(BlockerInvalid, match="Topik 1"):
        store.lock(b.id)
    assert not store.get(b.id).locked


def test_list_filters_by_generation_and_orders_newest_first(store):
    base = make_blocker(2)
    a = base.model_copy(update={"id": "blk_a", "locked": False})
    b = base.model_copy(update={"id": "blk_b", "locked": False})
    a.generation_id, b.generation_id = "g1", "g2"
    a.created_at, b.created_at = "2026-11-01T10:00:00+07:00", "2026-11-02T10:00:00+07:00"
    store.save(a)
    store.save(b)
    assert [x.id for x in store.list()] == [b.id, a.id]
    assert [x.id for x in store.list(generation_id="g1")] == [a.id]


def test_import_files_copies_once(tmp_path, db, monkeypatch, capsys):
    files = BlockerStore(tmp_path / "data")
    b = make_blocker(2)
    b.locked = False
    files.save(b)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "blocker_generations.jsonl").write_text(json.dumps({"ts": "2026-11-01T10:00:00+07:00", "tema": "Kopi"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", db.url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(logs))
    cli.main(["import-files"])
    cli.main(["import-files"])  # ulang aman
    out = capsys.readouterr().out
    assert "1 disalin, 0 sudah ada" in out and "0 disalin, 1 sudah ada" in out
    assert DbBlockerStore(db).get(b.id) == b
