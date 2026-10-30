"""Pemetaan persona → suara per provider.

Urutan prioritas voice: variabel `.env` khusus persona (mis. `EDGE_VOICE_RAKA`), lalu `voices` di
kartu persona, lalu default menurut gender (`EDGE_VOICE_MALE`). Rate dan pitch Edge per persona
juga dari `.env` (`EDGE_RATE_RAKA`, `EDGE_PITCH_RAKA`).
"""

from __future__ import annotations

from app.tts.base import TTSError


class VoiceBook:
    def __init__(self, settings, personas: dict):
        self._s = settings
        self._personas = personas

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
            getattr(self._s, f"{key}_VOICE_{persona.upper()}", "")
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
