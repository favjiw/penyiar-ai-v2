"""Ringkasan obrolan berjalan untuk prompt persona.

Prompt persona hanya memuat HISTORY_TURNS giliran terakhir. Pada obrolan panjang (target 40+ menit)
giliran yang keluar dari jendela itu dirangkum tiap `every` giliran, di latar belakang (tidak
menahan giliran berikutnya), lalu ringkasannya ikut di prompt. Bila LLM gagal, giliran itu
dimasukkan secara ekstraktif (kalimat pembuka tiap giliran) supaya konteks tidak hilang.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from pydantic import BaseModel

from app.agents.persona import HISTORY_TURNS, HistoryEntry
from app.llm import LLMClient, register_mock
from app.prompts import load_prompt

logger = logging.getLogger(__name__)
MAX_CHARS = 1000
SNIPPET_WORDS = 14


class SummaryOutput(BaseModel):
    summary: str


def _extract(entries: list[HistoryEntry]) -> str:
    return " ".join(f"{e.name}: {' '.join(e.text.split()[:SNIPPET_WORDS])}." for e in entries)


class ConversationSummary:
    def __init__(self, llm: LLMClient, model: str, every: int, window: int = HISTORY_TURNS):
        self._llm, self._model, self._every, self._window = llm, model, every, window
        self.prompt = load_prompt("summary")
        self.text = ""
        self.upto = 0  # jumlah entri riwayat yang sudah masuk ringkasan
        self.updates = 0
        self.failures = 0
        self._task: Optional[asyncio.Task] = None

    @property
    def enabled(self) -> bool:
        return self._every > 0

    def due(self, history: list[HistoryEntry]) -> bool:
        return self.enabled and len(history) - self._window - self.upto >= self._every

    def schedule(self, history: list[HistoryEntry]) -> None:
        """Perbarui di latar belakang bila sudah waktunya dan tidak ada pembaruan yang sedang berjalan."""
        if not self.due(history) or (self._task and not self._task.done()):
            return
        cut = len(history) - self._window
        chunk = list(history[self.upto : cut])
        self._task = asyncio.create_task(self._update(chunk, cut))

    async def _update(self, chunk: list[HistoryEntry], cut: int) -> None:
        prompt = f"RINGKASAN SEBELUMNYA: {self.text or '(belum ada)'}\n\nGILIRAN BARU:\n" + "\n".join(f"{e.name}: {e.text}" for e in chunk)
        try:
            resp = await self._llm.generate(
                prompt, model=self._model, system_instruction=self.prompt.text, response_schema=SummaryOutput, temperature=0.3
            )
            new = SummaryOutput.model_validate(resp.parsed).summary.strip()
            if not new:
                raise ValueError("ringkasan kosong")
            self.text = new[-MAX_CHARS:]
            self.updates += 1
        except Exception as e:  # kuota, jaringan, atau JSON rusak: jangan kehilangan konteks, jangan menghentikan siaran
            self.failures += 1
            logger.warning("Ringkasan obrolan gagal (%s); memakai kutipan ekstraktif", e)
            self.text = f"{self.text} {_extract(chunk)}".strip()[-MAX_CHARS:]
        self.upto = cut

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()


def _mock_summary(prompt: str, n: int) -> dict:
    lines = [l for l in prompt.split("GILIRAN BARU:\n")[-1].splitlines() if l.strip()]
    words = " ".join(" ".join(re.sub(r"^[^:]+:\s*", "", l).split()[:4]) for l in lines[:6])
    return {"summary": f"Sudah dibahas: {words}."}


register_mock(SummaryOutput, _mock_summary)
