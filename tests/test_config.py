from pathlib import Path

from app.config import Settings, load_settings


def test_load_settings_reads_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100987654321")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))

    settings = load_settings()

    assert settings == Settings(
        telegram_api_id=12345,
        telegram_api_hash="hash-value",
        telegram_channel_id=-100987654321,
        telegram_session=tmp_path / "telegram.session",
        database_path=tmp_path / "files.db",
        host="127.0.0.1",
        port=8000,
    )
