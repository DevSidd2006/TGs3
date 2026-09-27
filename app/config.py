from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()


BLOCKCHAIN_REQUIRED_ENV = (
    "BLOCKCHAIN_RPC_URL",
    "BLOCKCHAIN_CONTRACT_ADDRESS",
    "BLOCKCHAIN_CHAIN_ID",
    "ENCRYPTION_MASTER_KEY",
)


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
    secure_cookie: bool = True
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    blockchain_enabled: bool = False
    blockchain_rpc_url: str | None = None
    blockchain_contract_address: str | None = None
    blockchain_chain_id: int | None = None
    blockchain_abi_path: Path = Path("contracts/out/FileRegistry.sol/FileRegistry.json")
    encryption_master_key: str | None = None


def _optional_env(name: str) -> str | None:
    return os.environ.get(name) or None


def _require_blockchain_settings() -> None:
    missing = [name for name in BLOCKCHAIN_REQUIRED_ENV if not _optional_env(name)]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"BLOCKCHAIN_ENABLED=1 requires: {joined}")


def load_settings() -> Settings:
    blockchain_enabled = os.environ.get("BLOCKCHAIN_ENABLED", "0") == "1"
    if blockchain_enabled:
        _require_blockchain_settings()
    chain_id = os.environ.get("BLOCKCHAIN_CHAIN_ID")
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
        secure_cookie=os.environ.get("TGS3_SECURE_COOKIE", "1") == "1",
        max_upload_bytes=int(os.environ.get("TGS3_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))),
        blockchain_enabled=blockchain_enabled,
        blockchain_rpc_url=_optional_env("BLOCKCHAIN_RPC_URL"),
        blockchain_contract_address=_optional_env("BLOCKCHAIN_CONTRACT_ADDRESS"),
        blockchain_chain_id=int(chain_id) if chain_id else None,
        blockchain_abi_path=Path(os.environ.get("BLOCKCHAIN_ABI_PATH", "contracts/out/FileRegistry.sol/FileRegistry.json")),
        encryption_master_key=_optional_env("ENCRYPTION_MASTER_KEY"),
    )
