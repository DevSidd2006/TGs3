from app.main import create_app
from fastapi.testclient import TestClient
from tests.fakes import FakeTelegramStorage


def test_dashboard_renders_existing_files(app_client: TestClient):
    response = app_client.get("/")

    assert response.status_code == 200
    assert "All Files" in response.text
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


def test_folder_tree_renders_nested(app_client: TestClient):
    app_client.post("/folders", json={"name": "Photos", "parent_id": None}).raise_for_status()
    created = app_client.post("/folders", json={"name": "2024", "parent_id": 1})
    assert created.status_code == 201
    folder_id = created.json()["id"]
    tree = app_client.get("/folders").json()
    assert tree[0]["name"] == "Photos"
    assert tree[0]["children"][0]["name"] == "2024"


def test_rename_folder_endpoint(app_client: TestClient):
    created = app_client.post("/folders", json={"name": "Old", "parent_id": None})
    folder_id = created.json()["id"]
    renamed = app_client.patch(f"/folders/{folder_id}", json={"name": "New"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New"


def test_delete_non_empty_folder_returns_409(app_client: TestClient):
    folder = app_client.post("/folders", json={"name": "Docs", "parent_id": None}).json()
    app_client.post(f"/folders", json={"name": "Sub", "parent_id": folder["id"]})
    response = app_client.delete(f"/folders/{folder['id']}")
    assert response.status_code == 409


def test_delete_empty_folder_returns_204(app_client: TestClient):
    folder = app_client.post("/folders", json={"name": "Empty", "parent_id": None}).json()
    response = app_client.delete(f"/folders/{folder['id']}")
    assert response.status_code == 204


def test_upload_into_folder(app_client: TestClient):
    folder = app_client.post("/folders", json={"name": "Docs", "parent_id": None}).json()
    response = app_client.post(
        "/files/upload",
        params={"folder_id": folder["id"]},
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["folder_id"] == folder["id"]


def test_move_file_endpoint(app_client: TestClient):
    folder = app_client.post("/folders", json={"name": "Docs", "parent_id": None}).json()
    upload = app_client.post(
        "/files/upload",
        files={"file": ("a.txt", b"hello", "text/plain")},
    ).json()
    moved = app_client.post(f"/files/{upload['id']}/move", json={"folder_id": folder["id"]})
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder["id"]


def test_dashboard_scoped_to_folder_shows_breadcrumb(app_client: TestClient):
    folder = app_client.post("/folders", json={"name": "Photos", "parent_id": None}).json()
    response = app_client.get("/", params={"folder_id": folder["id"]})
    assert response.status_code == 200
    assert "Photos" in response.text


def test_sync_endpoint_returns_count(app_client: TestClient):
    response = app_client.post("/sync")
    assert response.status_code == 200
    assert response.json() == {"synced_count": 1}


def test_sync_endpoint_rate_limited(app_client: TestClient):
    first = app_client.post("/sync")
    assert first.status_code == 200
    second = app_client.post("/sync")
    assert second.status_code == 429

def test_share_endpoints(app_client: TestClient):
    upload = app_client.post(
        "/files/upload",
        files={"file": ("share_me.txt", b"secret data", "text/plain")},
    )
    file_id = upload.json()["id"]

    res = app_client.post(f"/files/{file_id}/share", json={"enabled": True})
    assert res.status_code == 200
    token = res.json()["share_token"]
    assert token is not None

    # Public download
    # To test without auth, we can just clear cookies but app_client in this test fixture 
    # automatically authenticates. However, the /s/ endpoints don't check auth.
    dl_res = app_client.get(f"/s/{token}/download")
    assert dl_res.status_code == 200
    assert dl_res.content == b"downloaded"

    # Public preview
    pr_res = app_client.get(f"/s/{token}/preview")
    assert pr_res.status_code == 200
    assert pr_res.content == b"downloaded"

    # Turn off sharing
    app_client.post(f"/files/{file_id}/share", json={"enabled": False})
    dl_res_off = app_client.get(f"/s/{token}/download")
    assert dl_res_off.status_code == 404

