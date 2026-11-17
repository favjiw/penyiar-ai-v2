"""Daftar wajah Simli yang bisa dipilih untuk tiap penyiar (halaman admin).

Tabel `simli_faces`. Wajah yang sudah dipakai lewat .env (SIMLI_FACE_ID*) dimasukkan saat pertama jalan supaya
tidak hilang dari pilihan. Pemilihan wajah per penyiar adalah setelan `SIMLI_FACE_ID_RAKA` / `SIMLI_FACE_ID_SALSA`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select

from app.blocker.store import now_iso
from app.db import Database, app_settings, simli_faces

SEEDED_FLAG = "meta.faces_seeded"
FACE_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,80}$")


class FaceError(ValueError):
    pass


class Face(BaseModel):
    id: str
    name: str
    notes: str = ""


class FaceCatalog:
    def __init__(self, db: Database):
        self._db = db

    def seed(self, settings) -> None:
        """Satu kali: masukkan wajah dari .env (bawaan, Raka, Salsa) bila belum ada."""
        with self._db.engine.begin() as conn:
            if conn.execute(select(app_settings.c.key).where(app_settings.c.key == SEEDED_FLAG)).first():
                return
            seen: set[str] = set()
            for label, fid in (("Bawaan", settings.SIMLI_FACE_ID), ("Raka", settings.SIMLI_FACE_ID_RAKA), ("Salsa", settings.SIMLI_FACE_ID_SALSA)):
                fid = (fid or "").strip().strip("'\"")
                if fid and fid not in seen and FACE_ID_RE.match(fid):
                    seen.add(fid)
                    conn.execute(insert(simli_faces).values(id=fid, name=f"{label} (dari .env)", notes="", position=len(seen)))
            conn.execute(insert(app_settings).values(key=SEEDED_FLAG, value="1", secret=False, updated_at=now_iso(), updated_by="sistem"))

    def all(self) -> list[Face]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(select(simli_faces).order_by(simli_faces.c.position, simli_faces.c.name)).all()
        return [Face(id=r.id, name=r.name, notes=r.notes or "") for r in rows]

    def get(self, face_id: str) -> Face | None:
        return next((f for f in self.all() if f.id == face_id), None)

    def add(self, face: Face) -> Face:
        fid, name = face.id.strip(), face.name.strip()
        if not FACE_ID_RE.match(fid):
            raise FaceError("ID wajah Simli tidak valid (huruf, angka, strip; 8-80 karakter)")
        if not name:
            raise FaceError("Nama wajah wajib diisi")
        if self.get(fid):
            raise FaceError(f"Wajah {fid} sudah ada di daftar")
        with self._db.engine.begin() as conn:
            pos = conn.execute(select(func.coalesce(func.max(simli_faces.c.position), -1) + 1)).scalar_one()
            conn.execute(insert(simli_faces).values(id=fid, name=name[:100], notes=face.notes.strip()[:500], position=pos))
        return Face(id=fid, name=name, notes=face.notes.strip())

    def remove(self, face_id: str) -> None:
        if self.get(face_id) is None:
            raise KeyError(face_id)
        with self._db.engine.begin() as conn:
            conn.execute(delete(simli_faces).where(simli_faces.c.id == face_id))
