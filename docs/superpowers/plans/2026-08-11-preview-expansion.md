# TGS3 Preview Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add video, audio, and raw text/markdown previews by making the preview renderer pass these types through unchanged.

**Architecture:** `PreviewRenderer.render()` in `app/previews.py` classifies files by MIME type. Images and PDF already pass through; office docs convert via LibreOffice to PDF. We add three new pass-through groups (video, audio, text/markdown) and remove text types from the LibreOffice group. No route or template changes — the preview route already serves `inline` with the stored `media_type`.

**Tech Stack:** Python 3.13, FastAPI, stdlib only. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-11-preview-expansion-design.md`

**Baseline:** Existing 53 tests must stay green. Run with `/home/devisdd/s3/.venv/bin/pytest tests -q`.

---

### Task 1: Pass-through video, audio, and text previews

**Files:**
- Modify: `app/previews.py`
- Test: `tests/test_previews.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_previews.py`:

```python
def test_video_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="clip.mp4",
        content=b"video-bytes",
        mime_type="video/mp4",
    )

    preview = renderer.render(file_id=4, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "video/mp4"
    assert preview.content == b"video-bytes"


def test_audio_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="song.mp3",
        content=b"audio-bytes",
        mime_type="audio/mpeg",
    )

    preview = renderer.render(file_id=5, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "audio/mpeg"
    assert preview.content == b"audio-bytes"


def test_text_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="notes.txt",
        content=b"plain text",
        mime_type="text/plain",
    )

    preview = renderer.render(file_id=6, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "text/plain"
    assert preview.content == b"plain text"


def test_markdown_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="README.md",
        content=b"# Title",
        mime_type="text/markdown",
    )

    preview = renderer.render(file_id=7, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "text/markdown"
    assert preview.content == b"# Title"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/devisdd/s3/.venv/bin/pytest tests/test_previews.py -v`
Expected: the 4 new tests FAIL (`AssertionError: preview is None`), existing 3 PASS.

- [ ] **Step 3: Implement pass-through groups in the renderer**

Modify `app/previews.py`:

Replace the `PDF_MIME_TYPE` / `OFFICE_MIME_TYPES` block (lines 16-30) with:

```python
PDF_MIME_TYPE = "application/pdf"

VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/ogg",
    "video/mpeg",
}

AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/ogg",
    "audio/aac",
    "audio/flac",
}

TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
}

OFFICE_MIME_TYPES = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
}
```

Replace the body of `render` (lines 38-53) with:

```python
    def render(self, *, file_id: int, downloaded: DownloadedTelegramFile) -> DownloadedTelegramFile | None:
        mime_type = downloaded.mime_type or "application/octet-stream"
        if mime_type in IMAGE_MIME_TYPES:
            return downloaded
        if mime_type == PDF_MIME_TYPE:
            return downloaded
        if mime_type in VIDEO_MIME_TYPES:
            return downloaded
        if mime_type in AUDIO_MIME_TYPES:
            return downloaded
        if mime_type in TEXT_MIME_TYPES:
            return downloaded
        if mime_type not in OFFICE_MIME_TYPES:
            return None
        pdf_path = self._cache_dir / f"{file_id}.pdf"
        if not pdf_path.exists():
            pdf_path = self._convert_to_pdf(downloaded.filename, downloaded.content, pdf_path)
        return DownloadedTelegramFile(
            filename=pdf_path.name,
            content=pdf_path.read_bytes(),
            mime_type=PDF_MIME_TYPE,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/devisdd/s3/.venv/bin/pytest tests/test_previews.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Run full suite**

Run: `/home/devisdd/s3/.venv/bin/pytest tests -q`
Expected: 57 passed, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add app/previews.py tests/test_previews.py
git commit -m "feat: preview video, audio, and text files by passing them through"
```

---

### Task 2: Manual verification on live server

- [ ] **Step 1: Restart server**

```bash
cd /home/devisdd/s3
pkill -f "uvicorn app.asgi:app" || true
nohup .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000 > .data/uvicorn.log 2>&1 &
```

- [ ] **Step 2: Verify preview endpoint returns inline content types**

Run: `curl -s -b /tmp/cj -o /dev/null -w "%{content_type}\n" http://localhost:8000/files/<file_id>/preview` for a stored video/audio/text file.
Expected: `video/mp4`, `audio/mpeg`, or `text/plain` as appropriate (not 415).
