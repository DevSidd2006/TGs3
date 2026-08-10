from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import ensure_schema
from app.main import build_app
from app.previews import PreviewRenderer
from app.repository import FileRepository
from app.service import StorageService
from tests.fakes import FakeTelegramStorage


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    connection = sqlite3.connect(tmp_path / "files.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=10, file_id="tg-10")
    service = StorageService(repository, telegram, channel_id=-10055)
    created = repository.create_uploading(name="seed.txt", size_bytes=4, mime_type="text/plain")
    repository.mark_ready(file_id=created.id, telegram_channel_id=-10055, telegram_message_id=10, telegram_file_id="tg-10")
    app = build_app(service, preview_renderer=PreviewRenderer(tmp_path / "previews"))
    return TestClient(app)
