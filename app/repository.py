import secrets
from datetime import datetime, timedelta
import sqlite3

from app.models import Folder, StoredFile


class FileRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_uploading(self, *, name: str, size_bytes: int, mime_type: str | None) -> StoredFile:
        cursor = self._connection.execute(
            "INSERT INTO files (name, size_bytes, mime_type, status) VALUES (?, ?, ?, 'uploading')",
            (name, size_bytes, mime_type),
        )
        self._connection.commit()
        return self.get_file(cursor.lastrowid)  # type: ignore[return-value]

    def mark_ready(self, *, file_id: int, telegram_channel_id: int, telegram_message_id: int, telegram_file_id: str) -> None:
        self._connection.execute(
            """
            UPDATE files
            SET telegram_channel_id = ?, telegram_message_id = ?, telegram_file_id = ?, status = 'ready'
            WHERE id = ?
            """,
            (telegram_channel_id, telegram_message_id, telegram_file_id, file_id),
        )
        self._connection.commit()

    def mark_failed(self, file_id: int) -> None:
        self._connection.execute("UPDATE files SET status = 'failed' WHERE id = ?", (file_id,))
        self._connection.commit()

    def upsert_synced_file(self, *, name: str, size_bytes: int, mime_type: str | None, telegram_channel_id: int, telegram_message_id: int, telegram_file_id: str) -> StoredFile:
        existing = self._connection.execute(
            "SELECT id FROM files WHERE telegram_channel_id = ? AND telegram_message_id = ?",
            (telegram_channel_id, telegram_message_id),
        ).fetchone()
        if existing:
            self._connection.execute(
                """
                UPDATE files
                SET name = ?, size_bytes = ?, mime_type = ?, telegram_file_id = ?, status = 'ready'
                WHERE id = ?
                """,
                (name, size_bytes, mime_type, telegram_file_id, existing["id"]),
            )
            self._connection.commit()
            return self.get_file(existing["id"])  # type: ignore[return-value]
        else:
            cursor = self._connection.execute(
                """
                INSERT INTO files (name, size_bytes, mime_type, status, telegram_channel_id, telegram_message_id, telegram_file_id)
                VALUES (?, ?, ?, 'ready', ?, ?, ?)
                """,
                (name, size_bytes, mime_type, telegram_channel_id, telegram_message_id, telegram_file_id),
            )
            self._connection.commit()
            return self.get_file(cursor.lastrowid)  # type: ignore[return-value]

    def get_file(self, file_id: int) -> StoredFile | None:

        row = self._connection.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return None if row is None else self._row_to_model(row)

    def list_files(self, folder_id: int | None = None) -> list[StoredFile]:
        if folder_id is None:
            rows = self._connection.execute(
                "SELECT * FROM files WHERE folder_id IS NULL ORDER BY uploaded_at DESC, id DESC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM files WHERE folder_id = ? ORDER BY uploaded_at DESC, id DESC",
                (folder_id,),
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def search_files(self, query: str) -> list[StoredFile]:
        rows = self._connection.execute(
            "SELECT * FROM files WHERE name LIKE ? ORDER BY uploaded_at DESC, id DESC",
            (f"%{query}%",),
        ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def create_folder(self, *, name: str, parent_id: int | None) -> Folder:
        name = name.strip()
        if not name:
            raise ValueError("folder name must not be empty")
        if parent_id is not None and self.get_folder(parent_id) is None:
            raise ValueError(f"parent folder {parent_id} not found")
        cursor = self._connection.execute(
            "INSERT INTO folders (name, parent_id) VALUES (?, ?)",
            (name, parent_id),
        )
        self._connection.commit()
        folder = self.get_folder(cursor.lastrowid)
        assert folder is not None
        return folder

    def rename_folder(self, folder_id: int, name: str) -> Folder:
        name = name.strip()
        if not name:
            raise ValueError("folder name must not be empty")
        folder = self.get_folder(folder_id)
        if folder is None:
            raise ValueError(f"folder {folder_id} not found")
        self._connection.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
        self._connection.commit()
        updated = self.get_folder(folder_id)
        assert updated is not None
        return updated

    def delete_folder(self, folder_id: int) -> None:
        direct_children = self._connection.execute(
            "SELECT COUNT(*) AS count FROM folders WHERE parent_id = ?", (folder_id,)
        ).fetchone()
        file_count = self._connection.execute(
            "SELECT COUNT(*) AS count FROM files WHERE folder_id = ?", (folder_id,)
        ).fetchone()
        if direct_children["count"] > 0 or file_count["count"] > 0:
            raise ValueError(f"folder {folder_id} is not empty")
        self._connection.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self._connection.commit()

    def get_folder(self, folder_id: int) -> Folder | None:
        row = self._connection.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return None
        return Folder(id=row["id"], name=row["name"], parent_id=row["parent_id"])

    def list_folders(self) -> list[Folder]:
        rows = self._connection.execute(
            "SELECT * FROM folders ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [Folder(id=row["id"], name=row["name"], parent_id=row["parent_id"]) for row in rows]

    def move_file(self, *, file_id: int, folder_id: int | None) -> StoredFile:
        if self.get_file(file_id) is None:
            raise ValueError(f"file {file_id} not found")
        if folder_id is not None and self.get_folder(folder_id) is None:
            raise ValueError(f"folder {folder_id} not found")
        self._connection.execute("UPDATE files SET folder_id = ? WHERE id = ?", (folder_id, file_id))
        self._connection.commit()
        moved = self.get_file(file_id)
        assert moved is not None
        return moved

    def get_breadcrumb(self, folder_id: int) -> list[Folder]:
        chain: list[Folder] = []
        current = folder_id
        seen: set[int] = set()
        while current is not None:
            if current in seen:
                raise ValueError("folder cycle detected")
            seen.add(current)
            folder = self.get_folder(current)
            if folder is None:
                raise ValueError(f"folder {current} not found")
            chain.append(folder)
            current = folder.parent_id
        chain.reverse()
        return chain

    def set_share_token(self, file_id: int, enable: bool) -> str | None:
        if enable:
            token = secrets.token_urlsafe(16)
            self._connection.execute("UPDATE files SET share_token = ? WHERE id = ?", (token, file_id))
        else:
            token = None
            self._connection.execute("UPDATE files SET share_token = NULL WHERE id = ?", (file_id,))
        self._connection.commit()
        return token

    def get_file_by_share_token(self, token: str) -> StoredFile | None:
        row = self._connection.execute("SELECT * FROM files WHERE share_token = ?", (token,)).fetchone()
        return None if row is None else self._row_to_model(row)

    def _row_to_model(self, row: sqlite3.Row) -> StoredFile:
        return StoredFile(
            id=row["id"],
            name=row["name"],
            size_bytes=row["size_bytes"],
            mime_type=row["mime_type"],
            telegram_channel_id=row["telegram_channel_id"],
            telegram_message_id=row["telegram_message_id"],
            telegram_file_id=row["telegram_file_id"],
            status=row["status"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            folder_id=row["folder_id"] if "folder_id" in row.keys() else None,
            share_token=row["share_token"] if "share_token" in row.keys() else None,
        )


class AuthRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_user(self, *, username: str, password_hash: str) -> None:
        self._connection.execute(
            """
            INSERT INTO users (username, password_hash) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
            """,
            (username, password_hash),
        )
        self._connection.commit()

    def verify_user(self, username: str, password_hash: str) -> bool:
        row = self._connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row is not None and row["password_hash"] == password_hash

    def get_user_hash(self, username: str) -> str | None:
        row = self._connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return None if row is None else row["password_hash"]

    def cleanup_expired_sessions(self) -> int:
        now = datetime.utcnow().isoformat()
        cursor = self._connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self._connection.commit()
        return cursor.rowcount

    def create_session(self, *, username: str, ttl: timedelta) -> str:
        self.cleanup_expired_sessions()
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + ttl).isoformat()
        self._connection.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires),
        )
        self._connection.commit()
        return token

    def get_session_user(self, token: str) -> str | None:
        row = self._connection.execute(
            "SELECT username, expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires <= datetime.utcnow():
            self.delete_session(token)
            return None
        return row["username"]

    def delete_session(self, token: str) -> None:
        self._connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self._connection.commit()
