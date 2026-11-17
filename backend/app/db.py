"""Database (SQLAlchemy Core): Postgres di hosting, SQLite untuk tes dan pengembangan.

Yang disimpan di database: pengguna, sesi login, materi (blocker), dan catatan pembuatan materi.
Log siaran (`logs/*.jsonl`, `sessions/<id>/turns.jsonl`) dan cache audio tetap file di volume data;
itu artefak tambah-saja untuk riset dan bisa diekspor apa adanya.

Skema dibuat otomatis saat aplikasi mulai (`create_all`, idempotent). Perubahan skema berikutnya perlu
migrasi (Alembic) sebelum ada data yang tidak boleh hilang.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

metadata = MetaData()
_JSON = JSON().with_variant(JSONB(), "postgresql")

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("display_name", String(100), nullable=False, default=""),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(16), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", String(32), nullable=False),
    Column("last_login_at", String(32)),
)

# Token sesi tidak disimpan; hanya hash SHA-256-nya (kebocoran basis data tidak membocorkan sesi aktif).
auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False, index=True),
    Column("ip", String(64)),
    Column("user_agent", String(200)),
)

blockers = Table(
    "blockers",
    metadata,
    Column("id", String(80), primary_key=True),
    Column("tema", String(200), nullable=False),
    Column("versi", Integer, nullable=False),
    Column("locked", Boolean, nullable=False, default=False),
    Column("created_at", String(32), nullable=False, index=True),
    Column("generation_id", String(80), index=True),
    Column("parent_id", String(80)),
    Column("data", _JSON, nullable=False),
)

generation_log = Table(
    "generation_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(32), nullable=False),
    Column("data", _JSON, nullable=False),
)


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite"):
            if ":memory:" not in url:
                Path(url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
            self.engine: Engine = create_engine(url, future=True)
        else:
            self.engine = create_engine(url, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5)

    def create_all(self, attempts: int = 10, wait_s: float = 2.0) -> None:
        """Buat tabel. Postgres yang baru menyala bisa belum menerima sambungan: coba ulang beberapa kali."""
        for i in range(1, attempts + 1):
            try:
                metadata.create_all(self.engine)
                return
            except Exception as e:  # noqa: BLE001 - galat sambungan beragam antar driver
                if i == attempts:
                    raise
                logger.warning("Database belum siap (%s); coba lagi %d/%d", type(e).__name__, i, attempts)
                time.sleep(wait_s)

    def dispose(self) -> None:
        self.engine.dispose()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name
