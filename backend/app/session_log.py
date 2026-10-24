"""Log sesi JSONL bertipe (FR-12): satu file per sesi, `logs/{session_id}.jsonl`.

Setiap baris punya `type` (session_start, turn, showrunner, supervisor,
topic_change, operator_action, stt, error, quota, session_end), `ts`, dan
`session_id`. Blocker yang dipakai disalin ke `session_start`, sehingga sesi
bisa direkonstruksi utuh dari log saja.

Nama modul bukan `logging` (seperti di PRD §11) supaya tidak tertukar dengan
pustaka standar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from app.blocker.store import now_iso

EVENT_TYPES = {
    "session_start",
    "turn",
    "showrunner",
    "supervisor",
    "topic_change",
    "operator_action",
    "stt",
    "error",
    "quota",
    "session_end",
}


class SessionLogger:
    def __init__(self, session_id: str, log_dir: str | Path):
        self.session_id = session_id
        self.path = Path(log_dir) / f"{session_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, type_: str, payload: BaseModel | dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"Tipe event log tidak dikenal: {type_}")
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload or {})
        line = {"type": type_, "ts": now_iso(), "session_id": self.session_id, **data, **fields}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        return line


def read_log(path: str | Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                yield json.loads(raw)
