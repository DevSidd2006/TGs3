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


class TestFolderRepository:
    def _repo(self, tmp_path: Path) -> FileRepository:
        connection = connect_db(tmp_path / "files.db")
        ensure_schema(connection)
        return FileRepository(connection)

    def test_create_and_get_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="Photos", parent_id=None)
        assert folder.id is not None
        assert repository.get_folder(folder.id).name == "Photos"
        assert repository.get_folder(folder.id).parent_id is None

    def test_create_nested_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        parent = repository.create_folder(name="Photos", parent_id=None)
        child = repository.create_folder(name="2024", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_list_folders_flat(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        a = repository.create_folder(name="A", parent_id=None)
        b = repository.create_folder(name="B", parent_id=None)
        c = repository.create_folder(name="C", parent_id=a.id)
        names = {f.id: f.name for f in repository.list_folders()}
        assert set(names.values()) == {"A", "B", "C"}

    def test_rename_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="Old", parent_id=None)
        renamed = repository.rename_folder(folder.id, "New")
        assert renamed.name == "New"
        assert repository.get_folder(folder.id).name == "New"

    def test_delete_empty_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="Empty", parent_id=None)
        repository.delete_folder(folder.id)
        assert repository.get_folder(folder.id) is None

    def test_delete_non_empty_folder_raises(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="HasStuff", parent_id=None)
        child = repository.create_folder(name="Sub", parent_id=folder.id)
        try:
            repository.delete_folder(folder.id)
        except ValueError as exc:
            assert "not empty" in str(exc)
        else:
            raise AssertionError("expected ValueError")
        assert repository.get_folder(child.id) is not None

    def test_move_file_into_and_out_of_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="Docs", parent_id=None)
        created = repository.create_uploading(name="a.txt", size_bytes=3, mime_type="text/plain")
        repository.mark_failed(created.id)
        moved = repository.move_file(file_id=created.id, folder_id=folder.id)
        assert moved.folder_id == folder.id
        back = repository.move_file(file_id=created.id, folder_id=None)
        assert back.folder_id is None

    def test_list_files_filters_by_folder(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        folder = repository.create_folder(name="Docs", parent_id=None)
        in_folder = repository.create_uploading(name="a.txt", size_bytes=3, mime_type="text/plain")
        at_root = repository.create_uploading(name="b.txt", size_bytes=3, mime_type="text/plain")
        repository.mark_failed(in_folder.id)
        repository.mark_failed(at_root.id)
        repository.move_file(file_id=in_folder.id, folder_id=folder.id)
        assert [f.name for f in repository.list_files(folder_id=folder.id)] == ["a.txt"]
        assert [f.name for f in repository.list_files(folder_id=None)] == ["b.txt"]

    def test_breadcrumb_walks_up_to_root(self, tmp_path: Path):
        repository = self._repo(tmp_path)
        root = repository.create_folder(name="Photos", parent_id=None)
        year = repository.create_folder(name="2024", parent_id=root.id)
        trip = repository.create_folder(name="Trip", parent_id=year.id)
        crumbs = repository.get_breadcrumb(trip.id)
        assert [(f.id, f.name) for f in crumbs] == [(root.id, "Photos"), (year.id, "2024"), (trip.id, "Trip")]
