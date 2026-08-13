from pathlib import Path
import sqlite3


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
    if "folder_id" not in file_columns:
        connection.execute("ALTER TABLE files ADD COLUMN folder_id INTEGER REFERENCES folders(id)")
    if "share_token" not in file_columns:
        connection.execute("ALTER TABLE files ADD COLUMN share_token TEXT")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_share_token ON files(share_token)")
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
