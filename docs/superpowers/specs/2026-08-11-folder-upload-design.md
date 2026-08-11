# TGS3 Folder Upload Design

**Goal:** Add a "folder upload" option to the desktop and mobile apps so users can pick a folder and have its full subfolder tree recreated in TGS3, with each file uploaded into its matching folder.

**Approach:** Pure client-side. Reuse the existing `POST /folders` and `POST /files/upload` APIs. No backend changes.

## Current behavior

- Desktop (`app/static/app.js`): New menu → "File upload" (`file-input-header`) and drop zone (`file-input-drop`) upload each selected file via `uploadFile(file)` → `POST /files/upload?folder_id=<currentFolderId>`.
- Mobile (`mobile/mobile.js`, WIP uncommitted): FAB → create modal → upload (`m-hidden-file-input`) → `uploadFiles()` → `POST /files/upload?folder_id=<currentFolderId>`.
- Folder creation: `POST /folders` `{name, parent_id}`. **No duplicate-name check** — every call creates a fresh folder.
- There is no backend endpoint for folder upload; browsers expose folder selection via `<input type="file" webkitdirectory multiple>`, and each file carries a `webkitRelativePath` like `Photos/2026/vacation.jpg`.

## Changes

### Desktop

`app/templates/index.html`:
- Add "Folder upload" item to the New menu dropdown (between "File upload" and "New folder").
- Add hidden `<input id="folder-input-header" type="file" webkitdirectory multiple style="display:none">`.
- Add hidden `<input id="folder-input-drop" type="file" webkitdirectory multiple style="display:none">` inside the drop zone.

`app/static/app.js`:
- Add `uploadFolder(fileList, rootParentId)`:
  1. Group files by directory path derived from `file.webkitRelativePath` (strip the file name; empty path = root of the selection).
  2. For each unique directory path, walk its parts top-down, creating each missing folder with `POST /folders {name, parent_id}`. Before creating, fetch the existing children of the parent (via the existing folder-tree API `GET /folders`) and reuse a folder whose name matches (no duplicates).
  3. Upload each file to its leaf folder id via the existing upload path (`uploadFile(file, folderId)`), with `rootParentId` used as the upload target for files at the selection root.
- Wire `folder-input-header` and `folder-input-drop` change events to call `uploadFolder(files, currentFolderId)`.
- Sequential processing: create folders top-down, then upload files one at a time (matches current Telegram one-by-one behavior).

### Mobile (WIP `mobile/mobile.js` + `mobile/mobile.html`)

- Add "Folder upload" option to the create modal.
- Add hidden `<input id="m-hidden-folder-input" type="file" webkitdirectory multiple>`.
- Reuse the same tree-walk logic (duplicated in `mobile.js` since it is standalone JS): `ensureFolderPath` helpers, `uploadFolder`, sequential folder create + file upload, toast feedback.
- Caveat: mobile browsers generally cannot select whole folders; this works on Android Chrome (and iOS via limited support). Files simply won't appear on unsupported browsers — no error path needed beyond existing upload toast.

### Duplicate-folder handling

- If a folder with the same name already exists under the target parent, reuse it instead of creating a new one. This matches typical cloud-drive behavior and avoids duplicate empty folders on re-upload.

### Error handling

- If `POST /folders` fails for a path, abort remaining folder creates for that path and surface a toast/alert; continue uploading files whose folders were resolved successfully.
- If an individual file upload fails, surface the existing failure message and continue with the next file.

### Testing

- No new Python tests (pure client-side). Existing 57 tests must stay green.
- Manual verification: upload a nested folder on desktop and mobile; confirm the tree and files land in the correct folders; re-upload the same folder and confirm no duplicate folders are created.

## Non-goals

- No server-side batch endpoint or zip extraction.
- No parallel uploads or upload queue/manager.
- No changes to the storage/Telegram layer.
