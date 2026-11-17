"""Parameter perilaku yang bisa diubah admin (dulu konstanta di kode): akses ke nilai Settings yang berlaku.

Kode membaca `tuning.NAMA` setiap kali dipakai, jadi perubahan dari halaman admin berlaku pada giliran/siaran
berikutnya tanpa mulai ulang. Nilai awal dan batasnya didefinisikan di `Settings` (config.py); tanpa aplikasi
(skrip, tes unit) dipakai nilai bawaan Settings.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache
def _defaults():
    from app.config import Settings

    return Settings(_env_file=None)


class _Tuning:
    def __init__(self) -> None:
        self._settings = None

    def configure(self, settings) -> None:
        """Dipanggil aplikasi saat mulai; None = kembali ke nilai bawaan."""
        self._settings = settings

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._settings or _defaults(), name)


tuning = _Tuning()
