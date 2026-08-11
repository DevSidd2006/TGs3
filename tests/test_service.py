import asyncio
from pathlib import Path

from io import BytesIO

import pytest

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


def test_upload_stream_marks_file_ready(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=7, file_id="tg-7")
    service = StorageService(repository, telegram, channel_id=-10099)

    stream = BytesIO(b"streamed content")
    stored = asyncio.run(
        service.upload_stream(
            filename="stream.txt",
            file_obj=stream,
            size_bytes=16,
            mime_type="text/plain",
        )
    )

    assert stored.status == "ready"
    assert stored.size_bytes == 16
    assert stored.telegram_message_id == 7
    assert telegram.uploads[0].content == b"streamed content"


def test_upload_stream_failure_marks_file_failed(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=0, file_id="", should_fail=True)
    service = StorageService(repository, telegram, channel_id=-10099)

    stream = BytesIO(b"bad stream")
    try:
        asyncio.run(
            service.upload_stream(
                filename="bad_stream.bin",
                file_obj=stream,
                size_bytes=10,
                mime_type="application/octet-stream",
            )
        )
    except RuntimeError:
        pass

    files = repository.list_files()
    assert len(files) == 1
    assert files[0].status == "failed"


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


def test_service_folder_delegation(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    folder = service.create_folder(name="Docs", parent_id=None)
    assert service.get_folder(folder.id).name == "Docs"

    created = repository.create_uploading(name="a.txt", size_bytes=3, mime_type="text/plain")
    repository.mark_failed(created.id)
    moved = service.move_file(file_id=created.id, folder_id=folder.id)
    assert moved.folder_id == folder.id
    assert [f.name for f in service.list_files(folder_id=folder.id)] == ["a.txt"]
    assert service.list_files() == []
    assert service.get_breadcrumb(folder.id) == [folder]


def test_sync_from_channel(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    count = asyncio.run(service.sync_from_channel())
    assert count == 1
    files = service.list_files()
    assert len(files) == 1
    assert files[0].name == "synced_doc.pdf"
    assert files[0].telegram_message_id == 101


def test_sync_from_channel_twice_does_not_duplicate(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    asyncio.run(service.sync_from_channel())
    asyncio.run(service.sync_from_channel())

    files = service.list_files()
    assert len(files) == 1
    assert files[0].name == "synced_doc.pdf"
    assert files[0].telegram_message_id == 101


def test_download_nonexistent_file_raises_file_not_found(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=1, file_id="tg-1")
    service = StorageService(repository, telegram, channel_id=-10099)

    with pytest.raises(FileNotFoundError):
        asyncio.run(service.download_file(99999))


def test_download_file_without_telegram_message_id_raises(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=1, file_id="tg-1")
    service = StorageService(repository, telegram, channel_id=-10099)

    created = repository.create_uploading(name="pending.txt", size_bytes=10, mime_type="text/plain")

    with pytest.raises(FileNotFoundError):
        asyncio.run(service.download_file(created.id))


def test_delete_file(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repo = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=5, file_id="tg-5")
    service = StorageService(repo, telegram, channel_id=-10099)
    stored = repo.create_uploading(name="test.txt", size_bytes=100, mime_type="text/plain")
    service.delete_file(stored.id)
    assert repo.get_file(stored.id) is None

def test_rename_file(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repo = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=5, file_id="tg-5")
    service = StorageService(repo, telegram, channel_id=-10099)
    stored = repo.create_uploading(name="test.txt", size_bytes=100, mime_type="text/plain")
    service.rename_file(stored.id, "new.txt")
    assert repo.get_file(stored.id).name == "new.txt"
