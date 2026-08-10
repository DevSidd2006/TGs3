from datetime import datetime
import sqlite3

from app.models import StoredFile


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

    def get_file(self, file_id: int) -> StoredFile | None:
        row = self._connection.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return None if row is None else self._row_to_model(row)

    def list_files(self) -> list[StoredFile]:
        rows = self._connection.execute("SELECT * FROM files ORDER BY uploaded_at DESC, id DESC").fetchall()
        return [self._row_to_model(row) for row in rows]

    def search_files(self, query: str) -> list[StoredFile]:
        rows = self._connection.execute(
            "SELECT * FROM files WHERE name LIKE ? ORDER BY uploaded_at DESC, id DESC",
            (f"%{query}%",),
        ).fetchall()
        return [self._row_to_model(row) for row in rows]

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
        )
