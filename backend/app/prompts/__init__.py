"""Prompt berversi dari database (lihat app/content.py); modul ini hanya pintu impor yang tetap."""

from app.content import Prompt, load_prompt

__all__ = ["Prompt", "load_prompt"]
