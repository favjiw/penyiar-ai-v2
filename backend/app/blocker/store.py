"""Penyimpanan blocker sebagai file JSON (DATA_DIR/blockers/{id}.json).

Blocker yang sudah dikunci tidak bisa diubah; perubahan dibuat sebagai versi
baru (versi + 1, parent_id = blocker asal), sesuai FR-1.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.schemas import Blocker

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
    """
    if not 1 <= len(blocker.topics) <= 3:
        raise BlockerInvalid("Blocker harus berisi 1-3 topik")
    for i, topic in enumerate(blocker.topics, 1):
        topic.id = f"t{i}"
        topic.poin = [p for p in topic.poin if p.text.strip()]
        if not topic.poin:
            raise BlockerInvalid(f"Topik {i} tidak punya poin")
        if not topic.judul.strip():
            raise BlockerInvalid(f"Topik {i} tanpa judul")
        for j, point in enumerate(topic.poin, 1):
            point.id = f"t{i}p{j}"
    blocker.opening.poin = [p for p in blocker.opening.poin if p.strip()]
    return blocker


class BlockerStore:
    def __init__(self, data_dir: str | Path):
        self._dir = Path(data_dir) / "blockers"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, blocker_id: str) -> Path:
        if not re.fullmatch(r"blk_[a-z0-9_-]+", blocker_id):
            raise BlockerNotFound(blocker_id)
        return self._dir / f"{blocker_id}.json"

    def save(self, blocker: Blocker) -> Blocker:
        self._path(blocker.id).write_text(blocker.model_dump_json(indent=2), encoding="utf-8")
        return blocker

    def get(self, blocker_id: str) -> Blocker:
        path = self._path(blocker_id)
        if not path.exists():
            raise BlockerNotFound(blocker_id)
        return Blocker.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, generation_id: str | None = None, locked: bool | None = None) -> list[Blocker]:
        items = [Blocker.model_validate_json(p.read_text(encoding="utf-8")) for p in self._dir.glob("blk_*.json")]
        if generation_id is not None:
            items = [b for b in items if b.generation_id == generation_id]
        if locked is not None:
            items = [b for b in items if b.locked == locked]
        return sorted(items, key=lambda b: b.created_at, reverse=True)

    def update(self, blocker_id: str, edited: Blocker) -> Blocker:
        """Simpan editan isi; metadata (id, versi, status kunci, asal) tetap dari server."""
        current = self.get(blocker_id)
        if current.locked:
            raise BlockerLocked(f"{blocker_id} sudah dikunci; buat versi baru untuk mengubah")
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
        current.locked = True
        return self.save(current)

    def new_version(self, blocker_id: str) -> Blocker:
        source = self.get(blocker_id)
        if not source.locked:
            raise BlockerInvalid("Versi baru hanya dibuat dari blocker yang sudah dikunci; draf bisa langsung diedit")
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
