"""Enkripsi nilai rahasia (kunci API) yang disimpan di database.

Kunci induk `SECRETS_KEY` (Fernet, 32 byte base64) hanya ada di lingkungan server (.env), tidak di database,
jadi dump database saja tidak membuka kunci API. Buat kunci: `python -m app.cli gen-secrets-key`.
Kunci induk hilang atau berganti = nilai lama tidak terbaca (diabaikan, kembali ke .env); simpan cadangannya.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)
PREFIX = "enc:"


def generate_key() -> str:
    return Fernet.generate_key().decode()


class SecretBox:
    def __init__(self, key: str = ""):
        self._fernet: Fernet | None = None
        key = key.strip()
        if key:
            try:
                self._fernet = Fernet(key.encode())
            except (ValueError, TypeError):
                logger.error("SECRETS_KEY tidak valid (harus kunci Fernet 32 byte base64); kunci API tidak bisa disimpan")

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plain: str) -> str:
        if self._fernet is None:
            raise RuntimeError("SECRETS_KEY belum diatur")
        return PREFIX + self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, stored: str) -> str | None:
        """Teks asli, atau None bila tidak terbaca (kunci induk berganti/hilang)."""
        if self._fernet is None or not stored.startswith(PREFIX):
            return None
        try:
            return self._fernet.decrypt(stored[len(PREFIX):].encode()).decode()
        except InvalidToken:
            return None
