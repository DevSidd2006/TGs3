# Design: Channel ↔ Local `.db` Sync

**Date:** 2026-08-11
**Status:** Approved

## Goal

Keep the Telegram channel and the local SQLite database in sync. The Telegram channel is the source of truth for file bytes; the local `.db` holds file metadata (name, size, mime type, Telegram references). This sync replaces cross-instance database reconciliation and provides a single consistent view of channel content in the app.

## Scope

This is a confirmation-and-verification pass over the sync feature as already built. No new subsystems. A common shared/hosted database is explicitly **out of scope** for now (deferred).

## Architecture

- **Telegram channel** = source of truth for file content. Uploads write straight to the channel.
- **Local `.db` (SQLite)** = working metadata store for the app (files, folders, auth).
- **Sync (pull)** = scan the channel and upsert metadata into the `.db`, deduped by `(telegram_channel_id, telegram_message_id)`.
- **Download (on-demand)** = fetch bytes from Telegram only when a file is opened, downloaded, or previewed. No local disk copy.

## Behavior

### Pull (sync button)
- `TelethonStorage.list_channel_files` scans the channel via `iter_messages`, capped at the **most recent 200 messages** to protect against Telegram ToS/ban risk.
- For each message with a file, `upsert_synced_file` writes `name`, `size_bytes`, `mime_type`, `telegram_channel_id`, `telegram_message_id`, `telegram_file_id` into `files`, marking status `ready`.
- Dedup: an existing row with the same `(channel_id, message_id)` is updated in place rather than duplicated.
- `POST /sync` requires auth and is rate-limited to one sync per 60 seconds (429 on rapid repeats).

### On-demand download
- `GET /files/{id}/download` and `GET /files/{id}/preview` fetch content from Telegram only when requested.
- Files synced from the channel are immediately downloadable without any local copy step.

### Push (uploads)
- Uploads are sent directly to the channel at upload time, so the channel always contains every file the app knows about.

## Known Limitation (accepted)

Telegram messages have no folder concept, so **folder structure is local-only**. Files pulled from the channel land at the root of the file list. Preserving folders across instances is deferred to the future shared-DB work.

## Testing

- Existing tests cover `sync_from_channel` (service) and `POST /sync` (web), including the rate-limit (429 on immediate second call).
- Add a test asserting the scan cap behavior (limit) at the bridge level if feasible with the current fake/telegram abstractions.
- Verify end-to-end manually: upload a file directly to the channel from the Telegram app → press sync → file appears in the app with correct metadata → download works.

## Out of Scope

- Shared/hosted database (deferred).
- Syncing folder structure via the channel.
- Fully downloading channel content to local disk.
- Bidirectional push of DB-only rows back to the channel.
