"""Log giliran untuk riset: `sessions/<session_id>/turns.jsonl`, satu baris per giliran (AI maupun manusia).

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
from pathlib import Path
from typing import Any, Optional

REQUIRED = (
    "session_id", "mode", "turn_idx", "speaker", "is_human", "topic_idx", "text", "t_start", "t_end",
    "latency_asr_ms", "latency_llm_ms", "latency_tts_ms", "model", "tts_chars", "filler_used",
)


def topic_index(topic_id: Optional[str]) -> Optional[int]:
    """`t2` → 1; None di Opening dan Closing."""
    m = re.fullmatch(r"t(\d+)", topic_id or "")
    return int(m.group(1)) - 1 if m else None


class TurnLog:
    def __init__(self, session_dir: Path):
        self.path = Path(session_dir) / "turns.jsonl"
        self.rows = 0

    def write(self, **fields: Any) -> dict[str, Any]:
        missing = [k for k in REQUIRED if k not in fields]
        if missing:
            raise ValueError(f"Baris turns.jsonl kekurangan medan: {', '.join(missing)}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False, default=str) + "\n")
        self.rows += 1
        return fields
