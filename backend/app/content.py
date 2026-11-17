"""Konten yang bukan kode: persona, prompt, potongan teks prompt, kata terlarang, dan kalimat aman Supervisor.

Sumbernya tabel di database. Data awal ada di `backend/seed/` dan hanya dibaca saat pertama jalan
(tidak menimpa apa pun yang sudah ada di database). Tanpa database (skrip, tes unit) konten dibaca langsung dari seed.

Prompt berversi: tiap (nama, versi) satu baris, yang `active` dipakai. Versi baru = baris baru (riwayat tetap ada),
dan versi + hash isinya dicatat di `session_start` supaya sebuah sesi bisa diulang.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select, update

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
_VERSION_RE = re.compile(r"^<!--\s*version:\s*(\S+)\s*-->\s*\n")
SNIPPET_PREFIX = "snippet."
SNIPPET_VERSION = "seed"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    def render(self, **values: object) -> str:
        """Isi placeholder {nama}; kurung kurawal lain (mis. contoh JSON) dibiarkan."""
        out = self.text
        for key, value in values.items():
            out = out.replace("{" + key + "}", str(value))
        return out


def parse_prompt(name: str, raw: str) -> Prompt:
    match = _VERSION_RE.match(raw)
    if not match:
        raise ValueError(f"Prompt {name} tanpa baris versi '<!-- version: ... -->'")
    return Prompt(name, match.group(1), raw[match.end():])


class ContentStore:
    def __init__(self) -> None:
        self._db = None
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}

    # ── pengaturan ───────────────────────────────────────────────────────────
    def configure(self, db) -> None:
        """Pakai database (None = baca dari seed). Mengisi data awal yang belum ada."""
        with self._lock:
            self._db, self._cache = db, {}
        if db is not None:
            self._seed(db)

    def invalidate(self) -> None:
        with self._lock:
            self._cache = {}

    def _cached(self, key: str, build):
        with self._lock:
            if key not in self._cache:
                self._cache[key] = build()
            return self._cache[key]

    # ── data awal ────────────────────────────────────────────────────────────
    def _seed(self, db) -> None:
        from app.blocker.store import now_iso
        from app.db import app_settings, personas, prompts, supervisor_banned_words, supervisor_fallbacks

        now = now_iso()
        with db.engine.begin() as conn:
            def flagged(name: str) -> bool:
                return conn.execute(select(app_settings.c.key).where(app_settings.c.key == name)).first() is not None

            def flag(name: str) -> None:
                conn.execute(insert(app_settings).values(key=name, value="1", secret=False, updated_at=now, updated_by="sistem"))

            # Persona: hanya id yang belum ada (perubahan admin tidak ditimpa).
            have = set(conn.execute(select(personas.c.id)).scalars())
            for p in sorted((SEED_DIR / "persona").glob("*.json")):
                if p.stem not in have:
                    conn.execute(insert(personas).values(id=p.stem, data=json.loads(p.read_text(encoding="utf-8")), updated_at=now))

            # Prompt: (nama, versi) yang belum ada; aktif hanya bila nama itu belum punya versi aktif.
            for p in sorted((SEED_DIR / "prompts").glob("*.md")):
                pr = parse_prompt(p.stem, p.read_text(encoding="utf-8"))
                if conn.execute(select(prompts.c.name).where(prompts.c.name == pr.name, prompts.c.version == pr.version)).first():
                    continue
                has_active = conn.execute(select(prompts.c.name).where(prompts.c.name == pr.name, prompts.c.active.is_(True))).first()
                conn.execute(insert(prompts).values(name=pr.name, version=pr.version, body=pr.text, active=not has_active, created_at=now, created_by="sistem"))

            # Potongan teks: kunci yang belum ada.
            snippets = json.loads((SEED_DIR / "snippets.json").read_text(encoding="utf-8"))
            have_snip = set(conn.execute(select(prompts.c.name).where(prompts.c.name.like(SNIPPET_PREFIX + "%"))).scalars())
            for key, text in snippets.items():
                if key.startswith(SNIPPET_PREFIX) and key not in have_snip:
                    conn.execute(insert(prompts).values(name=key, version=SNIPPET_VERSION, body=text, active=True, created_at=now, created_by="sistem"))

            # Kata terlarang dan kalimat aman: satu kali (penghapusan oleh admin tidak diisi ulang).
            if not flagged("meta.banned_words_seeded"):
                banned = json.loads((SEED_DIR / "supervisor" / "banned_words.json").read_text(encoding="utf-8"))
                for category, words in banned.items():
                    if category.startswith("_"):
                        continue
                    for w in words:
                        conn.execute(insert(supervisor_banned_words).values(word=w.strip().lower(), category=category))
                flag("meta.banned_words_seeded")
            if not flagged("meta.fallbacks_seeded"):
                bank = json.loads((SEED_DIR / "supervisor" / "fallback.json").read_text(encoding="utf-8"))
                for persona, kinds in bank.items():
                    for kind, lines in kinds.items():
                        for text in lines:
                            conn.execute(insert(supervisor_fallbacks).values(persona=persona, kind=kind, text=text))
                flag("meta.fallbacks_seeded")

    # ── persona ──────────────────────────────────────────────────────────────
    def personas(self) -> dict:
        from app.schemas import PersonaCard

        def build():
            if self._db is None:
                return {p.stem: PersonaCard.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted((SEED_DIR / "persona").glob("*.json"))}
            from app.db import personas

            with self._db.engine.connect() as conn:
                rows = conn.execute(select(personas.c.id, personas.c.data).order_by(personas.c.id)).all()
            return {r.id: PersonaCard.model_validate(r.data) for r in rows}

        return dict(self._cached("personas", build))

    def save_persona(self, persona_id: str, card) -> None:
        from app.blocker.store import now_iso
        from app.db import personas

        self._need_db()
        data = card.model_dump(mode="json")
        with self._db.engine.begin() as conn:
            conn.execute(delete(personas).where(personas.c.id == persona_id))
            conn.execute(insert(personas).values(id=persona_id, data=data, updated_at=now_iso()))
        self.invalidate()

    # ── prompt ───────────────────────────────────────────────────────────────
    def prompt(self, name: str) -> Prompt:
        def build():
            if self._db is None:
                return parse_prompt(name, (SEED_DIR / "prompts" / f"{name}.md").read_text(encoding="utf-8"))
            from app.db import prompts

            with self._db.engine.connect() as conn:
                row = conn.execute(select(prompts).where(prompts.c.name == name, prompts.c.active.is_(True))).first()
            if row is None:
                raise KeyError(f"Prompt {name} tidak ada di database")
            return Prompt(name, row.version, row.body)

        return self._cached(f"prompt:{name}", build)

    def list_prompts(self) -> list[dict]:
        self._need_db()
        from app.db import prompts

        with self._db.engine.connect() as conn:
            rows = conn.execute(select(prompts).where(~prompts.c.name.like(SNIPPET_PREFIX + "%")).order_by(prompts.c.name, prompts.c.created_at)).all()
        return [{"name": r.name, "version": r.version, "active": bool(r.active), "created_at": r.created_at, "created_by": r.created_by} for r in rows]

    def add_prompt_version(self, name: str, version: str, body: str, by: str, activate: bool = True) -> None:
        """Versi baru sebuah prompt (riwayat lama tetap). Versi yang sudah ada tidak boleh ditimpa."""
        from app.blocker.store import now_iso
        from app.db import prompts

        self._need_db()
        with self._db.engine.begin() as conn:
            if conn.execute(select(prompts.c.name).where(prompts.c.name == name, prompts.c.version == version)).first():
                raise ValueError(f"Versi {version} untuk prompt {name} sudah ada; pakai nama versi baru")
            if activate:
                conn.execute(update(prompts).where(prompts.c.name == name).values(active=False))
            conn.execute(insert(prompts).values(name=name, version=version, body=body, active=activate, created_at=now_iso(), created_by=by[:64]))
        self.invalidate()

    def activate_prompt(self, name: str, version: str) -> None:
        from app.db import prompts

        self._need_db()
        with self._db.engine.begin() as conn:
            if not conn.execute(select(prompts.c.name).where(prompts.c.name == name, prompts.c.version == version)).first():
                raise KeyError(f"{name} {version} tidak ada")
            conn.execute(update(prompts).where(prompts.c.name == name).values(active=False))
            conn.execute(update(prompts).where(prompts.c.name == name, prompts.c.version == version).values(active=True))
        self.invalidate()

    # ── potongan teks prompt ─────────────────────────────────────────────────
    def snippets(self) -> dict[str, str]:
        def build():
            if self._db is None:
                raw = json.loads((SEED_DIR / "snippets.json").read_text(encoding="utf-8"))
                return {k: v for k, v in raw.items() if k.startswith(SNIPPET_PREFIX)}
            from app.db import prompts

            with self._db.engine.connect() as conn:
                rows = conn.execute(select(prompts.c.name, prompts.c.body).where(prompts.c.name.like(SNIPPET_PREFIX + "%"), prompts.c.active.is_(True))).all()
            return {r.name: r.body for r in rows}

        return self._cached("snippets", build)

    def snippet(self, key: str) -> str:
        try:
            return self.snippets()[SNIPPET_PREFIX + key]
        except KeyError:
            raise KeyError(f"Potongan teks {key} tidak ada") from None

    def text(self, key: str, **values: object) -> str:
        """Potongan teks `key` dengan {placeholder} diisi (kurung kurawal lain dibiarkan)."""
        out = self.snippet(key)
        for name, value in values.items():
            out = out.replace("{" + name + "}", str(value))
        return out

    def snippets_with_prefix(self, prefix: str) -> dict[str, str]:
        full = SNIPPET_PREFIX + prefix
        return {k[len(full):]: v for k, v in self.snippets().items() if k.startswith(full)}

    # ── Supervisor ───────────────────────────────────────────────────────────
    def banned_words(self) -> tuple[str, ...]:
        def build():
            if self._db is None:
                raw = json.loads((SEED_DIR / "supervisor" / "banned_words.json").read_text(encoding="utf-8"))
                return tuple(w.strip().lower() for k, ws in raw.items() if not k.startswith("_") for w in ws)
            from app.db import supervisor_banned_words

            with self._db.engine.connect() as conn:
                return tuple(conn.execute(select(supervisor_banned_words.c.word).order_by(supervisor_banned_words.c.word)).scalars())

        return self._cached("banned", build)

    def fallback_bank(self) -> dict[str, dict[str, list[str]]]:
        def build():
            if self._db is None:
                return json.loads((SEED_DIR / "supervisor" / "fallback.json").read_text(encoding="utf-8"))
            from app.db import supervisor_fallbacks

            bank: dict[str, dict[str, list[str]]] = {}
            with self._db.engine.connect() as conn:
                for r in conn.execute(select(supervisor_fallbacks).order_by(supervisor_fallbacks.c.id)):
                    bank.setdefault(r.persona, {}).setdefault(r.kind, []).append(r.text)
            return bank

        return self._cached("fallbacks", build)

    # ── pengelolaan oleh admin ───────────────────────────────────────────────
    def placeholders(self, text: str) -> set[str]:
        return set(re.findall(r"\{(\w+)\}", text))

    def prompt_body(self, name: str, version: str) -> str:
        from app.db import prompts

        self._need_db()
        with self._db.engine.connect() as conn:
            body = conn.execute(select(prompts.c.body).where(prompts.c.name == name, prompts.c.version == version)).scalar_one_or_none()
        if body is None:
            raise KeyError(f"{name} {version} tidak ada")
        return body

    def check_prompt_placeholders(self, name: str, body: str) -> None:
        """Isi baru harus memuat tepat placeholder yang diisi kode (mis. {name}); kalau hilang, bagian itu tidak terisi
        saat siaran, kalau tambahan, tidak pernah terisi."""
        want = self.placeholders(self.prompt(name).text)
        got = self.placeholders(body)
        if want - got:
            raise ValueError("Placeholder hilang: " + ", ".join("{" + p + "}" for p in sorted(want - got)))
        if got - want:
            raise ValueError("Placeholder tidak dikenal kode: " + ", ".join("{" + p + "}" for p in sorted(got - want)))

    def all_snippets(self) -> list[dict]:
        from app.db import prompts

        self._need_db()
        with self._db.engine.connect() as conn:
            rows = conn.execute(select(prompts).where(prompts.c.name.like(SNIPPET_PREFIX + "%"), prompts.c.active.is_(True)).order_by(prompts.c.name)).all()
        return [{"key": r.name[len(SNIPPET_PREFIX):], "text": r.body, "placeholders": sorted(self.placeholders(r.body)), "updated_at": r.created_at, "updated_by": r.created_by} for r in rows]

    def set_snippet(self, key: str, text: str, by: str) -> None:
        """Ubah teks sebuah potongan (kunci harus sudah ada; yang diisi kode tidak boleh kehilangan placeholdernya)."""
        from app.blocker.store import now_iso
        from app.db import prompts

        self._need_db()
        name = SNIPPET_PREFIX + key
        with self._db.engine.begin() as conn:
            row = conn.execute(select(prompts).where(prompts.c.name == name, prompts.c.active.is_(True))).first()
            if row is None:
                raise KeyError(key)
            if not text.strip():
                raise ValueError("Teks tidak boleh kosong")
            if self.placeholders(row.body) - self.placeholders(text):
                raise ValueError("Placeholder hilang: " + ", ".join("{" + p + "}" for p in sorted(self.placeholders(row.body) - self.placeholders(text))))
            conn.execute(update(prompts).where(prompts.c.name == name, prompts.c.version == row.version).values(body=text, created_at=now_iso(), created_by=by[:64]))
        self.invalidate()

    def list_banned(self) -> list[dict]:
        from app.db import supervisor_banned_words as t

        self._need_db()
        with self._db.engine.connect() as conn:
            return [{"word": r.word, "category": r.category} for r in conn.execute(select(t).order_by(t.c.category, t.c.word))]

    def add_banned(self, word: str, category: str) -> None:
        from app.db import supervisor_banned_words as t

        self._need_db()
        word, category = word.strip().lower(), category.strip().lower()
        if not word or not category:
            raise ValueError("Kata dan kategori wajib diisi")
        with self._db.engine.begin() as conn:
            if conn.execute(select(t.c.word).where(t.c.word == word)).first():
                raise ValueError(f"'{word}' sudah ada di daftar")
            conn.execute(insert(t).values(word=word, category=category[:40]))
        self.invalidate()

    def remove_banned(self, word: str) -> None:
        from app.db import supervisor_banned_words as t

        self._need_db()
        with self._db.engine.begin() as conn:
            if conn.execute(delete(t).where(t.c.word == word.strip().lower())).rowcount == 0:
                raise KeyError(word)
        self.invalidate()

    FALLBACK_KINDS = ("opening", "topic", "closing")

    def list_fallbacks(self) -> list[dict]:
        from app.db import supervisor_fallbacks as t

        self._need_db()
        with self._db.engine.connect() as conn:
            return [{"id": r.id, "persona": r.persona, "kind": r.kind, "text": r.text} for r in conn.execute(select(t).order_by(t.c.persona, t.c.kind, t.c.id))]

    def add_fallback(self, persona: str, kind: str, text: str) -> None:
        from app.db import supervisor_fallbacks as t

        self._need_db()
        if persona not in self.personas():
            raise ValueError(f"Persona {persona} tidak dikenal")
        if kind not in self.FALLBACK_KINDS:
            raise ValueError("Jenis harus opening, topic, atau closing")
        if not text.strip():
            raise ValueError("Kalimat tidak boleh kosong")
        with self._db.engine.begin() as conn:
            conn.execute(insert(t).values(persona=persona, kind=kind, text=text.strip()[:500]))
        self.invalidate()

    def remove_fallback(self, fallback_id: int) -> None:
        from app.db import supervisor_fallbacks as t

        self._need_db()
        with self._db.engine.begin() as conn:
            if conn.execute(delete(t).where(t.c.id == fallback_id)).rowcount == 0:
                raise KeyError(fallback_id)
        self.invalidate()

    def _need_db(self) -> None:
        if self._db is None:
            raise RuntimeError("Mengubah konten butuh database")


content = ContentStore()


def load_prompt(name: str) -> Prompt:
    return content.prompt(name)
