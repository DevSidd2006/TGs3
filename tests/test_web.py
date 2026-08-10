from app.main import create_app
from fastapi.testclient import TestClient
from tests.fakes import FakeTelegramStorage


def test_dashboard_renders_existing_files(app_client: TestClient):
    response = app_client.get("/")

    assert response.status_code == 200
    assert "File Explorer" in response.text
    assert "seed.txt" in response.text


def test_upload_endpoint_returns_ready_file(app_client: TestClient):
    response = app_client.post(
        "/files/upload",
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "hello.txt"
    assert body["status"] == "ready"


def test_search_endpoint_filters_by_query(app_client: TestClient):
    response = app_client.get("/files/search", params={"q": "seed"})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["seed.txt"]


def test_detail_page_shows_download_link(app_client: TestClient):
    response = app_client.get("/view/files/1")

    assert response.status_code == 200
    assert "/files/1/download" in response.text


def test_preview_image_returns_inline(app_client: TestClient):
    upload = app_client.post(
        "/files/upload",
        files={"file": ("photo.png", b"png-bytes", "image/png")},
    )
    file_id = upload.json()["id"]

    response = app_client.get(f"/files/{file_id}/preview")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert "inline" in response.headers["content-disposition"]


def test_preview_unsupported_returns_415(app_client: TestClient):
    upload = app_client.post(
        "/files/upload",
        files={"file": ("archive.7z", b"7z-bytes", "application/x-7z-compressed")},
    )
    file_id = upload.json()["id"]

    response = app_client.get(f"/files/{file_id}/preview")

    assert response.status_code == 415


def test_preview_missing_file_returns_404(app_client: TestClient):
    response = app_client.get("/files/999/preview")

    assert response.status_code == 404


def test_create_app_builds_routes_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100123456789")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))

    app = create_app(telegram_storage=FakeTelegramStorage(message_id=1, file_id="tg-1"))

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/files/upload" in paths
