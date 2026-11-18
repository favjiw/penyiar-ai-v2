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
from app.db import Database, session_blockers, session_events, session_turns

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


def _summary(sid: str, start: dict[str, Any], end: dict[str, Any] | None, n_events: int, n_ai: int, n_human: int) -> dict[str, Any]:
    cfg = start.get("config") or {}
    blk = start.get("blocker") or {}
    return {
        "session_id": sid,
        "mode": start.get("mode"),
        "started": start.get("ts"),
        "ended": (end or {}).get("ts"),
        "elapsed_s": (end or {}).get("elapsed_s"),
        "end_reason": (end or {}).get("reason"),
        "tema": blk.get("tema"),
        "variant_label": blk.get("variant_label"),
        "n_topics": len(blk.get("topics") or []),
        "participants": [p.get("name") for p in (start.get("participants") or [])],
        "n_events": n_events,
        "n_ai_turns": n_ai,
        "n_human_turns": n_human,
        "llm_mode": cfg.get("LLM_MODE"),
        "tts_mode": cfg.get("TTS_MODE"),
        "tts_provider": cfg.get("TTS_PROVIDER"),
        "supervisor_mode": start.get("supervisor_mode_effective") or cfg.get("SUPERVISOR_MODE"),
        "pilot_condition": start.get("pilot_condition"),
        "models": start.get("models"),
        "code": start.get("code"),
    }


def session_page(db: Database, limit: int = 50, offset: int = 0, mode: str | None = None, q: str | None = None) -> dict[str, Any]:
    """Daftar sesi (terbaru dulu) dengan ringkasan; `mode` A|B dan `q` (cari di id/tema/judul/peserta) menyaring.
    Sesi tanpa event session_start (log rusak/terpotong) tetap tampil dengan ringkasan kosong."""
    with db.engine.connect() as conn:
        counts = {r.session_id: r.n for r in conn.execute(select(session_events.c.session_id, func.count().label("n")).group_by(session_events.c.session_id))}
        starts = {r.session_id: r.data for r in conn.execute(select(session_events.c.session_id, session_events.c.data).where(session_events.c.type == "session_start"))}
    rows = []
    needle = (q or "").strip().lower()
    for sid in counts:
        st = starts.get(sid) or {}
        if mode and st.get("mode") != mode:
            continue
        if needle:
            blk = st.get("blocker") or {}
            hay = " ".join(str(x) for x in [sid, blk.get("tema"), blk.get("variant_label"), *(p.get("name") for p in (st.get("participants") or []))]).lower()
            if needle not in hay:
                continue
        rows.append((st.get("ts") or sid, sid))
    rows.sort(reverse=True)
    total = len(rows)
    page = [sid for _, sid in rows[offset : offset + limit]]
    items: list[dict[str, Any]] = []
    if page:
        with db.engine.connect() as conn:
            ends = {r.session_id: r.data for r in conn.execute(select(session_events.c.session_id, session_events.c.data).where(session_events.c.type == "session_end", session_events.c.session_id.in_(page)))}
            turn_rows: dict[str, tuple[int, int]] = {}
            for r in conn.execute(select(session_turns.c.session_id, session_turns.c.data).where(session_turns.c.session_id.in_(page))):
                ai, hu = turn_rows.get(r.session_id, (0, 0))
                turn_rows[r.session_id] = (ai, hu + 1) if (r.data or {}).get("is_human") else (ai + 1, hu)
            turn_events = {r.session_id: r.n for r in conn.execute(select(session_events.c.session_id, func.count().label("n")).where(session_events.c.type == "turn", session_events.c.session_id.in_(page)).group_by(session_events.c.session_id))}
        for sid in page:
            ai, hu = turn_rows.get(sid, (turn_events.get(sid, 0), 0))  # tanpa baris giliran riset: pakai event turn (hanya AI)
            items.append(_summary(sid, starts.get(sid) or {}, ends.get(sid), counts[sid], ai, hu))
    return {"total": total, "items": items}


def session_detail(db: Database, session_id: str) -> dict[str, Any] | None:
    """Ringkasan + konfigurasi + event + giliran + materi sebuah sesi; None bila tidak ada log."""
    from app.show.turnlog import read_turns

    events = read_events(db, session_id)
    if not events:
        return None
    start = next((e for e in events if e.get("type") == "session_start"), {})
    end = next((e for e in reversed(events) if e.get("type") == "session_end"), None)
    turns = read_turns(db, session_id)
    ai = sum(1 for t in turns if not t.get("is_human"))
    n_ai = ai if turns else sum(1 for e in events if e.get("type") == "turn")
    summary = _summary(session_id, start, end, len(events), n_ai, len(turns) - ai)
    with db.engine.connect() as conn:
        blocker = conn.execute(select(session_blockers.c.data).where(session_blockers.c.session_id == session_id)).scalar_one_or_none() or start.get("blocker")
    config = {k: v for k, v in start.items() if k not in ("blocker", "type", "session_id")}
    return {"summary": summary, "config": config, "blocker": blocker, "events": events, "turns": turns}


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
