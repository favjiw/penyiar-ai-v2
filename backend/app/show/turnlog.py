"""Log giliran untuk riset (tabel `session_turns`), satu baris per giliran (AI maupun manusia).

Untuk analisis di luar aplikasi: `python -m app.cli export-session <id>` menulis turns.jsonl.

Medan wajib: session_id, mode, turn_idx, speaker, is_human, topic_idx, text, t_start, t_end,
latency_asr_ms, latency_llm_ms, latency_tts_ms, model, tts_chars, filler_used.
Medan tambahan membantu analisis (nama, segmen, teks mentah, verdict Supervisor, provider TTS).

Waktu (`t_start`, `t_end`) adalah detik epoch dinding. Untuk giliran AI: audio mulai dan selesai
diputar. Untuk giliran manusia: tombol bicara ditekan dan dilepas (dihitung mundur dari saat
transkrip final tiba). `topic_idx` berbasis 0, `null` di Opening dan Closing.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlalchemy import insert, select

from app.db import Database, session_turns

REQUIRED = (
    "session_id", "mode", "turn_idx", "speaker", "is_human", "topic_idx", "text", "t_start", "t_end",
    "latency_asr_ms", "latency_llm_ms", "latency_tts_ms", "model", "tts_chars", "filler_used", "condition",
)


def topic_index(topic_id: Optional[str]) -> Optional[int]:
    """`t2` → 1; None di Opening dan Closing."""
    m = re.fullmatch(r"t(\d+)", topic_id or "")
    return int(m.group(1)) - 1 if m else None


class TurnLog:
    def __init__(self, session_id: str, db: Database):
        self.session_id = session_id
        self.db = db
        self.count = 0

    def write(self, **fields: Any) -> dict[str, Any]:
        missing = [k for k in REQUIRED if k not in fields]
        if missing:
            raise ValueError(f"Baris log giliran kekurangan medan: {', '.join(missing)}")
        row = json.loads(json.dumps(fields, ensure_ascii=False, default=str))
        with self.db.engine.begin() as conn:
            conn.execute(insert(session_turns).values(session_id=self.session_id, turn_idx=int(fields["turn_idx"]), data=row))
        self.count += 1
        return fields

    def all(self) -> list[dict[str, Any]]:
        return read_turns(self.db, self.session_id)


def read_turns(db: Database, session_id: str) -> list[dict[str, Any]]:
    with db.engine.connect() as conn:
        return list(conn.execute(select(session_turns.c.data).where(session_turns.c.session_id == session_id).order_by(session_turns.c.id)).scalars())
