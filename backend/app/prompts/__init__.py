"""Prompt disimpan sebagai file .md berversi (PRD §10); versinya dicatat di log."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent
_VERSION_RE = re.compile(r"^<!--\s*version:\s*(\S+)\s*-->\s*\n")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    def render(self, **values: object) -> str:
        """Isi placeholder {nama}; kurung kurawal lain (mis. contoh JSON) dibiarkan."""
        out = self.text
        for key, value in values.items():
            out = out.replace("{" + key + "}", str(value))
        return out


@lru_cache
def load_prompt(name: str) -> Prompt:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    match = _VERSION_RE.match(raw)
    if not match:
        raise ValueError(f"Prompt {name}.md tanpa baris versi '<!-- version: ... -->'")
    return Prompt(name, match.group(1), raw[match.end():])
