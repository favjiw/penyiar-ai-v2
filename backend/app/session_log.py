"""Log siaran (FR-12) di database: tabel `session_events`, satu baris per kejadian.

Setiap kejadian punya `type` (session_start, turn, showrunner, supervisor, topic_change, operator_action, stt, error,
quota, session_end, ...), `ts`, dan `session_id`. Blocker yang dipakai disalin ke `session_start`, sehingga sesi
bisa direkonstruksi utuh dari log saja. Untuk analisis di luar aplikasi: `python -m app.cli export-session <id>`.

Nama modul bukan `logging` (seperti di PRD §11) supaya tidak tertukar dengan pustaka standar.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from pydantic import BaseModel
from sqlalchemy import func, insert, select

from app.blocker.store import now_iso
from app.db import Database, session_blockers, session_events

logger = logging.getLogger(__name__)

EVENT_TYPES = {
    "session_start",
    "turn",
    "showrunner",
    "supervisor",
    "topic_change",
    "point_start",
    "point_end",
    "point_trim",
    "operator_action",
    "stt",
    "error",
    "quota",
    "session_end",
    "nudge",  # mode A: kode halus pindah topik (PRD v2.7 FR-4)
    "topic_time",  # mode A: lama topik vs perkiraan menit setiap topik ditinggalkan
    "voice_switch",  # mode A: pindah topik dari ucapan penyiar (aturan yang cocok, teks) dan pembatalannya
}


class SessionLogger:
    def __init__(self, session_id: str, db: Database):
        self.session_id = session_id
        self.db = db
        self.failures = 0  # penulisan yang gagal; siaran tidak boleh berhenti hanya karena log

    def event(self, type_: str, payload: BaseModel | dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"Tipe event log tidak dikenal: {type_}")
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload or {})
        line = {"type": type_, "ts": now_iso(), "session_id": self.session_id, **data, **fields}
        row = _jsonable(line)
        try:
            with self.db.engine.begin() as conn:
                conn.execute(insert(session_events).values(session_id=self.session_id, ts=row["ts"], type=type_, data=row))
        except Exception:  # noqa: BLE001 - basis data bermasalah tidak boleh menjatuhkan siaran
            self.failures += 1
            logger.exception("Gagal menulis log siaran %s (%s)", self.session_id, type_)
        return line

    def events(self) -> list[dict[str, Any]]:
        return read_events(self.db, self.session_id)


def _jsonable(line: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(line, ensure_ascii=False, default=str))


def read_events(db: Database, session_id: str) -> list[dict[str, Any]]:
    with db.engine.connect() as conn:
        rows = conn.execute(select(session_events.c.data).where(session_events.c.session_id == session_id).order_by(session_events.c.id)).scalars()
        return list(rows)


def list_sessions(db: Database, prefix: str = "show_", limit: int = 200) -> list[dict[str, Any]]:
    """Sesi yang punya log, terbaru dulu: id, jumlah kejadian, waktu mulai."""
    with db.engine.connect() as conn:
        rows = conn.execute(
            select(session_events.c.session_id, func.count().label("events"), func.min(session_events.c.ts).label("first_ts"))
            .where(session_events.c.session_id.like(prefix + "%"))
            .group_by(session_events.c.session_id)
            .order_by(session_events.c.session_id.desc())
            .limit(limit)
        ).all()
    return [{"session_id": r.session_id, "events": r.events, "started": r.first_ts} for r in rows]


def save_session_blocker(db: Database, session_id: str, blocker: BaseModel) -> None:
    """Salin blocker terkunci yang dipakai sesi (bahan riset: apa yang dibaca AI dan penyiar)."""
    from sqlalchemy import delete

    with db.engine.begin() as conn:
        conn.execute(delete(session_blockers).where(session_blockers.c.session_id == session_id))
        conn.execute(insert(session_blockers).values(session_id=session_id, data=blocker.model_dump(mode="json")))


def read_log(path) -> Iterator[dict[str, Any]]:
    """Baca berkas JSONL hasil `python -m app.cli export-session` (untuk skrip riset di luar aplikasi)."""
    import json
    from pathlib import Path

    with open(Path(path), encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                yield json.loads(raw)
