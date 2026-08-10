from pathlib import Path

from app.db import connect_db, ensure_schema
from app.repository import FileRepository


def test_repository_round_trip(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)

    created = repository.create_uploading(name="photo.png", size_bytes=10, mime_type="image/png")
    repository.mark_ready(
        file_id=created.id,
        telegram_channel_id=-1001,
        telegram_message_id=77,
        telegram_file_id="abc123",
    )

    stored = repository.get_file(created.id)

    assert stored is not None
    assert stored.status == "ready"
    assert stored.telegram_message_id == 77


def test_repository_search_matches_name(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)

    first = repository.create_uploading(name="budget-2026.xlsx", size_bytes=100, mime_type="application/vnd.ms-excel")
    second = repository.create_uploading(name="notes.txt", size_bytes=20, mime_type="text/plain")
    repository.mark_failed(first.id)
    repository.mark_failed(second.id)

    result = repository.search_files("budget")

    assert [item.name for item in result] == ["budget-2026.xlsx"]


def test_schema_has_folders_table_and_folder_id_column(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "folders" in tables
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    assert "folder_id" in columns
