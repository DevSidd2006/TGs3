# TGS3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user local web app that uploads files into one private Telegram channel, indexes metadata in SQLite, and provides a minimal Drive-like UI for browse, search, detail, and download.

**Architecture:** Use a Python-first stack that avoids a JS build pipeline: FastAPI serves JSON APIs plus a server-hosted UI shell, SQLite stores file metadata, and a Telegram bridge module isolates Telethon-specific upload/download logic. Keep the upload/index/download path behind a `StorageService` so UI and API code never talk to Telegram directly.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2 templates, vanilla JavaScript, SQLite via `sqlite3`, Telethon sync client, pytest, httpx

---

## Planned File Structure

- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/models.py`
- Create: `app/db.py`
- Create: `app/repository.py`
- Create: `app/telegram_bridge.py`
- Create: `app/service.py`
- Create: `app/main.py`
- Create: `app/asgi.py`
- Create: `app/templates/base.html`
- Create: `app/templates/index.html`
- Create: `app/templates/file_detail.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Create: `tests/conftest.py`
- Create: `tests/fakes.py`
- Create: `tests/test_config.py`
- Create: `tests/test_repository.py`
- Create: `tests/test_service.py`
- Create: `tests/test_web.py`

## Notes Before Execution

- This plan assumes work happens inside `/home/devisdd/s3`.
- The directory is not a git repo yet. Run `git init` before the first commit step if that is still true at execution time.
- Keep the MVP single-user and local. Do not add auth, teams, folders UI, previews, or background jobs.

### Task 1: Bootstrap the Python App and Runtime Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing config test**

```python
# tests/test_config.py
from pathlib import Path

from app.config import Settings, load_settings


def test_load_settings_reads_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100987654321")
    monkeypatch.setenv("TELEGRAM_SESSION", str(tmp_path / "telegram.session"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "files.db"))

    settings = load_settings()

    assert settings == Settings(
        telegram_api_id=12345,
        telegram_api_hash="hash-value",
        telegram_channel_id=-100987654321,
        telegram_session=tmp_path / "telegram.session",
        database_path=tmp_path / "files.db",
        host="127.0.0.1",
        port=8000,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'` or `cannot import name 'load_settings'`

- [ ] **Step 3: Write the minimal implementation**

```toml
# pyproject.toml
[project]
name = "tgs3"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115,<1.0",
  "jinja2>=3.1,<4.0",
  "python-multipart>=0.0.9,<1.0",
  "telethon>=1.36,<2.0",
  "uvicorn>=0.30,<1.0",
]

[project.optional-dependencies]
dev = [
  "httpx>=0.27,<1.0",
  "pytest>=8.3,<9.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
```

```python
# app/config.py
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_channel_id: int
    telegram_session: Path
    database_path: Path
    host: str = "127.0.0.1"
    port: int = 8000


def load_settings() -> Settings:
    return Settings(
        telegram_api_id=int(os.environ["TELEGRAM_API_ID"]),
        telegram_api_hash=os.environ["TELEGRAM_API_HASH"],
        telegram_channel_id=int(os.environ["TELEGRAM_CHANNEL_ID"]),
        telegram_session=Path(os.environ["TELEGRAM_SESSION"]),
        database_path=Path(os.environ["DATABASE_PATH"]),
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8000")),
    )
```

```text
# .env.example
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace-me
TELEGRAM_CHANNEL_ID=-1000000000000
TELEGRAM_SESSION=.data/telegram.session
DATABASE_PATH=.data/files.db
APP_HOST=127.0.0.1
APP_PORT=8000
```

```python
# app/__init__.py
__all__ = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS with `1 passed`

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml .env.example app/__init__.py app/config.py tests/test_config.py
git commit -m "chore: bootstrap python app config"
```

### Task 2: Create the SQLite Schema and Metadata Repository

**Files:**
- Create: `app/models.py`
- Create: `app/db.py`
- Create: `app/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing repository tests**

```python
# tests/test_repository.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repository.py -v`
Expected: FAIL with missing `app.db` or `FileRepository`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/models.py
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StoredFile:
    id: int
    name: str
    size_bytes: int
    mime_type: str | None
    telegram_channel_id: int | None
    telegram_message_id: int | None
    telegram_file_id: str | None
    status: str
    uploaded_at: datetime
```

```python
# app/db.py
from pathlib import Path
import sqlite3


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime_type TEXT,
            telegram_channel_id INTEGER,
            telegram_message_id INTEGER,
            telegram_file_id TEXT,
            status TEXT NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
```

```python
# app/repository.py
from datetime import datetime
import sqlite3

from app.models import StoredFile


class FileRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_uploading(self, *, name: str, size_bytes: int, mime_type: str | None) -> StoredFile:
        cursor = self._connection.execute(
            "INSERT INTO files (name, size_bytes, mime_type, status) VALUES (?, ?, ?, 'uploading')",
            (name, size_bytes, mime_type),
        )
        self._connection.commit()
        return self.get_file(cursor.lastrowid)  # type: ignore[return-value]

    def mark_ready(self, *, file_id: int, telegram_channel_id: int, telegram_message_id: int, telegram_file_id: str) -> None:
        self._connection.execute(
            """
            UPDATE files
            SET telegram_channel_id = ?, telegram_message_id = ?, telegram_file_id = ?, status = 'ready'
            WHERE id = ?
            """,
            (telegram_channel_id, telegram_message_id, telegram_file_id, file_id),
        )
        self._connection.commit()

    def mark_failed(self, file_id: int) -> None:
        self._connection.execute("UPDATE files SET status = 'failed' WHERE id = ?", (file_id,))
        self._connection.commit()

    def get_file(self, file_id: int) -> StoredFile | None:
        row = self._connection.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return None if row is None else self._row_to_model(row)

    def list_files(self) -> list[StoredFile]:
        rows = self._connection.execute("SELECT * FROM files ORDER BY uploaded_at DESC, id DESC").fetchall()
        return [self._row_to_model(row) for row in rows]

    def search_files(self, query: str) -> list[StoredFile]:
        rows = self._connection.execute(
            "SELECT * FROM files WHERE name LIKE ? ORDER BY uploaded_at DESC, id DESC",
            (f"%{query}%",),
        ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def _row_to_model(self, row: sqlite3.Row) -> StoredFile:
        return StoredFile(
            id=row["id"],
            name=row["name"],
            size_bytes=row["size_bytes"],
            mime_type=row["mime_type"],
            telegram_channel_id=row["telegram_channel_id"],
            telegram_message_id=row["telegram_message_id"],
            telegram_file_id=row["telegram_file_id"],
            status=row["status"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repository.py -v`
Expected: PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/db.py app/repository.py tests/test_repository.py
git commit -m "feat: add sqlite file metadata repository"
```

### Task 3: Add the Telegram Bridge Contract and Storage Service

**Files:**
- Create: `app/telegram_bridge.py`
- Create: `app/service.py`
- Create: `tests/fakes.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
# tests/test_service.py
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

    stored = service.upload_bytes(
        filename="notes.txt",
        content=b"hello",
        mime_type="text/plain",
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
        service.upload_bytes(filename="bad.bin", content=b"broken", mime_type="application/octet-stream")
    except RuntimeError:
        pass

    files = repository.list_files()
    assert len(files) == 1
    assert files[0].status == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service.py -v`
Expected: FAIL with missing `StorageService` or `FakeTelegramStorage`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/telegram_bridge.py
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from telethon.sync import TelegramClient


@dataclass(frozen=True)
class UploadedTelegramFile:
    message_id: int
    file_id: str


@dataclass(frozen=True)
class DownloadedTelegramFile:
    filename: str
    content: bytes
    mime_type: str | None


class TelegramStorage(Protocol):
    def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        ...

    def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        ...


class TelethonStorage:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        message = self._client.send_file(entity=channel_id, file=BytesIO(content), file_name=filename, force_document=True)
        return UploadedTelegramFile(message_id=message.id, file_id=str(message.file.id))

    def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        message = self._client.get_messages(channel_id, ids=message_id)
        if message is None or message.file is None:
            raise FileNotFoundError(f"Telegram file not found for message {message_id}")
        content = self._client.download_media(message, file=bytes)
        if content is None:
            raise FileNotFoundError(f"Telegram content empty for message {message_id}")
        return DownloadedTelegramFile(filename=filename, content=content, mime_type=mime_type)
```

```python
# app/service.py
from app.repository import FileRepository
from app.telegram_bridge import DownloadedTelegramFile, TelegramStorage


class StorageService:
    def __init__(self, repository: FileRepository, telegram: TelegramStorage, channel_id: int) -> None:
        self._repository = repository
        self._telegram = telegram
        self._channel_id = channel_id

    def upload_bytes(self, *, filename: str, content: bytes, mime_type: str | None):
        stored = self._repository.create_uploading(name=filename, size_bytes=len(content), mime_type=mime_type)
        try:
            uploaded = self._telegram.upload(
                channel_id=self._channel_id,
                filename=filename,
                content=content,
                mime_type=mime_type,
            )
            self._repository.mark_ready(
                file_id=stored.id,
                telegram_channel_id=self._channel_id,
                telegram_message_id=uploaded.message_id,
                telegram_file_id=uploaded.file_id,
            )
        except Exception:
            self._repository.mark_failed(stored.id)
            raise
        return self._repository.get_file(stored.id)

    def list_files(self):
        return self._repository.list_files()

    def search_files(self, query: str):
        return self._repository.search_files(query)

    def get_file(self, file_id: int):
        return self._repository.get_file(file_id)

    def download_file(self, file_id: int) -> DownloadedTelegramFile:
        stored = self._repository.get_file(file_id)
        if stored is None or stored.telegram_message_id is None:
            raise FileNotFoundError(f"File {file_id} is unavailable")
        return self._telegram.download(
            channel_id=self._channel_id,
            message_id=stored.telegram_message_id,
            filename=stored.name,
            mime_type=stored.mime_type,
        )
```

```python
# tests/fakes.py
from dataclasses import dataclass

from app.telegram_bridge import DownloadedTelegramFile, UploadedTelegramFile


@dataclass(frozen=True)
class UploadStub:
    filename: str
    content: bytes
    mime_type: str | None


class FakeTelegramStorage:
    def __init__(self, *, message_id: int, file_id: str, should_fail: bool = False) -> None:
        self._message_id = message_id
        self._file_id = file_id
        self._should_fail = should_fail
        self.uploads: list[UploadStub] = []

    def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        if self._should_fail:
            raise RuntimeError("telegram upload failed")
        self.uploads.append(UploadStub(filename=filename, content=content, mime_type=mime_type))
        return UploadedTelegramFile(message_id=self._message_id, file_id=self._file_id)

    def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        return DownloadedTelegramFile(filename=filename, content=b"downloaded", mime_type=mime_type)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service.py -v`
Expected: PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/telegram_bridge.py app/service.py tests/fakes.py tests/test_service.py
git commit -m "feat: add telegram storage service"
```

### Task 4: Build the FastAPI App, JSON API, and Minimal UI

**Files:**
- Create: `app/main.py`
- Create: `app/templates/base.html`
- Create: `app/templates/index.html`
- Create: `app/templates/file_detail.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Create: `tests/conftest.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing web tests**

```python
# tests/test_web.py
from fastapi.testclient import TestClient


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -v`
Expected: FAIL with missing `app_client` fixture or missing FastAPI routes

- [ ] **Step 3: Write the minimal implementation**

```python
# tests/conftest.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect_db, ensure_schema
from app.main import build_app
from app.repository import FileRepository
from app.service import StorageService
from tests.fakes import FakeTelegramStorage


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    telegram = FakeTelegramStorage(message_id=10, file_id="tg-10")
    service = StorageService(repository, telegram, channel_id=-10055)
    created = repository.create_uploading(name="seed.txt", size_bytes=4, mime_type="text/plain")
    repository.mark_ready(file_id=created.id, telegram_channel_id=-10055, telegram_message_id=10, telegram_file_id="tg-10")
    app = build_app(service)
    return TestClient(app)
```

```python
# app/main.py
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.service import StorageService


def serialize_file(stored) -> dict:
    return {
        "id": stored.id,
        "name": stored.name,
        "size_bytes": stored.size_bytes,
        "mime_type": stored.mime_type,
        "status": stored.status,
        "uploaded_at": stored.uploaded_at.isoformat(),
    }


def build_app(service: StorageService) -> FastAPI:
    app = FastAPI()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "files": [serialize_file(item) for item in service.list_files()]},
        )

    @app.get("/view/files/{file_id}", response_class=HTMLResponse)
    def detail_page(request: Request, file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return templates.TemplateResponse(
            "file_detail.html",
            {"request": request, "file": serialize_file(stored)},
        )

    @app.post("/files/upload", status_code=201)
    async def upload(file: UploadFile = File(...)):
        stored = service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
        )
        return JSONResponse(serialize_file(stored), status_code=201)

    @app.get("/files")
    def list_files():
        return [serialize_file(item) for item in service.list_files()]

    @app.get("/files/search")
    def search_files(q: str = Query("")):
        return [serialize_file(item) for item in service.search_files(q)]

    @app.get("/files/{file_id}")
    def file_detail(file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return serialize_file(stored)

    @app.get("/files/{file_id}/download")
    def download_file(file_id: int):
        downloaded = service.download_file(file_id)
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{downloaded.filename}"'},
        )

    return app
```

```html
<!-- app/templates/base.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Telegram Storage</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    {% block body %}{% endblock %}
    <script src="/static/app.js"></script>
  </body>
  </html>
```

```html
<!-- app/templates/index.html -->
{% extends "base.html" %}
{% block body %}
<div class="app-shell">
  <aside class="sidebar">
    <h1>Storage</h1>
    <nav>
      <a href="#">All Files</a>
      <a href="#">Recent</a>
      <a href="#">Uploads</a>
    </nav>
  </aside>
  <main class="content">
    <header class="toolbar">
      <input id="search-input" type="search" placeholder="Search files">
      <form id="upload-form">
        <input id="file-input" name="file" type="file" required>
        <button type="submit">Upload</button>
      </form>
    </header>
    <section>
      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Size</th><th>Status</th></tr>
        </thead>
        <tbody id="file-table-body">
          {% for file in files %}
          <tr>
            <td><a href="/view/files/{{ file.id }}">{{ file.name }}</a></td>
            <td>{{ file.mime_type or "unknown" }}</td>
            <td>{{ file.size_bytes }}</td>
            <td>{{ file.status }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>
  </main>
</div>
{% endblock %}
```

```html
<!-- app/templates/file_detail.html -->
{% extends "base.html" %}
{% block body %}
<main class="detail-page">
  <h1>{{ file.name }}</h1>
  <p>Status: {{ file.status }}</p>
  <p>Type: {{ file.mime_type or "unknown" }}</p>
  <p>Size: {{ file.size_bytes }} bytes</p>
  <a href="/files/{{ file.id }}/download">Download</a>
</main>
{% endblock %}
```

```css
/* app/static/styles.css */
body {
  margin: 0;
  font-family: Inter, Arial, sans-serif;
  background: #f4f6fb;
  color: #162033;
}

.app-shell {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}

.sidebar {
  padding: 24px;
  background: #0f172a;
  color: white;
}

.sidebar a {
  display: block;
  margin: 12px 0;
  color: #cbd5e1;
  text-decoration: none;
}

.content {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border-radius: 12px;
  overflow: hidden;
}

th, td {
  padding: 14px 16px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
}
```

```javascript
// app/static/app.js
async function refreshFiles(query = "") {
  const url = query ? `/files/search?q=${encodeURIComponent(query)}` : "/files";
  const response = await fetch(url);
  const files = await response.json();
  const tbody = document.getElementById("file-table-body");
  if (!tbody) return;
  tbody.innerHTML = files.map((file) => `
    <tr>
      <td>${file.name}</td>
      <td>${file.mime_type ?? "unknown"}</td>
      <td>${file.size_bytes}</td>
      <td>${file.status}</td>
    </tr>
  `).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("search-input");
  const form = document.getElementById("upload-form");
  const input = document.getElementById("file-input");

  search?.addEventListener("input", (event) => {
    refreshFiles(event.target.value);
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!input?.files?.length) return;
    const data = new FormData();
    data.append("file", input.files[0]);
    await fetch("/files/upload", { method: "POST", body: data });
    input.value = "";
    refreshFiles();
  });
});
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web.py -v`
Expected: PASS with `4 passed`

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/templates/base.html app/templates/index.html app/templates/file_detail.html app/static/styles.css app/static/app.js tests/conftest.py tests/test_web.py
git commit -m "feat: add storage dashboard and api routes"
```

### Task 5: Wire the Production App Entry Point and Document Local Setup

**Files:**
- Modify: `app/main.py`
- Create: `app/asgi.py`
- Create: `README.md`

- [ ] **Step 1: Write the failing startup test**

```python
# tests/test_web.py
from app.main import create_app
from tests.fakes import FakeTelegramStorage


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
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_web.py::test_create_app_builds_routes_from_environment -v`
Expected: FAIL with `cannot import name 'create_app'` or unexpected `create_app()` signature mismatch

- [ ] **Step 3: Write the minimal implementation**

```python
# app/main.py
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon.sync import TelegramClient

from app.config import load_settings
from app.db import connect_db, ensure_schema
from app.repository import FileRepository
from app.service import StorageService
from app.telegram_bridge import TelegramStorage, TelethonStorage


def serialize_file(stored) -> dict:
    return {
        "id": stored.id,
        "name": stored.name,
        "size_bytes": stored.size_bytes,
        "mime_type": stored.mime_type,
        "status": stored.status,
        "uploaded_at": stored.uploaded_at.isoformat(),
    }


def build_app(service: StorageService) -> FastAPI:
    app = FastAPI()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"files": [serialize_file(item) for item in service.list_files()]},
        )

    @app.get("/view/files/{file_id}", response_class=HTMLResponse)
    def detail_page(request: Request, file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return templates.TemplateResponse(
            request,
            "file_detail.html",
            {"file": serialize_file(stored)},
        )

    @app.post("/files/upload", status_code=201)
    async def upload(file: UploadFile = File(...)):
        stored = service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
        )
        return JSONResponse(serialize_file(stored), status_code=201)

    @app.get("/files")
    def list_files():
        return [serialize_file(item) for item in service.list_files()]

    @app.get("/files/search")
    def search_files(q: str = Query("")):
        return [serialize_file(item) for item in service.search_files(q)]

    @app.get("/files/{file_id}")
    def file_detail(file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return serialize_file(stored)

    @app.get("/files/{file_id}/download")
    def download_file(file_id: int):
        downloaded = service.download_file(file_id)
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{downloaded.filename}"'},
        )

    return app


def create_app(telegram_storage: TelegramStorage | None = None) -> FastAPI:
    settings = load_settings()
    connection = connect_db(settings.database_path)
    ensure_schema(connection)
    if telegram_storage is None:
        client = TelegramClient(str(settings.telegram_session), settings.telegram_api_id, settings.telegram_api_hash)
        client.start()
        telegram_storage = TelethonStorage(client)
    service = StorageService(FileRepository(connection), telegram_storage, channel_id=settings.telegram_channel_id)
    return build_app(service)
```

```python
# app/asgi.py
from app.main import create_app


app = create_app()
```

```markdown
# README.md

## TGS3

### Local setup

1. Create a virtual environment.
2. Install dependencies with `pip install -e .[dev]`.
3. Copy `.env.example` values into your shell environment.
4. Start the app with `uvicorn app.asgi:app --reload`.
5. Open `http://127.0.0.1:8000`.

### Required Telegram preparation

1. Create a private Telegram channel.
2. Use your Telegram API ID and API hash.
3. Set `TELEGRAM_CHANNEL_ID` to the target channel.
4. On first run, complete the Telethon login flow so the session file is created.

### MVP behavior

- Upload a file from the dashboard.
- Files are sent to Telegram and indexed in SQLite.
- Search filters the local SQLite index.
- Download pulls the file back through the backend.
```

- [ ] **Step 4: Run focused and full tests**

Run: `pytest tests/test_web.py::test_create_app_builds_routes_from_environment -v`
Expected: PASS with `1 passed`

Run: `pytest tests -v`
Expected: PASS with all config, repository, service, and web tests green

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/asgi.py README.md tests/test_web.py
git commit -m "feat: wire production app bootstrap"
```

## Spec Coverage Check

- Upload flow: Task 3 and Task 4
- Browse flow: Task 2 and Task 4
- Search flow: Task 2 and Task 4
- Download flow: Task 3 and Task 4
- Local config and startup: Task 1 and Task 5
- Error handling for failed uploads and missing Telegram objects: Task 3 and Task 4

## Placeholder Scan

- No `TBD`, `TODO`, or deferred implementation markers remain.
- All routes, modules, and tests referenced in later tasks are defined earlier in the plan.

## Type Consistency Check

- `StorageService`, `FileRepository`, `TelethonStorage`, `UploadedTelegramFile`, and `DownloadedTelegramFile` use the same names across all tasks.
- Route paths are consistent across tests and implementation: `/`, `/view/files/{file_id}`, `/files`, `/files/search`, `/files/upload`, `/files/{file_id}`, `/files/{file_id}/download`.
