import sqlite3
from pathlib import Path

from app.config import load_settings
from app.db import connect_db, ensure_schema
from app.repository import FileRepository


BLOCKCHAIN_COLUMNS = {
    "blockchain_file_id",
    "content_hash",
    "wrapped_key",
    "storage_state",
    "chain_state",
    "register_tx_hash",
    "register_block_number",
    "owner_wallet",
}


def test_schema_adds_blockchain_columns_to_fresh_database(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")

    ensure_schema(connection)

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    assert BLOCKCHAIN_COLUMNS.issubset(columns)


def test_schema_migrates_legacy_files_table_without_losing_rows(tmp_path: Path):
    connection = connect_db(tmp_path / "legacy.db")
    connection.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime_type TEXT,
            telegram_channel_id INTEGER,
            telegram_message_id INTEGER,
            telegram_file_id TEXT,
            status TEXT NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO files (name, size_bytes, mime_type, status)
        VALUES ('legacy.txt', 12, 'text/plain', 'ready')
        """
    )
    connection.commit()

    ensure_schema(connection)
    repository = FileRepository(connection)

    stored = repository.get_file(1)
    assert stored is not None
    assert stored.name == "legacy.txt"
    assert stored.storage_state == "pending"
    assert stored.chain_state == "not_submitted"
    assert stored.blockchain_file_id is None


def test_repository_tracks_storage_and_chain_state(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    created = repository.create_uploading(name="proof.pdf", size_bytes=42, mime_type="application/pdf")

    stored = repository.mark_storage_ready(
        file_id=created.id,
        content_hash="0x" + "a" * 64,
        wrapped_key="wrapped-key-material",
    )
    assert stored is not None
    assert stored.content_hash == "0x" + "a" * 64
    assert stored.wrapped_key == "wrapped-key-material"
    assert stored.storage_state == "stored"

    pending = repository.mark_chain_pending(
        file_id=created.id,
        blockchain_file_id="file-opaque-id",
        owner_wallet="0x0000000000000000000000000000000000000001",
        register_tx_hash="0xabc",
    )
    assert pending is not None
    assert pending.chain_state == "pending"
    assert pending.register_tx_hash == "0xabc"

    registered = repository.mark_chain_registered(
        file_id=created.id,
        blockchain_file_id="file-opaque-id",
        owner_wallet="0x0000000000000000000000000000000000000001",
        register_tx_hash="0xdef",
        register_block_number=123,
    )
    assert registered is not None
    assert registered.chain_state == "registered"
    assert registered.register_tx_hash == "0xdef"
    assert registered.register_block_number == 123
    assert repository.get_file_by_blockchain_id("file-opaque-id").id == created.id


def test_repository_marks_storage_and_chain_failures(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    created = repository.create_uploading(name="failed.bin", size_bytes=2, mime_type=None)

    assert repository.mark_storage_failed(created.id).storage_state == "failed"
    assert repository.mark_chain_failed(created.id).chain_state == "failed"


def test_repository_marks_chain_deleted_without_dropping_existing_receipt(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    created = repository.create_uploading(name="deleted.bin", size_bytes=2, mime_type=None)
    repository.mark_chain_registered(
        file_id=created.id,
        blockchain_file_id="delete-me",
        owner_wallet="0x0000000000000000000000000000000000000002",
        register_tx_hash="0xold",
        register_block_number=7,
    )

    deleted = repository.mark_chain_deleted(file_id=created.id)

    assert deleted is not None
    assert deleted.chain_state == "deleted"
    assert deleted.register_tx_hash == "0xold"
    assert deleted.register_block_number == 7


def test_blockchain_settings_are_optional_and_parse_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100987654321")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))
    monkeypatch.setenv("BLOCKCHAIN_ENABLED", "1")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    monkeypatch.setenv("BLOCKCHAIN_CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000003")
    monkeypatch.setenv("BLOCKCHAIN_CHAIN_ID", "31337")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "dev-master-key")

    settings = load_settings()

    assert settings.blockchain_enabled is True
    assert settings.blockchain_rpc_url == "http://127.0.0.1:8545"
    assert settings.blockchain_contract_address == "0x0000000000000000000000000000000000000003"
    assert settings.blockchain_chain_id == 31337
    assert settings.encryption_master_key == "dev-master-key"


def test_legacy_sqlite_connection_can_be_migrated(tmp_path: Path):
    db_path = tmp_path / "legacy-connect.db"
    raw = sqlite3.connect(db_path)
    raw.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime_type TEXT,
            telegram_channel_id INTEGER,
            telegram_message_id INTEGER,
            telegram_file_id TEXT,
            status TEXT NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    raw.commit()
    raw.close()

    connection = connect_db(db_path)
    ensure_schema(connection)

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    assert BLOCKCHAIN_COLUMNS.issubset(columns)
