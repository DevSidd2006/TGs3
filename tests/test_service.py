import asyncio
from pathlib import Path

from app.db import connect_db, ensure_schema
from app.repository import FileRepository
from app.service import StorageService
from tests.fakes import FakeTelegramStorage


def test_upload_marks_file_ready(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=5, file_id="tg-5")
    service = StorageService(repository, telegram, channel_id=-10099)

    stored = asyncio.run(
        service.upload_bytes(
            filename="notes.txt",
            content=b"hello",
            mime_type="text/plain",
        )
    )

    assert stored.status == "ready"
    assert stored.telegram_message_id == 5


def test_upload_failure_marks_file_failed(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=0, file_id="", should_fail=True)
    service = StorageService(repository, telegram, channel_id=-10099)

    try:
        asyncio.run(
            service.upload_bytes(filename="bad.bin", content=b"broken", mime_type="application/octet-stream")
        )
    except RuntimeError:
        pass

    files = repository.list_files()
    assert len(files) == 1
    assert files[0].status == "failed"
