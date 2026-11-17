from app.db import Database


def make_db(tmp_path, name="t.db") -> Database:
    """SQLite sementara dengan semua tabel (untuk tes yang tidak lewat aplikasi)."""
    db = Database(f"sqlite:///{(tmp_path / name).as_posix()}")
    db.create_all()
    return db
