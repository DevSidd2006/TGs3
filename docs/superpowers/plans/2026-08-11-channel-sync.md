# Channel ↔ Local `.db` Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and lock in the existing Telegram channel ↔ local SQLite sync behavior with automated tests for the scan cap and dedup, then confirm end-to-end.

**Architecture:** The Telegram channel is the source of truth for file bytes; the local SQLite `.db` holds metadata. `TelethonStorage.list_channel_files` scans the channel (capped at 200 recent messages) and `StorageService.sync_from_channel` upserts metadata into the `files` table, deduped by `(telegram_channel_id, telegram_message_id)`. The feature is already built; this plan adds the missing test coverage and an E2E verification pass.

**Tech Stack:** Python 3.13, FastAPI, Telethon, SQLite, pytest.

**Reference spec:** `docs/superpowers/specs/2026-08-11-channel-sync-design.md`

---

### Task 1: Repository dedup test for `upsert_synced_file`

**Files:**
- Modify: `tests/test_repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_repository.py`:

```python
def test_upsert_synced_file_updates_existing_row(tmp_path: Path):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)

    first = repository.upsert_synced_file(
        name="report.pdf",
        size_bytes=100,
        mime_type="application/pdf",
        telegram_channel_id=-1005,
        telegram_message_id=42,
        telegram_file_id="file_42",
    )
    second = repository.upsert_synced_file(
        name="report-v2.pdf",
        size_bytes=200,
        mime_type="application/pdf",
        telegram_channel_id=-1005,
        telegram_message_id=42,
        telegram_file_id="file_42_new",
    )

    assert first.id == second.id
    files = repository.list_files()
    assert len(files) == 1
    assert files[0].name == "report-v2.pdf"
    assert files[0].telegram_file_id == "file_42_new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_repository.py::test_upsert_synced_file_updates_existing_row -v`
Expected: PASS (this behavior already exists — the test documents it). If it fails, fix `upsert_synced_file` in `app/repository.py` so updates happen in place.

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests -q`
Expected: 61 passed (60 existing + 1 new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_repository.py
git commit -m "test: assert sync upsert dedupes by channel and message id"
```

---

### Task 2: Service-level dedup test (sync twice → no duplicates)

**Files:**
- Modify: `tests/test_service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_service.py::test_sync_from_channel_twice_does_not_duplicate -v`
Expected: PASS (dedup handled by `upsert_synced_file`).

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests -q`
Expected: 62 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_service.py
git commit -m "test: sync twice keeps a single row per channel message"
```

---

### Task 3: Bridge scan-cap test (`list_channel_files` passes limit)

**Files:**
- Modify: `tests/fakes.py` — add `FakeTelethonClient`
- Create: `tests/test_telegram_bridge.py`
- Test: `tests/test_telegram_bridge.py`

- [ ] **Step 1: Add a fake Telethon client to `tests/fakes.py`**

Append to `tests/fakes.py`:

```python
class _AsyncMessages:
    def __init__(self, messages: list) -> None:
        self._iterator = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeTelethonClient:
    def __init__(self, messages: list) -> None:
        self._messages = messages
        self.iter_kwargs: dict | None = None

    def iter_messages(self, entity, **kwargs):
        self.iter_kwargs = kwargs
        return _AsyncMessages(self._messages)


def make_file_message(message_id: int, *, name: str | None = None, size: int | None = None, mime: str | None = None, has_file: bool = True):
    class _File:
        id = f"file_{message_id}"
        name = name
        size = size
        mime_type = mime

    class _Message:
        id = message_id
        message = f"caption_{message_id}"

        def __init__(self) -> None:
            self.file = _File() if has_file else None

    return _Message()
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_telegram_bridge.py`:

```python
from app.telegram_bridge import TelethonStorage
from tests.fakes import FakeTelethonClient, make_file_message


def test_list_channel_files_caps_scan_and_skips_non_files():
    messages = [
        make_file_message(1, name="a.pdf", size=10, mime="application/pdf"),
        make_file_message(2, name="b.txt", size=5, mime="text/plain"),
        make_file_message(3, has_file=False),
    ]
    client = FakeTelethonClient(messages)
    storage = TelethonStorage(client)

    files = asyncio.run(storage.list_channel_files(channel_id=-1009))

    assert client.iter_kwargs == {"limit": 200}
    assert [(f["telegram_message_id"], f["name"]) for f in files] == [(1, "a.pdf"), (2, "b.txt")]
    assert all(f["telegram_channel_id"] == -1009 for f in files)
```

Note: add `import asyncio` at the top of `tests/test_telegram_bridge.py`.

- [ ] **Step 3: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_telegram_bridge.py -v`
Expected: PASS (the `limit=200` default already exists in `TelethonStorage.list_channel_files`).

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests -q`
Expected: 64 passed (62 + 2 new: cap test + the non-file skip assertions inside it).

- [ ] **Step 5: Commit**

```bash
git add tests/fakes.py tests/test_telegram_bridge.py
git commit -m "test: assert channel scan caps at limit and skips non-file messages"
```

---

### Task 4: E2E verification (manual, live)

**Files:**
- None (verification only)

- [ ] **Step 1: Ensure local server is running with a valid session**

Run: `curl -s -c /tmp/cj.txt -d "username=admin&password=demo1234" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login`
Expected: `303`

If the server is not running, start it:
```bash
nohup .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000 > /tmp/tgs3.log 2>&1 &
```

- [ ] **Step 2: Upload a file directly to the Telegram channel from the Telegram app**

Use the Telegram app to send a document (e.g., `e2e-check.txt`) directly to the private channel configured in `TELEGRAM_CHANNEL_ID`.

- [ ] **Step 3: Trigger sync and confirm the file appears**

Run: `curl -s -b /tmp/cj.txt -X POST -w " [%{http_code}]\n" http://127.0.0.1:8000/sync`
Expected: `{"synced_count":N} [200]` with `N >= 1`.

Run: `curl -s -b /tmp/cj.txt http://127.0.0.1:8000/files`
Expected: JSON list containing `e2e-check.txt` with `"status": "ready"`.

If sync returns 429, wait ~60s and retry (cooldown is intentional).

- [ ] **Step 4: Confirm on-demand download works**

Run: `curl -s -b /tmp/cj.txt -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/files/<ID>/download` (replace `<ID>` with the file id from Step 3)
Expected: `200`

- [ ] **Step 5: Commit any fixes found during verification**

If Step 3 or Step 4 revealed a bug, fix it, run `.venv/bin/pytest tests -q`, and commit. If everything passed, no commit is needed.

---

## Self-Review

- **Spec coverage:** Spec's "Testing" section asks for a scan-cap test (Task 3), dedup coverage (Tasks 1–2), and E2E verification (Task 4). All covered.
- **Placeholder scan:** No TBD/TODO; every step has concrete code or commands.
- **Type consistency:** `make_file_message` returns objects with `.id`, `.message`, `.file` matching what `list_channel_files` reads (`message.id`, `message.file.name`, `message.file.size`, `message.file.mime_type`, `message.message`). `FakeTelethonClient.iter_kwargs` matches the real `iter_messages(channel_id, limit=limit)` call.
