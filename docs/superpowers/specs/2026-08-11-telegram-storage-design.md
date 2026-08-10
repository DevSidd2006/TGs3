# Telegram Storage Manager Design

## Summary

Build a single-user web app in `s3/` that feels like a minimal Google Drive for personal storage, but uses one private Telegram channel as the file backend. The first version focuses on uploading, browsing, searching, and downloading files reliably, with a local metadata index for speed.

## Goals

- Provide a minimal web UI for personal file storage management.
- Store uploaded files in a single private Telegram channel.
- Keep file browsing fast by indexing metadata locally.
- Leave clean extension points for folders, tags, multi-channel storage, and multi-user workspaces later.

## Non-Goals

- Team collaboration or org workspaces.
- Public sharing links.
- Complex permissions.
- Automatic sync from external drives or cloud providers.
- Multi-channel routing in the MVP.

## Recommended Architecture

Use a local web application with four main parts:

1. Frontend web UI
2. Backend HTTP API
3. Telegram storage bridge
4. Local SQLite metadata index

The browser never talks to Telegram directly. All Telegram interaction goes through the backend, which also owns indexing and download streaming.

## System Components

### Frontend

The frontend is a minimal storage dashboard with:

- A sidebar for `All Files`, `Recent`, and `Uploads`
- A top bar with search and upload controls
- A main file list or grid
- A file detail panel or page

The frontend only consumes backend APIs and does not contain Telegram-specific logic.

### Backend API

The backend is responsible for:

- Accepting file uploads from the browser
- Sending files to the Telegram channel
- Recording and querying metadata in SQLite
- Returning file lists and search results
- Streaming downloaded files back to the browser

### Telegram Storage Bridge

This module wraps Telegram client operations. Its responsibilities are:

- Upload file to the configured private channel
- Capture Telegram message and file identifiers
- Resolve file metadata needed for later downloads
- Download or stream file content when requested

This module should be isolated behind a small interface so later changes such as multiple channels or bot-based uploads do not affect the rest of the app heavily.

### SQLite Metadata Index

SQLite is the source of truth for app browsing state. Telegram remains the source of truth for file bytes.

SQLite is used for:

- Fast listing and search
- Local status tracking
- Future folder and tag support
- Detecting failed or missing uploads

## Data Model

Create a `files` table with these fields:

- `id`
- `name`
- `size_bytes`
- `mime_type`
- `telegram_channel_id`
- `telegram_message_id`
- `telegram_file_id`
- `uploaded_at`
- `status`

Optional MVP-safe fields that may be included now to reduce later migration friction:

- `folder`
- `tags`

`status` should support at least:

- `uploading`
- `ready`
- `failed`

## Core User Flows

### Upload Flow

1. User selects a file in the browser.
2. Frontend sends the file to the backend.
3. Backend uploads the file to the private Telegram channel.
4. Backend receives Telegram identifiers for the uploaded file.
5. Backend writes a metadata row into SQLite.
6. Frontend refreshes file state from the API.

The row should only become `ready` after both Telegram upload and metadata persistence succeed.

### Browse Flow

1. Frontend requests file list from the backend.
2. Backend reads metadata from SQLite.
3. Frontend renders results as a table or grid.

Browse should never require scanning Telegram messages live during normal operation.

### Search Flow

1. User types in the search bar.
2. Frontend queries the backend.
3. Backend searches SQLite metadata.
4. Frontend renders matching files.

MVP search can be limited to filename and basic metadata.

### Download Flow

1. User clicks a file to download.
2. Frontend requests the download endpoint.
3. Backend resolves Telegram IDs from SQLite.
4. Backend fetches or streams the file from Telegram.
5. Browser receives the file download.

## Minimal UI Scope

The first UI should stay narrow and usable:

- `All Files` view
- `Recent` view
- `Uploads` view
- Upload button with file picker support
- Search field
- File list showing name, size, type, upload date, and status
- File detail view with metadata and download action

No previews, no sharing UI, and no folder tree are required in v1.

## API Surface

The MVP backend should expose endpoints equivalent to:

- `POST /files/upload`
- `GET /files`
- `GET /files/:id`
- `GET /files/search?q=`
- `GET /files/:id/download`

Exact route names can change during implementation, but the responsibilities should remain the same.

## Error Handling

The app should explicitly handle:

- Telegram upload failure
- SQLite write failure after Telegram upload
- Download request for a missing Telegram message
- Unsupported or oversized files if Telegram limits are exceeded
- Temporary Telegram API/network failures

Behavior expectations:

- Failed uploads are marked `failed`
- The UI shows status clearly
- Partial failures do not silently appear as completed files
- Missing Telegram objects return a clear unavailable state

Retry support can be basic in the MVP, even if initially manual.

## Configuration

The app will require configuration for:

- Telegram API credentials or session details
- The target private channel identifier
- SQLite database location
- Local server settings

These should be isolated in environment-based configuration rather than hardcoded into the app.

## Testing Strategy

The first implementation should cover:

- Upload path success case
- Metadata persistence after upload
- File list and search behavior
- Download path success case
- Failure handling when Telegram upload or retrieval fails

At minimum, the storage bridge should be mockable so API and data-layer behavior can be tested without real Telegram traffic in every test.

## Future Expansion Path

After the MVP is working, the next logical phases are:

1. Folders and tags
2. Preview support for common file types
3. Multiple Telegram channels as storage buckets
4. Background sync or backup jobs
5. Authentication and small-team workspace features

The MVP architecture is chosen specifically so these features can be added without rewriting the basic upload, index, and download model.

## Open Implementation Decisions

These are intentionally left for implementation planning, not product design:

- Specific frontend framework
- Specific backend framework
- Telegram library choice
- Exact database access library

The design requirement is that the chosen stack should favor a fast local MVP with a simple path to growth.
