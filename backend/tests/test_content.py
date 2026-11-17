"""Konten bukan kode (persona, prompt, kata terlarang, kalimat aman, potongan teks) ada di database; seed hanya data awal."""

import pytest
from sqlalchemy import delete, func, select

from app.agents.supervisor import banned_words, fallback_bank, rule_violations
from app.content import ContentStore, content
from app.db import personas, prompts, supervisor_banned_words, supervisor_fallbacks
from app.prompts import load_prompt
from tests.dbutil import make_db


@pytest.fixture
def db(tmp_path):
    d = make_db(tmp_path)
    content.configure(d)
    yield d
    content.configure(None)  # jangan tinggalkan database tes sebagai sumber konten global


def count(db, table):
    with db.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_seed_fills_database_once(db):
    assert set(content.personas()) == {"raka", "salsa"}
    assert content.prompt("persona").version.startswith("persona-v") and "{name}" in content.prompt("persona").text
    assert "bangsat" in banned_words() and fallback_bank()["raka"]["topic"]
    assert content.snippet("opening_hint") and set(content.snippets_with_prefix("dialog_act.")) >= {"anecdote", "audience"}
    before = [count(db, t) for t in (personas, prompts, supervisor_banned_words, supervisor_fallbacks)]
    assert all(n > 0 for n in before)
    content.configure(db)  # start ulang: tidak menggandakan apa pun
    assert [count(db, t) for t in (personas, prompts, supervisor_banned_words, supervisor_fallbacks)] == before


def test_without_database_content_comes_from_seed():
    store = ContentStore()
    assert set(store.personas()) == {"raka", "salsa"} and "bangsat" in store.banned_words()
    assert store.prompt("showrunner").text and store.snippet("greeting_hint")


def test_prompt_versions_keep_history_and_switch_active(db):
    old = load_prompt("persona")
    content.add_prompt_version("persona", "persona-v99", "<<prompt baru {name}>>", by="admin")
    assert load_prompt("persona").version == "persona-v99" and load_prompt("persona").render(name="Raka") == "<<prompt baru Raka>>"
    rows = {r["version"]: r["active"] for r in content.list_prompts() if r["name"] == "persona"}
    assert rows == {old.version: False, "persona-v99": True}  # riwayat tetap ada
    with pytest.raises(ValueError):
        content.add_prompt_version("persona", "persona-v99", "timpa", by="admin")  # versi tidak boleh ditimpa
    content.activate_prompt("persona", old.version)
    assert load_prompt("persona") == old


def test_admin_changes_are_not_overwritten_by_reseed(db):
    with db.engine.begin() as conn:
        conn.execute(delete(supervisor_banned_words).where(supervisor_banned_words.c.word == "bangsat"))
        conn.execute(delete(supervisor_fallbacks).where(supervisor_fallbacks.c.persona == "salsa"))
    card = content.personas()["raka"].model_copy(update={"background_facts": ["fakta baru dari admin"]})
    content.save_persona("raka", card)
    content.configure(db)  # start ulang
    assert "bangsat" not in banned_words() and "salsa" not in fallback_bank()
    assert content.personas()["raka"].background_facts == ["fakta baru dari admin"]


def test_rules_use_banned_words_from_database(db):
    from app.db import supervisor_banned_words as t
    from sqlalchemy import insert

    with db.engine.begin() as conn:
        conn.execute(insert(t).values(word="katabaru", category="uji"))
    content.invalidate()
    assert "katabaru" in banned_words()
    assert "banned:katabaru" in rule_violations("kamu katabaru deh", [])
