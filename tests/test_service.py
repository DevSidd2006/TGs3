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


def test_star_trash_restore_and_views(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    kept = repository.create_uploading(name="kept.txt", size_bytes=1, mime_type="text/plain")
    trashed = repository.create_uploading(name="gone.txt", size_bytes=1, mime_type="text/plain")
    repository.mark_failed(kept.id)
    repository.mark_failed(trashed.id)

    starred = service.star_file(kept.id, True)
    assert starred.starred is True
    assert [f.id for f in service.list_starred()["files"]] == [kept.id]

    service.trash_file(trashed.id)
    assert [f.id for f in service.list_files()] == [kept.id]
    assert [f.id for f in service.list_trash()] == [trashed.id]

    service.restore_file(trashed.id)
    assert sorted(f.id for f in service.list_files()) == sorted([kept.id, trashed.id])

    service.trash_file(trashed.id)
    purged = service.empty_trash()
    assert purged == 1
    assert service.list_trash() == []


def test_star_missing_file_raises_file_not_found(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    try:
        service.star_file(999, True)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_list_recent_and_shared(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=5, file_id="tg-5"), channel_id=-10099)

    a = repository.create_uploading(name="a.txt", size_bytes=1, mime_type="text/plain")
    repository.mark_failed(a.id)
    repository.set_share_token(a.id, True)

    assert [f.id for f in service.list_recent()] == [a.id]
    assert [f.id for f in service.list_shared()] == [a.id]


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

