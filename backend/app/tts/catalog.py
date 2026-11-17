"""Daftar suara terkurasi yang bisa dipilih operator sebelum live (FR-6).

Sumber: tabel `voices` di database (dikelola admin di halaman admin); diisi satu kali dari
`app/data/voices.json` saat pertama jalan. Tanpa database (pengembangan, tes) daftar dibaca dari file itu.
Daftar disimpan di memori dan dimuat ulang setiap admin mengubahnya.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, update

VOICES_FILE = Path(__file__).resolve().parents[1] / "data" / "voices.json"
SEEDED_FLAG = "meta.voices_seeded"


class VoiceOption(BaseModel):
    id: str  # voice id provider
    provider: Literal["elevenlabs", "edge"]
    name: str
    gender: Literal["male", "female"]
    notes: str = ""


class VoiceError(ValueError):
    pass


def _from_file() -> tuple[VoiceOption, ...]:
    raw = json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    return tuple(VoiceOption.model_validate(v) for v in raw["voices"])


class VoiceCatalog:
    def __init__(self) -> None:
        self._db = None
        self._items: tuple[VoiceOption, ...] | None = None

    def configure(self, db) -> None:
        """Pakai database (None = file). Mengisi tabel dari voices.json sekali saja."""
        from app.blocker.store import now_iso
        from app.db import app_settings, voices

        self._db, self._items = db, None
        if db is None:
            return
        with db.engine.begin() as conn:
            seeded = conn.execute(select(app_settings.c.key).where(app_settings.c.key == SEEDED_FLAG)).first()
            if seeded is None:
                for i, v in enumerate(_from_file()):
                    conn.execute(insert(voices).values(**v.model_dump(), position=i))
                conn.execute(insert(app_settings).values(key=SEEDED_FLAG, value="1", secret=False, updated_at=now_iso(), updated_by="sistem"))

    def _load(self) -> tuple[VoiceOption, ...]:
        if self._items is None:
            if self._db is None:
                self._items = _from_file()
            else:
                from app.db import voices

                with self._db.engine.connect() as conn:
                    rows = conn.execute(select(voices).order_by(voices.c.position, voices.c.name)).all()
                self._items = tuple(VoiceOption(id=r.id, provider=r.provider, name=r.name, gender=r.gender, notes=r.notes or "") for r in rows)
        return self._items

    def all(self) -> list[VoiceOption]:
        return list(self._load())

    def find(self, voice_id: str) -> VoiceOption | None:
        return next((v for v in self._load() if v.id == voice_id), None)

    # pengelolaan (admin) -------------------------------------------------------
    def _need_db(self):
        if self._db is None:
            raise VoiceError("Mengelola suara butuh database (DATABASE_URL atau AUTH_REQUIRED)")
        return self._db

    def add(self, v: VoiceOption) -> VoiceOption:
        from app.db import voices

        db = self._need_db()
        v = v.model_copy(update={"id": v.id.strip(), "name": v.name.strip(), "notes": v.notes.strip()})
        if not v.id or not v.name:
            raise VoiceError("ID suara dan nama wajib diisi")
        if self.find(v.id):
            raise VoiceError(f"ID suara {v.id} sudah ada di daftar")
        with db.engine.begin() as conn:
            pos = conn.execute(select(func.coalesce(func.max(voices.c.position), -1) + 1)).scalar_one()
            conn.execute(insert(voices).values(**v.model_dump(), position=pos))
        self._items = None
        return v

    def update(self, voice_id: str, *, name: str | None = None, gender: str | None = None, notes: str | None = None) -> VoiceOption:
        from app.db import voices

        db = self._need_db()
        if self.find(voice_id) is None:
            raise KeyError(voice_id)
        values = {k: x for k, x in (("name", name), ("gender", gender), ("notes", notes)) if x is not None}
        if "name" in values and not values["name"].strip():
            raise VoiceError("Nama suara wajib diisi")
        if "gender" in values and values["gender"] not in ("male", "female"):
            raise VoiceError("Gender harus male atau female")
        if values:
            with db.engine.begin() as conn:
                conn.execute(update(voices).where(voices.c.id == voice_id).values(**values))
            self._items = None
        return self.find(voice_id)  # type: ignore[return-value]

    def remove(self, voice_id: str) -> None:
        from app.db import voices

        db = self._need_db()
        if self.find(voice_id) is None:
            raise KeyError(voice_id)
        with db.engine.begin() as conn:
            conn.execute(delete(voices).where(voices.c.id == voice_id))
        self._items = None


catalog = VoiceCatalog()


def load_voice_catalog() -> list[VoiceOption]:
    return catalog.all()


def find_voice(voice_id: str) -> VoiceOption | None:
    return catalog.find(voice_id)
