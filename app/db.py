from pathlib import Path
import sqlite3


FILE_COLUMN_MIGRATIONS: dict[str, str] = {
    "folder_id": "ALTER TABLE files ADD COLUMN folder_id INTEGER REFERENCES folders(id)",
    "share_token": "ALTER TABLE files ADD COLUMN share_token TEXT",
    "starred": "ALTER TABLE files ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
    "deleted_at": "ALTER TABLE files ADD COLUMN deleted_at TEXT",
    "blockchain_file_id": "ALTER TABLE files ADD COLUMN blockchain_file_id TEXT",
    "content_hash": "ALTER TABLE files ADD COLUMN content_hash TEXT",
    "wrapped_key": "ALTER TABLE files ADD COLUMN wrapped_key TEXT",
    "storage_state": "ALTER TABLE files ADD COLUMN storage_state TEXT NOT NULL DEFAULT 'pending'",
    "chain_state": "ALTER TABLE files ADD COLUMN chain_state TEXT NOT NULL DEFAULT 'not_submitted'",
    "register_tx_hash": "ALTER TABLE files ADD COLUMN register_tx_hash TEXT",
    "register_block_number": "ALTER TABLE files ADD COLUMN register_block_number INTEGER",
    "owner_wallet": "ALTER TABLE files ADD COLUMN owner_wallet TEXT",
}


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
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
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES folders(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    file_columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    for column, migration in FILE_COLUMN_MIGRATIONS.items():
        if column not in file_columns:
            connection.execute(migration)

    folder_columns = {row["name"] for row in connection.execute("PRAGMA table_info(folders)")}
    if "starred" not in folder_columns:
        connection.execute("ALTER TABLE folders ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_share_token ON files(share_token)")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_blockchain_file_id ON files(blockchain_file_id)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL REFERENCES users(username),
            expires_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
