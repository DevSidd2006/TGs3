# Folders & Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google-Drive-style nested folders to TeleVault: create/rename/delete folders, browse via a sidebar tree and breadcrumbs, upload into a chosen folder, and move files between folders.

**Architecture:** A new `folders` table uses a self-referencing `parent_id` (NULL = root) for unlimited nesting. Files gain a nullable `folder_id` foreign key. `FileRepository` gains folder methods; `StorageService` delegates them; FastAPI routes expose a folder-tree JSON plus CRUD; the Jinja + vanilla-JS frontend renders the tree in the sidebar, a clickable breadcrumb, folder rows above file rows, an upload destination picker, and a move action.

**Tech Stack:** Python 3.13, FastAPI, Starlette, Jinja2, SQLite (`sqlite3` stdlib), vanilla JS, existing TeleVault dark theme. Tests via pytest with `TestClient`.

**Spec:** `docs/superpowers/specs/2026-08-11-folders-design.md`

---

## File Structure

- `app/db.py` — add `folders` table + `files.folder_id` column to `ensure_schema` (idempotent migration).
- `app/models.py` — add `Folder` dataclass.
- `app/repository.py` — add folder CRUD, `move_file`, `get_breadcrumb`, `list_files(folder_id=None)`. Existing `FileRepository` name retained.
- `app/service.py` — add folder passthrough methods + `list_files(folder_id=None)`.
- `app/main.py` — add `serialize_folder`, folder routes, `folder_id` params on upload/list/index.
- `app/templates/index.html` — sidebar folder tree, breadcrumb, folder rows, upload folder select, move modal.
- `app/templates/base.html` — bump static asset version.
- `app/static/app.js` — `loadFolderTree`, `navigate`, folder modal, move, folder rows in `renderFileList`.
- `app/static/styles.css` — styles for tree, breadcrumb, folder rows, modal.
- `tests/test_repository.py` — folder repository tests.
- `tests/test_service.py` — folder service tests.
- `tests/test_web.py` — folder route tests.
- `tests/conftest.py` — unchanged (schema is extended via `ensure_schema`).

---

### Task 1: Schema and Folder Model

**Files:**
- Modify: `app/db.py`
- Modify: `app/models.py`
- Test: `tests/test_repository.py` (add a migration test here)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repository.py`:

```python
def test_schema_has_folders_table_and_folder_id_column(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "folders" in tables
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    assert "folder_id" in columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_repository.py::test_schema_has_folders_table_and_folder_id_column -q`
Expected: FAIL (`folders` not in tables)

- [ ] **Step 3: Implement schema**

In `app/db.py`, replace the `ensure_schema` body with:

```python
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES folders(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    file_columns = {row["name"] for row in connection.execute("PRAGMA table_info(files)")}
    if "folder_id" not in file_columns:
        connection.execute("ALTER TABLE files ADD COLUMN folder_id INTEGER REFERENCES folders(id)")
    connection.commit()
```

In `app/models.py`, add after the `StoredFile` class:

```python
@dataclass(frozen=True)
class Folder:
    id: int
    name: str
    parent_id: int | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_repository.py::test_schema_has_folders_table_and_folder_id_column -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/models.py tests/test_repository.py
git commit -m "feat: add folders schema and Folder model"
```

---

### Task 2: Folder Repository Methods

**Files:**
- Modify: `app/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repository.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_repository.py::TestFolderRepository -q`
Expected: FAIL (methods missing)

- [ ] **Step 3: Implement repository methods**

In `app/repository.py`, import `Folder` from models, and add to `FileRepository`:

```python
    def create_folder(self, *, name: str, parent_id: int | None) -> Folder:
        name = name.strip()
        if not name:
            raise ValueError("folder name must not be empty")
        if parent_id is not None and self.get_folder(parent_id) is None:
            raise ValueError(f"parent folder {parent_id} not found")
        cursor = self._connection.execute(
            "INSERT INTO folders (name, parent_id) VALUES (?, ?)",
            (name, parent_id),
        )
        self._connection.commit()
        folder = self.get_folder(cursor.lastrowid)
        assert folder is not None
        return folder

    def rename_folder(self, folder_id: int, name: str) -> Folder:
        name = name.strip()
        if not name:
            raise ValueError("folder name must not be empty")
        folder = self.get_folder(folder_id)
        if folder is None:
            raise ValueError(f"folder {folder_id} not found")
        self._connection.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
        self._connection.commit()
        updated = self.get_folder(folder_id)
        assert updated is not None
        return updated

    def delete_folder(self, folder_id: int) -> None:
        direct_children = self._connection.execute(
            "SELECT COUNT(*) AS count FROM folders WHERE parent_id = ?", (folder_id,)
        ).fetchone()
        file_count = self._connection.execute(
            "SELECT COUNT(*) AS count FROM files WHERE folder_id = ?", (folder_id,)
        ).fetchone()
        if direct_children["count"] > 0 or file_count["count"] > 0:
            raise ValueError(f"folder {folder_id} is not empty")
        self._connection.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self._connection.commit()

    def get_folder(self, folder_id: int) -> Folder | None:
        row = self._connection.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return None
        return Folder(id=row["id"], name=row["name"], parent_id=row["parent_id"])

    def list_folders(self) -> list[Folder]:
        rows = self._connection.execute(
            "SELECT * FROM folders ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [Folder(id=row["id"], name=row["name"], parent_id=row["parent_id"]) for row in rows]

    def move_file(self, *, file_id: int, folder_id: int | None) -> StoredFile:
        if self.get_file(file_id) is None:
            raise ValueError(f"file {file_id} not found")
        if folder_id is not None and self.get_folder(folder_id) is None:
            raise ValueError(f"folder {folder_id} not found")
        self._connection.execute("UPDATE files SET folder_id = ? WHERE id = ?", (folder_id, file_id))
        self._connection.commit()
        moved = self.get_file(file_id)
        assert moved is not None
        return moved

    def get_breadcrumb(self, folder_id: int) -> list[Folder]:
        chain: list[Folder] = []
        current = folder_id
        seen: set[int] = set()
        while current is not None:
            if current in seen:
                raise ValueError("folder cycle detected")
            seen.add(current)
            folder = self.get_folder(current)
            if folder is None:
                raise ValueError(f"folder {current} not found")
            chain.append(folder)
            current = folder.parent_id
        chain.reverse()
        return chain
```

- [ ] **Step 4: Modify `list_files` to accept `folder_id`**

Replace the existing `list_files` method:

```python
    def list_files(self, folder_id: int | None = None) -> list[StoredFile]:
        if folder_id is None:
            rows = self._connection.execute(
                "SELECT * FROM files WHERE folder_id IS NULL ORDER BY uploaded_at DESC, id DESC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM files WHERE folder_id = ? ORDER BY uploaded_at DESC, id DESC",
                (folder_id,),
            ).fetchall()
        return [self._row_to_model(row) for row in rows]
```

Also add the `from app.models import Folder` import alongside the existing `StoredFile` import.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_repository.py -q`
Expected: PASS (all existing + new tests)

- [ ] **Step 6: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: add folder repository methods and folder filtering"
```

---

### Task 3: Service Passthroughs

**Files:**
- Modify: `app/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_service.py::test_service_folder_delegation -q`
Expected: FAIL (methods missing)

- [ ] **Step 3: Implement service methods**

In `app/service.py`, update the signature of `list_files` and add the folder methods:

```python
    def list_files(self, folder_id: int | None = None):
        return self._repository.list_files(folder_id)

    def create_folder(self, *, name: str, parent_id: int | None):
        return self._repository.create_folder(name=name, parent_id=parent_id)

    def rename_folder(self, folder_id: int, name: str):
        return self._repository.rename_folder(folder_id, name)

    def delete_folder(self, folder_id: int) -> None:
        return self._repository.delete_folder(folder_id)

    def get_folder(self, folder_id: int):
        return self._repository.get_folder(folder_id)

    def list_folders(self):
        return self._repository.list_folders()

    def move_file(self, *, file_id: int, folder_id: int | None):
        return self._repository.move_file(file_id=file_id, folder_id=folder_id)

    def get_breadcrumb(self, folder_id: int):
        return self._repository.get_breadcrumb(folder_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/service.py tests/test_service.py
git commit -m "feat: delegate folder operations through StorageService"
```

---

### Task 4: Folder Routes

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_web.py -q`
Expected: FAIL (routes missing)

- [ ] **Step 3: Implement routes**

In `app/main.py`, add a `serialize_folder` helper and the folder routes.

Add after `serialize_file`:

```python
def serialize_folder(folder) -> dict:
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


def build_folder_tree(folders: list) -> list[dict]:
    children: dict[int | None, list[dict]] = {f.id: [] for f in folders}
    roots: list[dict] = []
    by_id = {f.id: f for f in folders}
    for folder in folders:
        node = {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id, "children": children[folder.id]}
        if folder.parent_id is None:
            roots.append(node)
        elif folder.parent_id in by_id:
            children[folder.parent_id].append(node)
        else:
            roots.append(node)
    return roots
```

Change the `index` route to accept `folder_id` and pass breadcrumb + tree context:

```python
    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, folder_id: int | None = None):
        files = service.list_files(folder_id=folder_id)
        breadcrumb = service.get_breadcrumb(folder_id) if folder_id is not None else []
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "files": [serialize_file(item) for item in files],
                "folders": service.list_folders(),
                "folder_tree": build_folder_tree(service.list_folders()),
                "breadcrumb": [serialize_folder(item) for item in breadcrumb],
                "current_folder_id": folder_id,
            },
        )
```

Change the upload route to accept `folder_id`:

```python
    @app.post("/files/upload", status_code=201)
    async def upload(file: UploadFile = File(...), folder_id: int | None = None):
        stored = await service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
            folder_id=folder_id,
        )
        return JSONResponse(serialize_file(stored), status_code=201)
```

Change the `list_files` route to accept `folder_id`:

```python
    @app.get("/files")
    def list_files(folder_id: int | None = None):
        return [serialize_file(item) for item in service.list_files(folder_id=folder_id)]
```

Add the folder routes before the `@app.get("/files/{file_id}")` route:

```python
    @app.get("/folders")
    def folder_tree():
        return build_folder_tree(service.list_folders())

    @app.post("/folders", status_code=201)
    def create_folder(payload: dict):
        try:
            folder = service.create_folder(name=payload.get("name"), parent_id=payload.get("parent_id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(serialize_folder(folder), status_code=201)

    @app.patch("/folders/{folder_id}")
    def rename_folder(folder_id: int, payload: dict):
        if service.get_folder(folder_id) is None:
            raise HTTPException(status_code=404, detail=f"folder {folder_id} not found")
        try:
            folder = service.rename_folder(folder_id, payload.get("name"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return serialize_folder(folder)

    @app.delete("/folders/{folder_id}", status_code=204)
    def delete_folder(folder_id: int):
        try:
            service.delete_folder(folder_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/files/{file_id}/move")
    def move_file(file_id: int, payload: dict):
        try:
            stored = service.move_file(file_id=file_id, folder_id=payload.get("folder_id"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)
```

Update `serialize_file` to include `folder_id`:

```python
def serialize_file(stored) -> dict:
    return {
        "id": stored.id,
        "name": stored.name,
        "size_bytes": stored.size_bytes,
        "mime_type": stored.mime_type,
        "status": stored.status,
        "uploaded_at": stored.uploaded_at.isoformat(),
        "folder_id": getattr(stored, "folder_id", None),
    }
```

Add the `folder_id` param to `StorageService.upload_bytes` in `app/service.py`:

```python
    async def upload_bytes(self, *, filename: str, content: bytes, mime_type: str | None, folder_id: int | None = None):
        stored = self._repository.create_uploading(name=filename, size_bytes=len(content), mime_type=mime_type)
        if folder_id is not None:
            self._repository.move_file(file_id=stored.id, folder_id=folder_id)
        try:
            uploaded = await self._telegram.upload(
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_web.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/service.py tests/test_web.py
git commit -m "feat: add folder CRUD, move, and folder-scoped routes"
```

---

### Task 5: Sidebar Folder Tree and Folder Modals

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Modify: `app/templates/base.html`

- [ ] **Step 1: Replace the static sidebar nav with a folder tree**

In `app/templates/index.html`, replace the `<ul class="nav-list">...</ul>` block with a root "All Files" entry plus a tree container:

```html
      <ul class="nav-list">
        <li class="nav-item active" data-folder-root>
          <a href="/" data-nav="root"><i class="ph-bold ph-house"></i> All Files</a>
        </li>
      </ul>
      <div id="folder-tree" class="folder-tree" data-tree></div>
      <button id="btn-new-folder" class="btn-secondary sidebar-new-folder">
        <i class="ph-bold ph-folder-plus"></i> New Folder
      </button>
```

In `app/templates/index.html`, update the breadcrumb block to render server-side crumbs:

```html
        <div class="breadcrumb-title" id="breadcrumb">
          <a href="/" class="crumb-link">All Files</a>
          {% for crumb in breadcrumb %}
            <span class="crumb-sep">&rsaquo;</span>
            <a href="/?folder_id={{ crumb.id }}" class="crumb-link">{{ crumb.name }}</a>
          {% endfor %}
        </div>
```

In `app/templates/index.html`, add the folder modal markup just before `{% endblock %}` (next to the preview overlay):

```html
<!-- Folder Modal -->
<div id="folder-modal" class="preview-overlay" hidden>
  <div class="modal-card">
    <div class="preview-header">
      <span class="preview-name" id="folder-modal-title">New Folder</span>
      <button id="folder-modal-close" class="icon-action-btn" title="Close"><i class="ph-bold ph-x"></i></button>
    </div>
    <div class="modal-body">
      <input id="folder-modal-name" class="search-input" type="text" placeholder="Folder name">
      <div class="modal-actions">
        <button id="folder-modal-cancel" class="btn-secondary">Cancel</button>
        <button id="folder-modal-save" class="btn-secondary btn-primary-solid">Save</button>
      </div>
    </div>
  </div>
</div>

<!-- Move Modal -->
<div id="move-modal" class="preview-overlay" hidden>
  <div class="modal-card">
    <div class="preview-header">
      <span class="preview-name">Move to folder</span>
      <button id="move-modal-close" class="icon-action-btn" title="Close"><i class="ph-bold ph-x"></i></button>
    </div>
    <div class="modal-body">
      <select id="move-modal-folder" class="search-input"></select>
      <div class="modal-actions">
        <button id="move-modal-cancel" class="btn-secondary">Cancel</button>
        <button id="move-modal-save" class="btn-secondary btn-primary-solid">Move</button>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Add folder tree and modal JS**

Append to `app/static/app.js`:

```javascript
let moveFileId = null;
let folderModalMode = null; // 'create' | 'rename'
let folderModalTarget = null;

function buildTreeHtml(nodes, depth = 0) {
  return nodes.map((node) => `
    <div class="tree-node" style="--depth: ${depth}">
      <div class="tree-row">
        <button type="button" class="tree-folder" data-nav="${node.id}" title="${node.name}">
          <i class="ph-bold ph-folder"></i>
          <span>${node.name}</span>
        </button>
        <button type="button" class="icon-action-btn tree-menu" data-menu="${node.id}" title="Options">
          <i class="ph-bold ph-dots-three-vertical"></i>
        </button>
      </div>
      ${node.children && node.children.length ? buildTreeHtml(node.children, depth + 1) : ''}
    </div>
  `).join("");
}

async function loadFolderTree() {
  try {
    const res = await fetch("/folders");
    const tree = await res.json();
    const container = document.getElementById("folder-tree");
    if (!container) return;
    container.innerHTML = buildTreeHtml(tree);
  } catch (err) {
    console.error("Error loading folder tree:", err);
  }
}

function navigate(folderId) {
  const url = folderId ? `/?folder_id=${folderId}` : "/";
  window.location.href = url;
}

function openFolderModal(mode, folderId) {
  folderModalMode = mode;
  folderModalTarget = folderId ?? null;
  document.getElementById("folder-modal-title").textContent = mode === "create" ? "New Folder" : "Rename Folder";
  document.getElementById("folder-modal-name").value = mode === "create" ? "" : (document.querySelector(`[data-menu="${folderId}"]`)?.closest(".tree-row")?.querySelector("span")?.textContent ?? "");
  document.getElementById("folder-modal").hidden = false;
}

function closeFolderModal() {
  document.getElementById("folder-modal").hidden = true;
  folderModalMode = null;
  folderModalTarget = null;
}

async function saveFolder() {
  const name = document.getElementById("folder-modal-name").value.trim();
  if (!name) return;
  const url = folderModalMode === "rename" ? `/folders/${folderModalTarget}` : "/folders";
  const method = folderModalMode === "rename" ? "PATCH" : "POST";
  const body = folderModalMode === "rename" ? { name } : { name, parent_id: folderModalTarget };
  const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (res.ok) {
    closeFolderModal();
    await loadFolderTree();
    await refreshFiles();
  } else {
    const err = await res.json();
    alert(err.detail || "Failed to save folder.");
  }
}

function openMoveModal(fileId) {
  moveFileId = fileId;
  const select = document.getElementById("move-modal-folder");
  select.innerHTML = '<option value="">All Files</option>' + folderOptionsHtml();
  document.getElementById("move-modal").hidden = false;
}

function folderOptionsHtml() {
  const container = document.getElementById("folder-tree");
  if (!container) return "";
  return Array.from(container.querySelectorAll(".tree-folder")).map((btn) => {
    const name = btn.querySelector("span").textContent;
    const depth = parseInt(btn.closest(".tree-row").parentElement.style.getPropertyValue("--depth") || "0", 10);
    return `<option value="${btn.dataset.nav}">${"&nbsp;".repeat(depth * 2)}${name}</option>`;
  }).join("");
}

async function saveMove() {
  if (!moveFileId) return;
  const folderId = document.getElementById("move-modal-folder").value || null;
  const res = await fetch(`/files/${moveFileId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_id: folderId }),
  });
  if (res.ok) {
    document.getElementById("move-modal").hidden = true;
    moveFileId = null;
    await refreshFiles();
  } else {
    const err = await res.json();
    alert(err.detail || "Failed to move file.");
  }
}
```

Wire these up in the existing `DOMContentLoaded` handler (add before the closing `});`):

```javascript
  document.getElementById("btn-new-folder")?.addEventListener("click", () => openFolderModal("create", null));
  document.getElementById("folder-modal-close")?.addEventListener("click", closeFolderModal);
  document.getElementById("folder-modal-cancel")?.addEventListener("click", closeFolderModal);
  document.getElementById("folder-modal-save")?.addEventListener("click", saveFolder);
  document.getElementById("move-modal-close")?.addEventListener("click", () => { document.getElementById("move-modal").hidden = true; moveFileId = null; });
  document.getElementById("move-modal-cancel")?.addEventListener("click", () => { document.getElementById("move-modal").hidden = true; moveFileId = null; });
  document.getElementById("move-modal-save")?.addEventListener("click", saveMove);

  const folderTree = document.getElementById("folder-tree");
  folderTree?.addEventListener("click", (e) => {
    const nav = e.target.closest(".tree-folder");
    if (nav) return navigate(nav.dataset.nav);
    const menu = e.target.closest(".tree-menu");
    if (menu) {
      const id = menu.dataset.menu;
      const action = window.prompt("Folder options: type 'new' for subfolder, 'rename', or 'delete'");
      if (action === "new") openFolderModal("create", id);
      else if (action === "rename") openFolderModal("rename", id);
      else if (action === "delete") {
        if (window.confirm("Delete this folder? Only empty folders can be deleted.")) {
          fetch(`/folders/${id}`, { method: "DELETE" }).then((res) => {
            if (res.status === 204) { loadFolderTree(); refreshFiles(); }
            else if (res.status === 409) alert("Folder is not empty.");
          });
        }
      }
    }
  });

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => { e.preventDefault(); navigate(null); });
  });

  await loadFolderTree();
```

Note: change the `DOMContentLoaded` callback from `() => {` to `async () => {` so `await loadFolderTree()` works.

- [ ] **Step 3: Update `renderFileList` to show folder rows and Move/Delete actions**

In `app/static/app.js`, update the actions cell in `renderFileList` to include a Move button:

```javascript
        <td>
          <div class="table-actions">
            <button type="button" class="link-action preview-trigger" data-id="${file.id}" data-mime="${file.mime_type || ''}" data-name="${file.name}" style="cursor: pointer; background: none; border: none;">Preview</button>
            <button type="button" class="link-action move-trigger" data-id="${file.id}" style="cursor: pointer; background: none; border: none;">Move</button>
            <a href="/files/${file.id}/download" class="link-action">Download</a>
            <button class="icon-action-btn"><i class="ph-bold ph-dots-three-vertical"></i></button>
          </div>
        </td>
```

And add a handler in the existing table click listener (after the preview handler):

```javascript
    const move = e.target.closest(".move-trigger");
    if (move) return openMoveModal(move.dataset.id);
```

- [ ] **Step 4: Add CSS**

Append to `app/static/styles.css`:

```css
/* Folder Tree */
.folder-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.tree-node {
  margin-left: calc(var(--depth) * 14px);
}

.tree-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

.tree-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.tree-folder {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 0;
  flex: 1;
  text-align: left;
  overflow: hidden;
}

.tree-folder i {
  color: var(--accent-cyan);
  font-size: 15px;
  flex-shrink: 0;
}

.tree-folder span {
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}

.tree-folder:hover {
  color: var(--text-main);
}

.tree-menu {
  font-size: 14px;
  opacity: 0;
  transition: var(--transition);
}

.tree-row:hover .tree-menu {
  opacity: 1;
}

.sidebar-new-folder {
  margin-top: 12px;
  width: 100%;
}

/* Breadcrumb */
.crumb-link {
  color: var(--text-muted);
  text-decoration: none;
  font-weight: 500;
  transition: var(--transition);
}

.crumb-link:hover {
  color: var(--accent-cyan);
}

.crumb-sep {
  color: var(--text-subtle);
}

/* Modal */
.modal-card {
  width: 100%;
  max-width: 400px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: 0 30px 60px -12px rgba(0, 0, 0, 0.7);
  overflow: hidden;
}

.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-primary-solid {
  background: var(--primary);
  border-color: var(--primary);
  color: white;
}

.btn-primary-solid:hover {
  background: var(--primary-hover);
}
```

- [ ] **Step 5: Bump static asset version**

In `app/templates/base.html`, change both `?v=3` to `?v=4` (for `styles.css` and `app.js`).

- [ ] **Step 6: Manual smoke test**

Run: `.venv/bin/pytest tests -q`
Expected: all tests PASS.

Then start the server and verify in a browser at http://127.0.0.1:8000:
- "New Folder" button creates a folder; it appears in the sidebar tree.
- Clicking a folder in the tree navigates to `/?folder_id=X`.
- The breadcrumb shows `All Files › <folder name>`.
- Folder's `⋯` menu: "new" creates a subfolder, "rename" renames, "delete" works on empty folders.
- Upload with the destination folder selected stores the file in that folder.
- Move action on a file moves it into a chosen folder.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/templates/base.html app/static/app.js app/static/styles.css
git commit -m "feat: folder tree sidebar, breadcrumbs, and move/create/rename/delete UI"
```

---

## Self-Review

**Spec coverage:**
- Folders table + `folder_id` on files → Task 1 ✓
- Create/rename/delete (empty only) → Task 2, Task 4 ✓
- Unlimited nesting → `parent_id` self-reference, tree building → Task 2, Task 5 ✓
- Sidebar tree → Task 5 ✓
- Breadcrumb → Task 4 (server breadcrumb), Task 5 (UI) ✓
- Upload into folder → Task 4 (route + service), Task 5 (UI select via navigate-to-folder) ✓
- Move files → Task 2, Task 4, Task 5 ✓
- Search global (unchanged) ✓
- Tests: repository (Task 2), service (Task 3), web (Task 4) ✓

**Placeholder scan:** No TBD/TODO; all steps contain concrete code.

**Type consistency:** `serialize_file` now includes `folder_id`; `Folder` model used consistently across repository/service/routes; `build_folder_tree` produces `children` lists used by `app.js` `buildTreeHtml`. `StorageService.upload_bytes` accepts `folder_id` and `move_file` handles `None` for root.
