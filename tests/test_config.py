from pathlib import Path

from app.config import Settings, load_settings


def test_load_settings_reads_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100987654321")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))
    monkeypatch.setenv("TGS3_PASSWORD", "")

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


def _set_required_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100987654321")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))


def test_secure_cookie_defaults_to_true(monkeypatch, tmp_path: Path):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.delenv("TGS3_SECURE_COOKIE", raising=False)

    assert load_settings().secure_cookie is True


def test_secure_cookie_can_be_disabled_for_lan_use(monkeypatch, tmp_path: Path):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("TGS3_SECURE_COOKIE", "0")

    assert load_settings().secure_cookie is False


def test_max_upload_bytes_reads_environment(monkeypatch, tmp_path: Path):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("TGS3_MAX_UPLOAD_BYTES", "1024")

    assert load_settings().max_upload_bytes == 1024
