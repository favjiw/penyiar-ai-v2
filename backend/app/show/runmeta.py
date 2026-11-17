"""Jejak kondisi sebuah sesi untuk `session_start` (FR-12): apa yang benar-benar berlaku, bukan hanya isi .env.

Dipakai riset: sesi tanpa Supervisor (KP) dan dengan Supervisor penuh harus bisa dibedakan dan diulang dari log
saja. `SUPERVISOR_MODE` di .env bisa menyesatkan (PILOT_CONDITION=D memaksa `full`), jadi mode yang berlaku
dicatat terpisah, bersama commit kode, temperature, dan hash isi prompt serta kartu persona.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@lru_cache
def git_revision() -> dict[str, Any]:
    """SHA commit kode yang berjalan dan apakah ada perubahan yang belum di-commit; kosong bila bukan repo git.

    Di image Docker tidak ada folder .git: SHA datang dari variabel GIT_SHA yang diisi saat build (dirty = False).
    """
    if sha := os.environ.get("GIT_SHA", "").strip():
        return {"sha": sha, "dirty": False}

    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=Path(REPO_ROOT), capture_output=True, text=True, timeout=5, check=True).stdout.strip()

    try:
        return {"sha": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}
    except (OSError, subprocess.SubprocessError):
        return {"sha": "", "dirty": None}


def run_metadata(engine: Any) -> dict[str, Any]:
    """Medan tambahan `session_start`: kondisi pilot, mode Supervisor yang berlaku, temperature, commit, hash."""
    s = engine.settings
    agents = (engine.persona_agent, engine.supervisor, engine.showrunner, engine.summary)
    return {
        "pilot_condition": s.PILOT_CONDITION,
        "supervisor_mode_effective": engine.supervisor.mode,  # SUPERVISOR_MODE di .env bukan jaminan: kondisi D memaksa `full`
        "persona_temperature": s.PERSONA_TEMPERATURE,
        "code": git_revision(),
        "prompt_hashes": {a.prompt.name: _digest(a.prompt.text) for a in agents},
        "persona_hashes": {p.id: _digest(p.model_dump_json()) for p in engine.personas},
    }
