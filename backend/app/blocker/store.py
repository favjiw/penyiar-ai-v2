"""Penyimpanan blocker (materi) di database, aturan kunci, normalisasi, dan versi (FR-1)."""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

from app.schemas import MAX_TOPICS, Blocker

WIB = timezone(timedelta(hours=7))


class BlockerNotFound(KeyError):
    pass


class BlockerLocked(RuntimeError):
    pass


class BlockerInvalid(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(WIB).isoformat(timespec="seconds")


def slugify(text: str, max_len: int = 24) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].strip("-") or "tema"


def new_blocker_id(tema: str) -> str:
    return f"blk_{datetime.now(WIB):%Y%m%d}_{slugify(tema)}_{secrets.token_hex(2)}"


def normalize(blocker: Blocker) -> Blocker:
    """Susun ulang id topik dan poin (t1, t1p1, ...) setelah poin ditambah, dihapus, atau digeser.

    Id ini dipakai Showrunner untuk menandai poin yang tercakup, jadi harus stabil
    setelah blocker dikunci; karena itu hanya dinormalisasi selama masih draf.
    Draf boleh setengah jadi (topik baru tanpa judul/bahan) supaya editor bisa simpan
    otomatis; kelengkapan baru ditegakkan `validate_for_lock` saat siaran dimulai.
    """
    if not 1 <= len(blocker.topics) <= MAX_TOPICS:
        raise BlockerInvalid(f"Materi harus berisi 1-{MAX_TOPICS} topik")
    for i, topic in enumerate(blocker.topics, 1):
        topic.id = f"t{i}"
        topic.poin = [p for p in topic.poin if p.text.strip()]
        for j, point in enumerate(topic.poin, 1):
            point.id = f"t{i}p{j}"
    blocker.opening.poin = [p for p in blocker.opening.poin if p.strip()]
    return blocker


MIN_POINTS, MAX_POINTS = 3, 5


def validate_for_lock(blocker: Blocker) -> None:
    """Aturan FR-1 yang wajib terpenuhi sebelum materi dikunci (draf boleh belum rapi).
    Pesan memakai istilah UI (DESIGN.md §5) karena tampil ke operator."""
    problems = []
    if not blocker.opening.hook.strip():
        problems.append("Opening: kalimat pembuka kosong")
    if not blocker.closing.rangkuman.strip() or not blocker.closing.ajakan.strip():
        problems.append("Closing: rangkuman atau ajakan kosong")
    for i, t in enumerate(blocker.topics, 1):
        if not t.judul.strip():
            problems.append(f"Topik {i}: judul kosong")
        if not MIN_POINTS <= len(t.poin) <= MAX_POINTS:
            problems.append(f"Topik {i} ({t.judul[:30]}): {len(t.poin)} bahan obrolan, harus {MIN_POINTS}-{MAX_POINTS}")
        for name, label in (("sudut_pandang", "sudut pandang"), ("pertanyaan_penonton", "pertanyaan ke penonton"), ("transisi", "kalimat pindah topik")):
            if not getattr(t, name).strip():
                problems.append(f"Topik {i}: {label} kosong")
    if problems:
        raise BlockerInvalid("Belum bisa dikunci: " + "; ".join(problems))


class BlockerStore:
    """Materi di database (tabel `blockers`). Blocker yang sudah dikunci tidak bisa diubah; perubahan dibuat sebagai
    versi baru (versi + 1, parent_id = blocker asal), sesuai FR-1.

    Kolom indeks (tema, versi, locked, ...) disalin dari isi supaya daftar bisa disaring tanpa membuka JSON;
    isi lengkap ada di kolom `data` dan itulah yang dibaca kembali.
    """

    def __init__(self, db):
        self._db = db

    @staticmethod
    def _check_id(blocker_id: str) -> None:
        if not re.fullmatch(r"blk_[a-z0-9_-]+", blocker_id):
            raise BlockerNotFound(blocker_id)

    def save(self, blocker: Blocker) -> Blocker:
        from sqlalchemy import delete, insert

        from app.db import blockers

        self._check_id(blocker.id)
        row = {
            "id": blocker.id,
            "tema": blocker.tema[:200],
            "versi": blocker.versi,
            "locked": blocker.locked,
            "created_at": blocker.created_at,
            "generation_id": blocker.generation_id,
            "parent_id": blocker.parent_id,
            "data": blocker.model_dump(mode="json"),
        }
        with self._db.engine.begin() as conn:  # hapus lalu sisip dalam satu transaksi: sama di SQLite dan Postgres
            conn.execute(delete(blockers).where(blockers.c.id == blocker.id))
            conn.execute(insert(blockers).values(**row))
        return blocker

    def get(self, blocker_id: str) -> Blocker:
        from sqlalchemy import select

        from app.db import blockers

        self._check_id(blocker_id)
        with self._db.engine.connect() as conn:
            data = conn.execute(select(blockers.c.data).where(blockers.c.id == blocker_id)).scalar_one_or_none()
        if data is None:
            raise BlockerNotFound(blocker_id)
        return Blocker.model_validate(data)

    def list(self, generation_id: str | None = None, locked: bool | None = None) -> list[Blocker]:
        from sqlalchemy import select

        from app.db import blockers

        stmt = select(blockers.c.data).order_by(blockers.c.created_at.desc())
        if generation_id is not None:
            stmt = stmt.where(blockers.c.generation_id == generation_id)
        if locked is not None:
            stmt = stmt.where(blockers.c.locked == locked)
        with self._db.engine.connect() as conn:
            return [Blocker.model_validate(d) for d in conn.execute(stmt).scalars()]

    def create_draft(self, blocker: Blocker) -> Blocker:
        """Simpan varian hasil generate sebagai draf (pilihan operator). Id yang sudah ada dan masih draf ditimpa
        (simpan ulang); yang sudah terkunci ditolak. Isi dinormalkan; status kunci dan asal tidak dipercaya dari klien."""
        try:
            current = self.get(blocker.id)
        except BlockerNotFound:
            current = None
        if current is not None and current.locked:
            raise BlockerLocked("Materi ini sudah dikunci (pernah dipakai live); buat versi baru untuk mengubah")
        draft = blocker.model_copy(deep=True, update={"locked": False})
        if current is not None:
            draft.created_at, draft.parent_id, draft.versi = current.created_at, current.parent_id, current.versi
        return self.save(normalize(draft))

    def update(self, blocker_id: str, edited: Blocker) -> Blocker:
        """Simpan editan isi; metadata (id, versi, status kunci, asal) tetap dari server."""
        current = self.get(blocker_id)
        if current.locked:
            raise BlockerLocked("Materi ini sudah dikunci (pernah dipakai live); buat versi baru untuk mengubah")
        merged = edited.model_copy(
            update={
                "id": current.id,
                "tema": current.tema,
                "versi": current.versi,
                "locked": False,
                "created_at": current.created_at,
                "parent_id": current.parent_id,
                "generation_id": current.generation_id,
            }
        )
        return self.save(normalize(merged))

    def lock(self, blocker_id: str) -> Blocker:
        current = self.get(blocker_id)
        if current.locked:
            return current
        current = normalize(current)
        validate_for_lock(current)
        current.locked = True
        return self.save(current)

    def new_version(self, blocker_id: str) -> Blocker:
        source = self.get(blocker_id)
        if not source.locked:
            raise BlockerInvalid("Versi baru hanya dibuat dari materi yang sudah dikunci; draf bisa langsung diubah")
        copy = source.model_copy(
            deep=True,
            update={
                "id": new_blocker_id(source.tema),
                "versi": source.versi + 1,
                "locked": False,
                "created_at": now_iso(),
                "parent_id": source.id,
            },
        )
        return self.save(copy)
