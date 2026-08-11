# TGS3 Preview Expansion Design

**Goal:** Expand the preview pane to support video, audio, and raw text/markdown files, alongside the existing image/PDF/office previews.

**Approach:** Pure pass-through in the preview renderer. No template or route changes.

## Current behavior

`app/previews.py::PreviewRenderer.render` classifies by MIME type:

- **Pass-through:** images, PDF
- **LibreOffice → PDF:** office documents plus `text/plain` and `text/markdown`
- **Unsupported (415):** video, audio, archives, and everything else

The detail page (`app/templates/file_detail.html`) and mobile both embed `/files/{id}/preview` in an iframe. The preview route already serves `Content-Disposition: inline` with the stored `media_type`, so passing through a new type works with no route change.

## Changes

### `app/previews.py`

1. Add `VIDEO_MIME_TYPES`:
   - `video/mp4`, `video/webm`, `video/quicktime`, `video/x-msvideo`, `video/ogg`, `video/mpeg`

2. Add `AUDIO_MIME_TYPES`:
   - `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/mp4`, `audio/ogg`, `audio/aac`, `audio/flac`

3. Add `TEXT_MIME_TYPES`:
   - `text/plain`, `text/markdown`

4. Remove `text/plain` and `text/markdown` from `OFFICE_MIME_TYPES` (LibreOffice is now only for real office documents).

5. In `render()`: pass through (return `downloaded` unchanged) when the MIME type is in `IMAGE_MIME_TYPES`, `PDF_MIME_TYPE`, `VIDEO_MIME_TYPES`, `AUDIO_MIME_TYPES`, or `TEXT_MIME_TYPES`.

### Tests (`tests/test_previews.py`)

- `test_video_preview_passes_through` — `video/mp4` returns unchanged.
- `test_audio_preview_passes_through` — `audio/mpeg` returns unchanged.
- `test_text_preview_passes_through` — `text/plain` returns unchanged (no LibreOffice invoked).
- `test_markdown_preview_passes_through` — `text/markdown` returns unchanged.
- Keep existing image/PDF/unsupported tests green.

## Non-goals

- No HTTP Range/seek support for video (personal-use limitation; iframe/player still plays from the top).
- No markdown→HTML rendering (raw markdown text is shown).
- No changes to routes, templates, or the mobile app.
