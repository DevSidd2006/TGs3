import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import ensure_schema
from app.main import build_app
from app.previews import PreviewRenderer
from app.repository import FileRepository
from app.service import StorageService
from tests.fakes import FakeTelegramStorage


def make_client(tmp_path: Path, *, auth_password: str = "") -> TestClient:
    connection = sqlite3.connect(tmp_path / "files.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    repository = FileRepository(connection)
    service = StorageService(repository, FakeTelegramStorage(message_id=1, file_id="tg-1"), channel_id=-10055)
    app = build_app(service, preview_renderer=PreviewRenderer(tmp_path / "previews"), auth_password=auth_password)
    return TestClient(app)


def test_mobile_page_served(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/mobile")
    assert response.status_code == 200
    assert "TGS3" in response.text


def test_manifest_served(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/mobile/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/manifest+json"
    assert '"name": "TGS3"' in response.text


def test_service_worker_served(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/mobile/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/javascript"
    assert "CACHE" in response.text


def test_icons_served(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/mobile/icons/icon-192.png").status_code == 200
    assert client.get("/mobile/icons/icon-512.png").status_code == 200
