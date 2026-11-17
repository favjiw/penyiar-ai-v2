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
    Text,
    create_engine,
)
from sqlalchemy import event
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

# Setelan yang diatur admin (kunci API, model, suara, Simli). Nilai rahasia disimpan terenkripsi (lihat app/secrets.py).
# Baris `meta.*` menandai langkah satu kali (mis. katalog suara sudah diisi dari voices.json).
app_settings = Table(
    "app_settings",
    metadata,
    Column("key", String(80), primary_key=True),
    Column("value", String, nullable=False),
    Column("secret", Boolean, nullable=False, default=False),
    Column("updated_at", String(32), nullable=False),
    Column("updated_by", String(64)),
)

voices = Table(
    "voices",
    metadata,
    Column("id", String(200), primary_key=True),  # voice id provider
    Column("provider", String(16), nullable=False),
    Column("name", String(100), nullable=False),
    Column("gender", String(8), nullable=False),
    Column("notes", String(500), nullable=False, default=""),
    Column("position", Integer, nullable=False, default=0),
)

simli_faces = Table(
    "simli_faces",
    metadata,
    Column("id", String(80), primary_key=True),  # face id Simli
    Column("name", String(100), nullable=False),
    Column("notes", String(500), nullable=False, default=""),
    Column("position", Integer, nullable=False, default=0),
)


_ID = BigInteger().with_variant(Integer, "sqlite")  # SQLite hanya menaikkan otomatis kolom INTEGER PRIMARY KEY

# Log siaran (FR-12): satu baris per kejadian (session_start, turn, showrunner, ...). Urutan = id.
session_events = Table(
    "session_events",
    metadata,
    Column("id", _ID, primary_key=True, autoincrement=True),
    Column("session_id", String(80), nullable=False, index=True),
    Column("ts", String(32), nullable=False),
    Column("type", String(32), nullable=False),
    Column("data", _JSON, nullable=False),
)

# Log giliran untuk riset: satu baris per giliran (AI maupun manusia).
session_turns = Table(
    "session_turns",
    metadata,
    Column("id", _ID, primary_key=True, autoincrement=True),
    Column("session_id", String(80), nullable=False, index=True),
    Column("turn_idx", Integer, nullable=False),
    Column("data", _JSON, nullable=False),
)

# Materi terkunci yang dipakai sebuah sesi (bahan riset: apa yang dibaca AI dan penyiar).
session_blockers = Table(
    "session_blockers",
    metadata,
    Column("session_id", String(80), primary_key=True),
    Column("data", _JSON, nullable=False),
)

# Penghitung kuota harian per model (satu baris per model; hari Pasifik).
quota_counters = Table(
    "quota_counters",
    metadata,
    Column("model", String(120), primary_key=True),
    Column("day", String(10), nullable=False),
    Column("used", Integer, nullable=False, default=0),
    Column("exhausted", Boolean, nullable=False, default=False),
)

# Kartu persona (Raka, Salsa): isi sesuai skema PersonaCard.
personas = Table(
    "personas",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("data", _JSON, nullable=False),
    Column("updated_at", String(32), nullable=False),
)

# Kata terlarang aturan cepat Supervisor, per kategori.
supervisor_banned_words = Table(
    "supervisor_banned_words",
    metadata,
    Column("word", String(80), primary_key=True),
    Column("category", String(40), nullable=False),
)

# Kalimat aman pengganti (bank per persona dan segmen: opening | topic | closing).
supervisor_fallbacks = Table(
    "supervisor_fallbacks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("persona", String(40), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("text", String(500), nullable=False),
)

# Prompt berversi dan potongan teks prompt (nama `snippet.*`). Yang dipakai = baris `active` per nama.
prompts = Table(
    "prompts",
    metadata,
    Column("name", String(80), primary_key=True),
    Column("version", String(80), primary_key=True),
    Column("body", Text, nullable=False),
    Column("active", Boolean, nullable=False, default=False),
    Column("created_at", String(32), nullable=False),
    Column("created_by", String(64)),
)


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite"):
            if ":memory:" not in url:
                Path(url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
            self.engine: Engine = create_engine(url, future=True)
            # WAL: penulis log siaran tidak memblokir pembaca dan jauh lebih cepat daripada jurnal bawaan.
            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi_conn, _):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        else:
            self.engine = create_engine(
                url, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_timeout=5,
                connect_args={"connect_timeout": 5},  # database yang macet jangan menahan siaran lama (log ditulis dari loop siaran)
            )

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


_registry: dict[str, Database] = {}


def database_for(settings) -> Database:
    """Database bersama untuk satu URL (aplikasi, mesin siaran, skrip memakai koneksi yang sama). Tabel dibuat bila belum ada."""
    url = settings.database_url
    db = _registry.get(url)
    if db is None:
        db = _registry[url] = Database(url)
        db.create_all()
    return db
