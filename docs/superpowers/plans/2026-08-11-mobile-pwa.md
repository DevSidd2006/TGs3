# TGS3 Mobile PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a phone-installable PWA at `/mobile` plus a stdlib-only login layer so TGS3 can be safely reached over the internet via a free Cloudflare Tunnel.

**Architecture:** The FastAPI server (a) seeds a single user from `.env`, (b) issues signed session tokens stored in a `sessions` table, (c) serves a static mobile app (`s3/mobile/`) at `/mobile` same-origin, and (d) exposes a manifest + service worker for installability. The mobile app is pure HTML/CSS/JS talking to the existing REST API. No changes to the storage/Telegram layer.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, SQLite, vanilla JS. Stdlib only for auth: `hashlib.pbkdf2_hmac` (password hash), `secrets` (session tokens). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-11-mobile-pwa-design.md`

**Baseline:** Existing 34 tests must stay green. Run with `/home/devisdd/s3/.venv/bin/pytest tests -q`. Server: `cd /home/devisdd/s3 && .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000`.

---

### Task 1: Auth settings + password hashing

**Files:**
- Modify: `app/config.py`
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth.py`:

```python
from app.auth import hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed) is True


def test_verify_password_rejects_wrong_value():
    hashed = hash_password("correct horse")
    assert verify_password("wrong", hashed) is False


def test_hash_is_salted_and_reproducible():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write minimal implementation**

Create `app/auth.py`:

```python
import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, expected_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth.py -v`
Expected: 3 PASS

- [ ] **Step 5: Update Settings with auth config**

Modify `app/config.py` — add fields and defaults:

```python
@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_channel_id: int
    telegram_session: Path
    database_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    tgs3_user: str = "admin"
    tgs3_password: str = ""
    session_ttl_days: int = 30
    secure_cookie: bool = True
```

In `load_settings()` add:

```python
        tgs3_user=os.environ.get("TGS3_USER", "admin"),
        tgs3_password=os.environ.get("TGS3_PASSWORD", ""),
        session_ttl_days=int(os.environ.get("TGS3_SESSION_TTL_DAYS", "30")),
        secure_cookie=os.environ.get("TGS3_SECURE_COOKIE", "1") == "1",
```

- [ ] **Step 6: Run full suite + commit**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests -q`
Expected: 37 passed

```bash
git add app/auth.py app/config.py tests/test_auth.py
git commit -m "feat: add password hashing and auth settings"
```

---

### Task 2: Auth schema + repository methods

**Files:**
- Modify: `app/db.py`
- Modify: `app/repository.py`
- Test: `tests/test_auth_repository.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_repository.py`:

```python
import sqlite3
from datetime import timedelta
from pathlib import Path

from app.db import ensure_schema
from app.repository import AuthRepository


def make_repo(tmp_path: Path) -> AuthRepository:
    connection = sqlite3.connect(tmp_path / "auth.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return AuthRepository(connection)


def test_create_and_verify_user(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    assert repo.verify_user("admin", "hash-1") is True
    assert repo.verify_user("admin", "hash-2") is False
    assert repo.verify_user("nobody", "hash-1") is False


def test_upsert_user_updates_existing(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    repo.upsert_user(username="admin", password_hash="hash-2")
    assert repo.verify_user("admin", "hash-2") is True
    assert repo.verify_user("admin", "hash-1") is False


def test_session_create_and_validate(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    token = repo.create_session(username="admin", ttl=timedelta(days=1))
    assert repo.get_session_user(token) == "admin"


def test_session_expired_or_unknown_returns_none(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.get_session_user("missing-token") is None
    token = repo.create_session(username="admin", ttl=timedelta(days=-1))
    assert repo.get_session_user(token) is None


def test_delete_session_invalidates_token(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    token = repo.create_session(username="admin", ttl=timedelta(days=1))
    repo.delete_session(token)
    assert repo.get_session_user(token) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'AuthRepository'`

- [ ] **Step 3: Add users/sessions schema**

Modify `app/db.py` — append to `ensure_schema` before `connection.commit()`:

```python
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL REFERENCES users(username),
            expires_at TEXT NOT NULL
        )
        """
    )
```

- [ ] **Step 4: Add AuthRepository**

Add to `app/repository.py` (at the end of the file):

```python
class AuthRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_user(self, *, username: str, password_hash: str) -> None:
        self._connection.execute(
            """
            INSERT INTO users (username, password_hash) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
            """,
            (username, password_hash),
        )
        self._connection.commit()

    def verify_user(self, username: str, password_hash: str) -> bool:
        row = self._connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row is not None and row["password_hash"] == password_hash

    def create_session(self, *, username: str, ttl: timedelta) -> str:
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + ttl).isoformat()
        self._connection.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires),
        )
        self._connection.commit()
        return token

    def get_session_user(self, token: str) -> str | None:
        row = self._connection.execute(
            "SELECT username, expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires <= datetime.utcnow():
            self.delete_session(token)
            return None
        return row["username"]

    def delete_session(self, token: str) -> None:
        self._connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self._connection.commit()
```

Add imports at the top of `app/repository.py` (after existing imports):

```python
import secrets
from datetime import datetime, timedelta
```

Add `get_user_hash` to the `AuthRepository` class (used by the login route in Task 3):

```python
    def get_user_hash(self, username: str) -> str | None:
        row = self._connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return None if row is None else row["password_hash"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth_repository.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/repository.py tests/test_auth_repository.py
git commit -m "feat: add users and sessions tables with auth repository"
```

---

### Task 3: Login routes, session dependency, and route protection

**Files:**
- Modify: `app/main.py`
- Create: `app/templates/login.html`
- Test: `tests/test_auth_web.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_web.py`:

```python
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
    )
    return TestClient(app), auth


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth_web.py -v`
Expected: FAIL (login route 404, protection absent)

- [ ] **Step 3: Add auth dependency helpers to main.py**

Modify `app/main.py`. Add imports at top:

```python
from datetime import timedelta

from fastapi.responses import RedirectResponse

from app.auth import hash_password, verify_password
from app.repository import AuthRepository
```

(Do not remove the existing `from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile` line — add the new names to that existing import or keep it separate as shown.)

Add helper functions before `build_app`. Two behaviors are needed: HTML page routes must **redirect** to `/login` (303), while JSON API routes must return **401**. A private exception + handler provides the redirect for pages:

```python
class RedirectRequest(Exception):
    def __init__(self, location: str = "/login") -> None:
        self.location = location


def require_auth(request: Request, *, auth_password: str, auth_repo: AuthRepository) -> None:
    """For JSON API endpoints: raise 401 when unauthenticated."""
    if not auth_password:
        return
    token = request.cookies.get("tgs3_session")
    user = auth_repo.get_session_user(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")


def require_page(request: Request, *, auth_password: str, auth_repo: AuthRepository) -> None:
    """For HTML page endpoints: redirect to /login when unauthenticated."""
    if not auth_password:
        return
    token = request.cookies.get("tgs3_session")
    user = auth_repo.get_session_user(token) if token else None
    if user is None:
        raise RedirectRequest("/login")
```

Add a login page render + routes. Change `build_app` signature to accept auth config:

```python
def build_app(service, lifespan=None, preview_renderer=None, *, auth_password: str = "", auth_username: str = "admin", auth_repository: AuthRepository | None = None, session_ttl_days: int = 30, secure_cookie: bool = True) -> FastAPI:
```

Inside `build_app`, after `templates` setup, create auth repository and seed user. The repository shares the same SQLite connection as the file repository, so it is derived from the service; production `create_app` may instead pass `auth_repository=` explicitly when it constructs the service:

```python
    auth = auth_repository or AuthRepository(service._repository._connection)
    if auth_password:
        auth.upsert_user(username=auth_username, password_hash=hash_password(auth_password))
```

Define a small closure used by every protected handler:

```python
    @app.exception_handler(RedirectRequest)
    async def _redirect_handler(_request: Request, exc: RedirectRequest):
        return RedirectResponse(exc.location, status_code=303)

    def require_auth_route(request: Request) -> None:
        require_auth(request, auth_password=auth_password, auth_repo=auth)

    def require_page_route(request: Request) -> None:
        require_page(request, auth_password=auth_password, auth_repo=auth)
```

- [ ] **Step 4: Wire protection + login/logout routes**

Add login routes before `index`:

```python
    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if not auth_password:
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "login.html", {"error": None, "next": request.query_params.get("next", "/")})

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        next_url = form.get("next", "/")
        if not auth_password:
            return RedirectResponse(next_url or "/", status_code=303)
        stored_hash = auth.get_user_hash(auth_username)
        if username == auth_username and stored_hash and verify_password(password, stored_hash):
            token = auth.create_session(username=auth_username, ttl=timedelta(days=session_ttl_days))
            response = RedirectResponse(next_url or "/", status_code=303)
            response.set_cookie("tgs3_session", token, httponly=True, samesite="lax", secure=secure_cookie, max_age=session_ttl_days * 86400)
            return response
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "next": next_url}, status_code=401)

    @app.post("/logout")
    def logout(request: Request):
        token = request.cookies.get("tgs3_session")
        if token:
            auth.delete_session(token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("tgs3_session")
        return response
```

Apply protection to protected routes:
- **HTML pages** (`index`, `detail_page`, `mobile_page`): add `require_page_route(request)` as the first line.
- **JSON API** (`list_files`, `search_files`, `folder_tree`, `create_folder`, `rename_folder`, `delete_folder`, `move_file`, `file_detail`, `download_file`, `preview_file`): add `require_auth_route(request)` as the first line.
- Exempt: `/login`, `/static`, `/mobile/manifest.webmanifest`, `/mobile/sw.js`, `/mobile/icons/*` (no auth call).

- [ ] **Step 5: Create login template**

Create `app/templates/login.html`:

```html
{% extends "base.html" %}
{% block body %}
<div class="login-app">
  <form method="post" action="/login" class="login-card">
    <input type="hidden" name="next" value="{{ next }}">
    <div class="login-brand">
      <span class="drive-title">TGS3</span>
    </div>
    <h1>Sign in</h1>
    {% if error %}<div class="login-error">{{ error }}</div>{% endif %}
    <input class="login-input" type="text" name="username" placeholder="Username" autocomplete="username" required>
    <input class="login-input" type="password" name="password" placeholder="Password" autocomplete="current-password" required>
    <button class="login-submit" type="submit">Sign in</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_auth_web.py -v`
Expected: all PASS (the `test_mobile_page_requires_auth` and manifest/static exemptions pass once Task 4's routes exist — run again after Task 4).

NOTE: `test_static_and_manifest_exempt_from_auth` may fail until `/mobile/manifest.webmanifest` exists (Task 4). It is acceptable to see this one fail here; it must pass at the end of Task 4.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/templates/login.html tests/test_auth_web.py
git commit -m "feat: add login/logout and protect routes with session auth"
```

---

### Task 4: Serve the mobile app shell

**Files:**
- Modify: `app/main.py`
- Create: `s3/mobile/manifest.webmanifest`, `s3/mobile/sw.js`, `s3/mobile/mobile.html`, `s3/mobile/mobile.css`, `s3/mobile/mobile.js`
- Test: `tests/test_mobile_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mobile_routes.py`:

```python
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
    assert "serviceworker" in response.headers.get("content-type", "")
    assert "CACHE" in response.text


def test_icons_served(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/mobile/icons/icon-192.png").status_code == 200
    assert client.get("/mobile/icons/icon-512.png").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_mobile_routes.py -v`
Expected: FAIL (404s)

- [ ] **Step 3: Create mobile app files**

Create `s3/mobile/manifest.webmanifest`:

```json
{
  "name": "TGS3",
  "short_name": "TGS3",
  "start_url": "/mobile",
  "display": "standalone",
  "background_color": "#131314",
  "theme_color": "#1a73e8",
  "icons": [
    { "src": "/mobile/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
    { "src": "/mobile/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
```

Create `s3/mobile/sw.js`:

```javascript
const CACHE = "tgs3-shell-v1";
const SHELL = [
  "/mobile",
  "/mobile/mobile.css",
  "/mobile/mobile.js",
  "/mobile/manifest.webmanifest",
  "/mobile/icons/icon-192.png",
  "/mobile/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/files") || url.pathname.startsWith("/folders") || url.pathname.startsWith("/mobile")) {
    event.respondWith(
      fetch(event.request).then((response) => {
        if (response.ok && url.pathname.startsWith("/mobile")) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      }).catch(() => caches.match(event.request).then((hit) => hit || caches.match("/mobile")))
    );
    return;
  }
  event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
});
```

Create `s3/mobile/icons/` with two valid PNG files (192 and 512). Generate with Python:

```python
# Run once to create placeholder icons (blue square with "T"):
from pathlib import Path
import struct, zlib

def make_png(path: Path, size: int) -> None:
    # minimal solid-color PNG (we replace with real icons later)
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([26, 115, 232]) * size for _ in range(size))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)

Path("s3/mobile/icons").mkdir(parents=True, exist_ok=True)
make_png("s3/mobile/icons/icon-192.png", 192)
make_png("s3/mobile/icons/icon-512.png", 512)
```

Create `s3/mobile/mobile.html` (full single-page shell; app logic in mobile.js, styles in mobile.css):

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>TGS3</title>
  <link rel="manifest" href="/mobile/manifest.webmanifest">
  <meta name="theme-color" content="#1a73e8">
  <link rel="apple-touch-icon" href="/mobile/icons/icon-192.png">
  <link rel="stylesheet" href="/mobile/mobile.css">
</head>
<body>
  <header class="m-header">
    <h1 class="m-brand">TGS3</h1>
    <div class="m-search">
      <input id="m-search" type="search" placeholder="Search files" autocomplete="off">
    </div>
    <button id="m-logout" class="m-icon-btn" title="Log out">⏻</button>
  </header>

  <nav id="m-breadcrumb" class="m-breadcrumb"></nav>

  <main id="m-main" class="m-main">
    <div id="m-empty" class="m-empty" hidden>No files yet. Tap + to upload.</div>
    <ul id="m-file-list" class="m-file-list"></ul>
  </main>

  <div class="m-fab">
    <input id="m-upload-input" type="file" multiple hidden>
    <button id="m-upload-btn" class="m-fab-btn" title="Upload">+</button>
  </div>

  <div id="m-toast" class="m-toast" hidden></div>
  <script src="/mobile/mobile.js" defer></script>
</body>
</html>
```

Create `s3/mobile/mobile.css` (phone-first, minimal; dark-aware):

```css
:root {
  --bg: #ffffff; --fg: #1f1f1f; --subtle: #5f6368;
  --card: #f8f9fa; --accent: #1a73e8; --border: #e1e8f0;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #131314; --fg: #e3e2e6; --subtle: #c4c6c0; --card: #1e1f20; --border: #333537; }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--fg); height: 100dvh; display: flex; flex-direction: column; }
.m-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border); }
.m-brand { font-size: 20px; font-weight: 600; }
.m-search { flex: 1; }
.m-search input { width: 100%; padding: 8px 12px; border-radius: 20px; border: 1px solid var(--border); background: var(--card); color: var(--fg); font-size: 15px; }
.m-icon-btn { border: none; background: transparent; color: var(--fg); font-size: 20px; padding: 8px; }
.m-breadcrumb { display: flex; align-items: center; gap: 6px; padding: 8px 12px; font-size: 13px; color: var(--subtle); overflow-x: auto; white-space: nowrap; }
.m-breadcrumb a { color: var(--accent); text-decoration: none; }
.m-main { flex: 1; overflow-y: auto; padding: 8px 12px 96px; }
.m-file-list { list-style: none; }
.m-file-item { display: flex; align-items: center; gap: 12px; padding: 12px 8px; border-bottom: 1px solid var(--border); cursor: pointer; }
.m-file-icon { font-size: 22px; }
.m-file-meta { flex: 1; min-width: 0; }
.m-file-name { font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-file-sub { font-size: 12px; color: var(--subtle); }
.m-file-action { border: none; background: transparent; color: var(--accent); font-size: 18px; padding: 6px; }
.m-empty { text-align: center; color: var(--subtle); padding: 48px 16px; font-size: 15px; }
.m-fab { position: fixed; right: 20px; bottom: 24px; }
.m-fab-btn { width: 56px; height: 56px; border-radius: 50%; border: none; background: var(--accent); color: #fff; font-size: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.m-toast { position: fixed; left: 50%; bottom: 96px; transform: translateX(-50%); background: #323232; color: #fff; padding: 10px 16px; border-radius: 8px; font-size: 14px; z-index: 10; }
```

Create `s3/mobile/mobile.js` (minimal working bootstrap; full app logic is added in Task 5):

```javascript
// TGS3 mobile bootstrap. Full app logic lands in Task 5.
document.addEventListener("DOMContentLoaded", () => {
  const main = document.getElementById("m-main");
  if (main) main.innerHTML = "<p>Loading…</p>";
});
```

- [ ] **Step 4: Add FastAPI routes for the mobile shell**

Modify `app/main.py`. Add before the `return app` line in `build_app`:

```python
    MOBILE_DIR = Path(__file__).parent.parent / "mobile"

    @app.get("/mobile", response_class=HTMLResponse)
    def mobile_page(request: Request):
        return HTMLResponse((MOBILE_DIR / "mobile.html").read_text())

    @app.get("/mobile/manifest.webmanifest")
    def mobile_manifest():
        return Response(
            content=(MOBILE_DIR / "manifest.webmanifest").read_text(),
            media_type="application/manifest+json",
        )

    @app.get("/mobile/sw.js")
    def mobile_sw():
        return Response(
            content=(MOBILE_DIR / "sw.js").read_text(),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/mobile/icons/{name}")
    def mobile_icon(name: str):
        allowed = {"icon-192.png", "icon-512.png"}
        if name not in allowed:
            raise HTTPException(status_code=404, detail="icon not found")
        return Response(content=(MOBILE_DIR / "icons" / name).read_bytes(), media_type="image/png")
```

Wire `require_auth(request)` into `mobile_page` (per Task 3 Step 4) but NOT into manifest/sw/icons.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests/test_mobile_routes.py tests/test_auth_web.py -v`
Expected: all PASS (both new test files)

- [ ] **Step 6: Commit**

```bash
git add app/main.py s3/mobile tests/test_mobile_routes.py
git commit -m "feat: serve mobile PWA shell with manifest and service worker"
```

---

### Task 5: Mobile app logic

**Files:**
- Modify: `s3/mobile/mobile.js`
- Modify: `s3/mobile/mobile.html` (small additions: preview overlay + folder modal)

- [ ] **Step 1: Replace mobile.js with full logic**

Replace `s3/mobile/mobile.js` with:

```javascript
let currentFolderId = null;
let allFilesCache = [];

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024, sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function typeIcon(mime, name) {
  if ((mime || "").includes("spreadsheet") || (name || "").endsWith(".xlsx")) return "📊";
  if ((mime || "").includes("pdf")) return "📕";
  if ((mime || "").startsWith("image/")) return "🖼️";
  if ((mime || "").startsWith("video/")) return "🎬";
  if ((mime || "").includes("zip")) return "🗜️";
  return "📄";
}

function showToast(msg) {
  const toast = document.getElementById("m-toast");
  toast.textContent = msg;
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 3000);
}

function renderBreadcrumb() {
  const nav = document.getElementById("m-breadcrumb");
  nav.innerHTML = `<a href="#" data-folder="">All Files</a>`;
  // Real breadcrumb requires the backend chain; keep simple: show current folder name if set.
  if (currentFolderId) nav.innerHTML += `<span>›</span><span>Folder ${currentFolderId}</span>`;
}

async function refreshFiles(query = "") {
  const url = query ? `/files/search?q=${encodeURIComponent(query)}` : `/files?folder_id=${currentFolderId || ""}`;
  const res = await fetch(url);
  if (res.status === 401) { window.location.href = "/login"; return; }
  allFilesCache = await res.json();
  renderFileList();
}

function renderFileList() {
  const list = document.getElementById("m-file-list");
  const empty = document.getElementById("m-empty");
  const files = allFilesCache;
  empty.hidden = files.length > 0;
  list.innerHTML = files.map((f) => `
    <li class="m-file-item" data-id="${f.id}">
      <div class="m-file-icon">${typeIcon(f.mime_type, f.name)}</div>
      <div class="m-file-meta">
        <div class="m-file-name">${f.name}</div>
        <div class="m-file-sub">${formatBytes(f.size_bytes)} • ${formatDate(f.uploaded_at)}</div>
      </div>
      <button class="m-file-action" data-action="download" data-id="${f.id}" title="Download">⬇</button>
    </li>
  `).join("");
}

async function uploadFiles(fileList) {
  for (const file of Array.from(fileList)) {
    const formData = new FormData();
    formData.append("file", file);
    const folderParam = currentFolderId ? `?folder_id=${currentFolderId}` : "";
    try {
      const res = await fetch(`/files/upload${folderParam}`, { method: "POST", body: formData });
      if (res.ok) {
        showToast(`Uploaded ${file.name}`);
      } else if (res.status === 401) {
        window.location.href = "/login"; return;
      } else {
        showToast(`Failed to upload ${file.name}`);
      }
    } catch (err) {
      showToast("You're offline. Upload failed.");
    }
  }
  await refreshFiles();
}

document.addEventListener("DOMContentLoaded", () => {
  refreshFiles();

  document.getElementById("m-search").addEventListener("input", (e) => {
    const q = e.target.value.trim();
    if (q) refreshFiles(q); else refreshFiles();
  });

  document.getElementById("m-upload-btn").addEventListener("click", () => {
    document.getElementById("m-upload-input").click();
  });
  document.getElementById("m-upload-input").addEventListener("change", (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
  });

  document.getElementById("m-logout").addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    window.location.href = "/login";
  });

  document.getElementById("m-main").addEventListener("click", (e) => {
    const downloadBtn = e.target.closest("[data-action='download']");
    if (downloadBtn) {
      e.stopPropagation();
      window.location.href = `/files/${downloadBtn.dataset.id}/download`;
      return;
    }
    const item = e.target.closest(".m-file-item");
    if (item) window.location.href = `/view/files/${item.dataset.id}`;
  });
});
```

- [ ] **Step 2: Test on live server (manual)**

Run: `cd /home/devisdd/s3 && .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000`
Open `http://localhost:8000/mobile` in a browser/phone devtools mobile view. Expected: page loads, files list from the API, search filters, upload works, download triggers.

- [ ] **Step 3: Commit**

```bash
git add s3/mobile/mobile.js
git commit -m "feat: implement mobile PWA app logic"
```

---

### Task 6: Hosting doc (Cloudflare Tunnel)

**Files:**
- Create: `docs/HOSTING.md`

- [ ] **Step 1: Write hosting instructions**

Create `docs/HOSTING.md`:

```markdown
# Hosting TGS3 on the Internet (free)

TGS3 runs as a local web app. To reach it from your phone anywhere:

## 1. Set up auth first (required)

Create a `.env` entry:

    TGS3_PASSWORD=your-secret-password
    TGS3_USER=admin            # optional, default admin

Without a password the app runs open (dev mode). With a password,
every page (including /mobile) requires login.

## 2. Install Cloudflare Tunnel (free)

1. Download `cloudflared` (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
2. Run the app: `cd ~/s3 && .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000`
3. Expose it: `cloudflared tunnel --url http://localhost:8000`
4. Cloudflare prints a public HTTPS URL (e.g. `https://xxxx.trycloudflare.com`)

That URL is temporary (changes on restart). For a permanent URL use a
named tunnel + your own domain on the Cloudflare free plan.

## 3. Use it on your phone

1. Open the public URL in a mobile browser.
2. Sign in (username/password from step 1).
3. Add to home screen (Android: menu → Add to Home screen; iOS: Share → Add to Home Screen).
4. Open the installed "TGS3" icon — it launches fullscreen.

## Notes

- Your home computer must stay on and online while the tunnel is running.
- Session cookie lasts 30 days by default (`TGS3_SESSION_TTL_DAYS`).
- `TGS3_SECURE_COOKIE=1` (default) works over the tunnel's HTTPS.
- For LAN-only use (no tunnel), visit `http://<home-ip>:8000` and set
  `TGS3_SECURE_COOKIE=0` so the cookie works over plain HTTP.
```

- [ ] **Step 2: Commit**

```bash
git add docs/HOSTING.md
git commit -m "docs: add Cloudflare Tunnel hosting instructions"
```

---

### Task 7: Final verification

- [ ] **Step 1: Full test suite**

Run: `cd /home/devisdd/s3 && .venv/bin/pytest tests -q`
Expected: 53 passed (34 baseline + 3 `test_auth` + 5 `test_auth_repository` + 7 `test_auth_web` + 4 `test_mobile_routes`), 0 failures

- [ ] **Step 2: Restart server with auth enabled**

```bash
cd /home/devisdd/s3
pkill -f "uvicorn app.asgi:app" || true
TGS3_PASSWORD=test123 .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000 > .data/uvicorn.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/   # expect 303 to /login
curl -s -c /tmp/cj -d "username=admin&password=test123" -o /dev/null -w "%{http_code}\n" http://localhost:8000/login   # expect 303
curl -s -b /tmp/cj -o /dev/null -w "%{http_code}\n" http://localhost:8000/   # expect 200
curl -s -b /tmp/cj -o /dev/null -w "%{http_code}\n" http://localhost:8000/mobile   # expect 200
```

- [ ] **Step 3: Update README**

Add a "Mobile" section to `README.md` pointing to `docs/HOSTING.md` and `/mobile`. Commit:

```bash
git add README.md
git commit -m "docs: document mobile access in README"
```
