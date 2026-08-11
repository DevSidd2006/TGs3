# S3 Improvements (Deprecation Fixes & File Upload Streaming) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate Python 3.13 deprecation warnings in repository sessions and add chunked file upload streaming support to prevent memory bloat during file uploads.

**Architecture:** 
1. Replace `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` in `AuthRepository`.
2. Extend `TelegramStorage.upload` and `StorageService` to support file-like streams (`BinaryIO`), allowing FastAPI to stream `UploadFile.file` directly without loading the entire payload into RAM via `bytes`.

**Tech Stack:** Python 3.10+, FastAPI, Telethon, SQLite3, pytest.

---

### Task 1: Replace Deprecated `datetime.utcnow()` in `app/repository.py`

**Files:**
- Modify: `app/repository.py:206-226`
- Test: `tests/test_auth_repository.py`

- [ ] **Step 1: Write failing/updating test in `tests/test_auth_repository.py` for timezone-aware session validation**

Ensure `create_session` and `get_session_user` handle UTC timezone-aware datetimes properly.

- [ ] **Step 2: Update `app/repository.py` to use `datetime.now(timezone.utc)`**

In `create_session` and `get_session_user`:
Import `timezone` from `datetime`.
Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.
In `get_session_user`, parse `expires_at` using `datetime.fromisoformat`. If `expires` is naive (from old DB data), make it UTC aware before comparing with `datetime.now(timezone.utc)`.

- [ ] **Step 3: Run pytest to verify all auth repository tests pass and no deprecation warnings are emitted for session timestamps**

Run: `.venv/bin/pytest tests/test_auth_repository.py -v`
Expected: PASS with 0 deprecation warnings for `datetime.utcnow()`.

---

### Task 2: Implement File Stream Uploading in `app/telegram_bridge.py` and `app/service.py`

**Files:**
- Modify: `app/telegram_bridge.py:21-42`
- Modify: `app/service.py:11-31`
- Modify: `tests/fakes.py:20-25`
- Test: `tests/test_service.py`

- [ ] **Step 1: Update `TelegramStorage` protocol and `TelethonStorage` implementation**

In `app/telegram_bridge.py`:
Support `content: bytes | BinaryIO` (or `file_obj: BinaryIO`).
If `content` is `bytes`, wrap in `BytesIO(content)`.
If `content` is file-like, ensure `name` attribute is set to `filename` and pass directly to `self._client.send_file(...)`.

- [ ] **Step 2: Update `FakeTelegramStorage` in `tests/fakes.py`**

In `FakeTelegramStorage.upload`:
If `content` is a file-like object, call `content.read()` to capture the `bytes` in `UploadStub(content=...)`.

- [ ] **Step 3: Add streaming upload method `upload_stream` to `StorageService` in `app/service.py`**

Add `upload_stream(*, filename: str, file_obj: BinaryIO, size_bytes: int, mime_type: str | None, folder_id: int | None = None)` in `StorageService`.
Refactor `upload_bytes` to wrap bytes in `BytesIO(content)` and call `upload_stream`.

- [ ] **Step 4: Add unit tests for `upload_stream` in `tests/test_service.py`**

Add test verifying `upload_stream` correctly records file size, status `ready`, and sends file stream to `TelegramStorage`.

- [ ] **Step 5: Run pytest on service tests**

Run: `.venv/bin/pytest tests/test_service.py -v`
Expected: PASS.

---

### Task 3: Update FastAPI Upload Endpoint in `app/main.py` & Test Suite

**Files:**
- Modify: `app/main.py:205-215`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Update POST `/upload` route in `app/main.py`**

In `upload_file` route in `app/main.py`:
Instead of `content = await file.read()` and `upload_bytes`, use `file.file` and `file.size` (or seek to determine size) with `service.upload_stream(...)`.

- [ ] **Step 2: Run pytest to verify all web routes pass**

Run: `.venv/bin/pytest tests/test_web.py tests/test_mobile_routes.py -v`
Expected: PASS.

---

### Task 4: Full Test Suite Verification & Graphify Update

- [ ] **Step 1: Run full pytest suite**

Run: `.venv/bin/pytest`
Expected: 64+ tests passing, 0 deprecation warnings from repository.

- [ ] **Step 2: Update knowledge graph**

Run: `graphify update .` (or check graphify status).
