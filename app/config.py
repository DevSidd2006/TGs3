from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_channel_id: int
    telegram_session: Path
    database_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    tgs3_user: str = "admin"
    tgs3_password: str = ""
    session_ttl_days: int = 30
    sync_cooldown_seconds: int = 60
    secure_cookie: bool = False
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024



def load_settings() -> Settings:
    return Settings(
        telegram_api_id=int(os.environ["TELEGRAM_API_ID"]),
        telegram_api_hash=os.environ["TELEGRAM_API_HASH"],
        telegram_channel_id=int(os.environ["TELEGRAM_CHANNEL_ID"]),
        telegram_session=Path(os.environ["TELEGRAM_SESSION"]),
        database_path=Path(os.environ["DATABASE_PATH"]),
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8000")),
        tgs3_user=os.environ.get("TGS3_USER", "admin"),
        tgs3_password=os.environ.get("TGS3_PASSWORD", ""),
        session_ttl_days=int(os.environ.get("TGS3_SESSION_TTL_DAYS", "30")),
        sync_cooldown_seconds=int(os.environ.get("TGS3_SYNC_COOLDOWN_SECONDS", "60")),
        secure_cookie=os.environ.get("TGS3_SECURE_COOKIE", "0") == "1",
        max_upload_bytes=int(os.environ.get("TGS3_MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024)),
    )

