# Folders & Hierarchy — Design

**Date:** 2026-08-11
**Status:** Approved
**Base:** TGS3 — see `2026-08-11-telegram-storage-design.md`

## Goal

Add Google-Drive-style folder organization to TGS3: create, rename, and delete folders with unlimited nesting, navigate via a sidebar tree and breadcrumbs, upload into a chosen folder, and move existing files between folders. Tags, favorites, sharing, and auth are explicitly out of scope.

## Data Model

New table:

```sql
CREATE TABLE folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES folders(id),  -- NULL = root
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

Alter `files`:

```sql
ALTER TABLE files ADD COLUMN folder_id INTEGER REFERENCES folders(id)  -- NULL = root
```

- Unlimited nesting via `parent_id` self-reference.
- Deleting a folder is allowed only when it is empty (no direct files, no subfolders) — no cascades in this phase.
- A file in a folder is only reachable when browsing that folder's subtree; root (`folder_id IS NULL`) is "All Files".

## Backend

### Repository (`FileRepository` grows folder methods)

- `create_folder(name, parent_id)` — raises on unknown parent or invalid name.
- `rename_folder(folder_id, name)` — raises 404 if folder missing.
- `delete_folder(folder_id)` — raises 409 if not empty.
- `get_folder(folder_id)`
- `list_folders()` — flat list for tree building.
- `list_files(folder_id=None)` — filter by exact folder; `None` = root.
- `move_file(file_id, folder_id)` — raises 404/400 on unknown target; `folder_id` may be `None` (move to root).
- `get_breadcrumb(folder_id)` — ordered ancestors root→current, raising 404 if any link broken.

### Service (`StorageService`)

Thin passthroughs for folder ops and `list_files(folder_id=None)`.

### Routes (`main.py`)

- `GET /folders` → nested folder tree JSON.
- `POST /folders` `{name, parent_id}` → 201 + folder JSON.
- `PATCH /folders/{id}` `{name}` → renamed folder JSON.
- `DELETE /folders/{id}` → 204; 409 if not empty.
- `GET /?folder_id=X` → dashboard scoped to folder (breadcrumb + contents).
- `GET /files?folder_id=X` → filtered JSON list.
- `POST /files/upload?folder_id=X` → upload into folder.
- `POST /files/{id}/move` `{folder_id}` → moved file JSON.

Error mapping: 404 unknown folder/file, 400 invalid name/target, 409 non-empty delete.

## Frontend

Extend the existing TGS3 dark theme; no new dependencies.

- **Sidebar**: replace the static nav list with a collapsible folder tree. Root entry "All Files". Each folder gets a `⋯` menu offering New Subfolder / Rename / Delete (delete disabled state not required; server enforces 409).
- **Breadcrumb**: `All Files › Photos › 2024`, each segment clickable. Rendered from `get_breadcrumb`.
- **Table**: folder rows render above file rows (folder icon, name, item count). "No files" empty state only when a folder is truly empty.
- **Upload**: drop zone gains a destination folder `<select>` populated from the tree (default = current folder).
- **Move**: existing files get a Move action opening a folder picker (including "All Files" for root).
- **JS**: `loadFolderTree()`, `navigate(folderId)`, folder create/rename modal, delete confirm, move picker. Data fetched via `/folders` JSON; file table re-rendered with existing `renderFileList`.

## Behavior Details

- Browsing root shows top-level folders + files with no folder.
- Browsing a folder shows its subfolders + files with that `folder_id`.
- Search stays global (across all folders) — no change.
- Preview and download routes are unchanged and work from any folder.
- Renaming a folder does not affect file paths (files reference folder by id).

## Testing

- **Repository:** create, rename, delete (empty), delete non-empty → 409, move file (incl. to root), breadcrumb, list_files by folder.
- **Service:** passthrough delegation.
- **Web:** tree renders, create → 201 and appears in tree, rename → reflected, delete non-empty → 409, upload with `folder_id`, move endpoint, dashboard breadcrumb present.

## Out of Scope

Tags, favorites, sharing, multi-user auth, folder drag-and-drop, recursive folder delete, file copies.
