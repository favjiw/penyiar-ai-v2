import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Tiap tes punya SQLite sendiri (DATA_DIR sementara): data aplikasi ada di database, bukan berkas."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
