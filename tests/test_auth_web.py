from fastapi.testclient import TestClient

from app.main import build_app
from app.repository import FileRepository, AuthRepository
from app.previews import PreviewRenderer
from app.service import StorageService
from tests.fakes import FakeTelegramStorage


def make_client(tmp_path, *, password: str = "s3cret"):
    import sqlite3
    connection = sqlite3.connect(tmp_path / "files.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    from app.db import ensure_schema
    ensure_schema(connection)
    repository = FileRepository(connection)
    auth = AuthRepository(connection)
    auth.upsert_user(username="admin", password_hash="not-used")  # seeded in build_app anyway
    telegram = FakeTelegramStorage(message_id=1, file_id="tg-1")
    service = StorageService(repository, telegram, channel_id=-10055)
    app = build_app(
        service,
        preview_renderer=PreviewRenderer(tmp_path / "previews"),
        auth_password=password,
        secure_cookie=False,
    )
    return TestClient(app, follow_redirects=False), auth


def test_unauthenticated_html_redirects_to_login(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_api_returns_401(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/files")
    assert response.status_code == 401


def test_login_success_sets_session_cookie(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    response = client.post("/login", data={"username": "admin", "password": "s3cret"})
    assert response.status_code == 303
    assert "tgs3_session" in response.cookies


def test_login_wrong_password_rejected(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    response = client.post("/login", data={"username": "admin", "password": "nope"})
    assert response.status_code == 401


def test_authenticated_access_and_logout(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    client.post("/login", data={"username": "admin", "password": "s3cret"})
    assert client.get("/").status_code == 200
    logout = client.post("/logout")
    assert logout.status_code == 303
    assert client.get("/").status_code == 303


def test_mobile_page_requires_auth(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/mobile")
    assert response.status_code == 303


def test_static_and_manifest_exempt_from_auth(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/static/styles.css?v=9").status_code == 200
    assert client.get("/mobile/manifest.webmanifest").status_code == 200


def test_login_page_neutralizes_external_next(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/login", params={"next": "https://evil.example/phish"})
    assert response.status_code == 200
    assert "https://evil.example" not in response.text


def test_login_post_neutralizes_external_next(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "s3cret", "next": "https://evil.example/phish"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_post_neutralizes_protocol_relative_next(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "s3cret", "next": "//evil.example/phish"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_post_allows_relative_next(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "s3cret", "next": "/view/files/1"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/view/files/1"
