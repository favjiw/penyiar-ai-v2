"""Manajer WebSocket /ws/session (PRD §6.3), pola dari main.py repo lama.

Setiap klien menyatakan role: `console` (konsol operator) atau `prompter`
(penyiar manusia, mode A dan C). Hanya satu klien yang memutar audio
(pemilik audio): konsol pertama yang tersambung. Hanya laporan pemutaran dari
pemilik audio yang dipakai Show Engine.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)
ROLES = ("console", "prompter")

# Event yang dikirim ke role tertentu saja; selain ini dikirim ke semua.
EVENT_ROLES: dict[str, tuple[str, ...]] = {
    "supervisor": ("console",),
    "output_status": ("console",),
    "stt_partial": ("console",),
}


class ConnectionManager:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, str] = {}
        self.audio_blocked: set[WebSocket] = set()

    async def connect(self, ws: WebSocket, role: str) -> None:
        await ws.accept()
        self.clients[ws] = role if role in ROLES else "console"
        logger.info("WS tersambung (role=%s), total %d", self.clients[ws], len(self.clients))

    def disconnect(self, ws: WebSocket) -> None:
        self.audio_blocked.discard(ws)
        self.clients.pop(ws, None)

    def audio_owner(self) -> Optional[WebSocket]:
        for ws, r in self.clients.items():
            if r == "console":
                return ws
        return None

    def output_status(self, ws: WebSocket | None = None) -> dict[str, Any]:
        roles = list(self.clients.values())
        owner = self.audio_owner()
        return {
            "is_audio_owner": ws is not None and ws is owner,
            "audio_owner_role": self.clients.get(owner) if owner else None,
            "audio_blocked": any(self.clients.get(w) == "console" for w in self.audio_blocked),
            "clients": {r: roles.count(r) for r in ROLES},
        }

    async def send(self, ws: WebSocket, type_: str, data: dict[str, Any]) -> None:
        await ws.send_json({"type": type_, "data": data})

    async def broadcast(self, type_: str, data: dict[str, Any]) -> None:
        roles = EVENT_ROLES.get(type_)
        for ws, role in list(self.clients.items()):
            if roles is not None and role not in roles:
                continue
            try:
                await self.send(ws, type_, data)
            except Exception:
                self.disconnect(ws)

    async def broadcast_output_status(self) -> None:
        for ws, role in list(self.clients.items()):
            try:
                await self.send(ws, "output_status", self.output_status(ws))
            except Exception:
                self.disconnect(ws)
