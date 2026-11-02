"""Pemetaan persona → suara per provider.

Urutan prioritas voice: pilihan operator (`select`, dari daftar suara terkurasi), variabel `.env` khusus persona (mis. `EDGE_VOICE_RAKA`), lalu `voices` di
kartu persona, lalu default menurut gender (`EDGE_VOICE_MALE`). Rate dan pitch Edge per persona
juga dari `.env` (`EDGE_RATE_RAKA`, `EDGE_PITCH_RAKA`).
"""

from __future__ import annotations

from app.tts.base import TTSError
from app.tts.catalog import find_voice


class VoiceBook:
    def __init__(self, settings, personas: dict):
        self._s = settings
        self._personas = personas
        self._selected: dict[tuple[str, str], str] = {}  # (provider, persona) -> voice id pilihan operator

    def select(self, selection: dict[str, str]) -> None:
        """Pilihan operator (persona -> id suara dari katalog); menggantikan pilihan sebelumnya dan menang atas `.env`."""
        chosen: dict[tuple[str, str], str] = {}
        for persona, voice_id in selection.items():
            self._card(persona)
            option = find_voice(voice_id)
            if option is None:
                raise TTSError(f"Suara {voice_id!r} tidak ada di daftar suara terkurasi")
            chosen[(option.provider, persona)] = option.id
        self._selected = chosen

    def _card(self, persona: str):
        card = self._personas.get(persona)
        if card is None:
            raise TTSError(f"Persona {persona!r} tidak dikenal untuk TTS")
        return card

    def voice(self, provider: str, persona: str) -> str:
        """Voice ID `provider` ('elevenlabs' | 'edge') untuk satu persona."""
        card = self._card(persona)
        key = provider.upper()
        voice = (
            self._selected.get((provider, persona), "")
            or getattr(self._s, f"{key}_VOICE_{persona.upper()}", "")
            or card.voices.get(provider, "")
            or getattr(self._s, f"{key}_VOICE_{card.gender.upper()}", "")
        )
        if not voice:
            raise TTSError(f"Voice {provider} untuk {persona} kosong; isi {key}_VOICE_{persona.upper()} atau kartu persona")
        return voice

    def prosody(self, persona: str) -> tuple[str, str]:
        """(rate, pitch) Edge TTS untuk satu persona, mis. ('+4%', '-2Hz')."""
        self._card(persona)
        rate = getattr(self._s, f"EDGE_RATE_{persona.upper()}", "") or "+0%"
        pitch = getattr(self._s, f"EDGE_PITCH_{persona.upper()}", "") or "+0Hz"
        return rate, pitch
