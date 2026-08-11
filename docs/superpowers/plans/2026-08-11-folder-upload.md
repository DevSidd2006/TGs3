# TGS3 Folder Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "folder upload" option to the desktop and mobile apps that recreates the selected folder's full subfolder tree in TGS3 and uploads each file into its matching folder.

**Architecture:** Pure client-side. Each app gets a `<input type="file" webkitdirectory multiple>`. A JS helper walks each file's `webkitRelativePath`, reusing existing folders by name+parent (via `GET /folders`) or creating missing ones (`POST /folders {name, parent_id}`), then uploads files via the existing `POST /files/upload?folder_id=X`. No backend changes.

**Tech Stack:** Vanilla JS, existing FastAPI routes (`GET /folders`, `POST /folders`, `POST /files/upload`).

**Spec:** `docs/superpowers/specs/2026-08-11-folder-upload-design.md`

**Baseline:** Existing 57 tests must stay green. Run with `/home/devisdd/s3/.venv/bin/pytest tests -q`.

**IMPORTANT git state:** There are UNCOMMITTED WIP changes in `app/main.py`, `mobile/mobile.css`, `mobile/mobile.html`, `mobile/mobile.js` (a mobile redesign, already live on the running server). This plan builds on top of that WIP. Task 2's commit therefore includes those WIP files together with the folder-upload changes — do NOT try to separate them.

---

### Task 1: Desktop folder upload

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`

- [ ] **Step 1: Add "Folder upload" to the New menu**

In `app/templates/index.html`, inside the `#new-dropdown-menu` div (currently lines 46-53), insert a folder-upload item between "File upload" and "New folder":

```html
        <div class="new-dropdown" id="new-dropdown-menu" hidden>
          <button type="button" class="dropdown-item" onclick="document.getElementById('file-input-header').click()">
            <i class="ph-bold ph-file-arrow-up"></i> File upload
          </button>
          <button type="button" class="dropdown-item" onclick="document.getElementById('folder-input-header').click()">
            <i class="ph-bold ph-folder-open"></i> Folder upload
          </button>
          <button type="button" class="dropdown-item" onclick="openFolderModal('create', currentFolderId)">
            <i class="ph-bold ph-folder-plus"></i> New folder
          </button>
        </div>
```

- [ ] **Step 2: Add the desktop folder input for the New menu**

In `app/templates/index.html`, directly after the line `<input id="file-input-header" type="file" style="display: none;" multiple>` (line 56), add:

```html
      <input id="folder-input-header" type="file" webkitdirectory multiple style="display: none;">
```

- [ ] **Step 3: Add the folder input to the drop zone**

In `app/templates/index.html`, the drop zone block (lines 107-113) currently ends with `<input id="file-input-drop" type="file" multiple style="display: none;">`. Replace that line with:

```html
        <input id="file-input-drop" type="file" multiple style="display: none;">
        <input id="folder-input-drop" type="file" webkitdirectory multiple style="display: none;">
```

- [ ] **Step 4: Refactor `uploadFile` to accept an optional folder id**

In `app/static/app.js`, replace the `uploadFile` function (lines 202-220):

```javascript
async function uploadFile(file, folderId = null) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const targetFolderId = folderId ?? currentFolderId;
    const folderParam = targetFolderId ? `?folder_id=${targetFolderId}` : "";
    const response = await fetch(`/files/upload${folderParam}`, {
      method: "POST",
      body: formData,
    });
    if (response.ok) {
      await refreshFiles();
    } else {
      alert("Failed to upload file.");
    }
  } catch (err) {
    console.error("Upload error:", err);
  }
}
```

- [ ] **Step 5: Add folder-upload helpers**

In `app/static/app.js`, add these functions immediately after `uploadFile` (after line 220):

```javascript
async function findChildFolder(folderId, name) {
  const res = await fetch("/folders");
  if (!res.ok) return null;
  const tree = await res.json();
  const findNode = (nodes, id) => {
    for (const n of nodes) {
      if (n.id === id) return n;
      if (n.children) {
        const found = findNode(n.children, id);
        if (found) return found;
      }
    }
    return null;
  };
  const node = findNode(tree, folderId);
  const children = folderId ? (node ? node.children || [] : []) : tree;
  return children.find((c) => c.name === name) || null;
}

async function ensureFolderPath(parts, rootParentId) {
  let parentId = rootParentId;
  for (const part of parts) {
    const existing = await findChildFolder(parentId, part);
    if (existing) {
      parentId = existing.id;
      continue;
    }
    const res = await fetch("/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: part, parent_id: parentId }),
    });
    if (!res.ok) throw new Error(`Failed to create folder ${part}`);
    const folder = await res.json();
    parentId = folder.id;
  }
  return parentId;
}

async function uploadFolder(fileList) {
  const rootParentId = currentFolderId;
  const grouped = {};
  for (const file of Array.from(fileList)) {
    const rel = file.webkitRelativePath || file.name;
    const parts = rel.split("/");
    parts.pop();
    const key = parts.join("/");
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(file);
  }
  const folderIdCache = {};
  for (const key of Object.keys(grouped)) {
    const parts = key ? key.split("/") : [];
    let leafId = rootParentId;
    if (parts.length) {
      if (!(key in folderIdCache)) {
        try {
          folderIdCache[key] = await ensureFolderPath(parts, rootParentId);
        } catch (err) {
          alert("Failed to create folder structure. See console for details.");
          continue;
        }
      }
      leafId = folderIdCache[key];
    }
    for (const file of grouped[key]) {
      await uploadFile(file, leafId);
    }
  }
}
```

- [ ] **Step 6: Wire the folder inputs**

In `app/static/app.js`, in the `DOMContentLoaded` handler, after the `fileInputDrop` change handler (after line 443), add:

```javascript
  const folderInputHeader = document.getElementById("folder-input-header");
  const folderInputDrop = document.getElementById("folder-input-drop");

  folderInputHeader?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadFolder(e.target.files);
    }
    e.target.value = "";
  });

  folderInputDrop?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadFolder(e.target.files);
    }
    e.target.value = "";
  });
```

- [ ] **Step 7: Verify JS syntax**

Run: `gjs-console -c "$(cat app/static/app.js)" 2>&1 | head -3`
Expected: a runtime error mentioning `document` is not defined (this confirms the file parsed); a syntax error would be reported differently.

- [ ] **Step 8: Run full test suite**

Run: `/home/devisdd/s3/.venv/bin/pytest tests -q`
Expected: 57 passed, 0 failures (no Python changes; must stay green).

- [ ] **Step 9: Commit**

```bash
git add app/templates/index.html app/static/app.js
git commit -m "feat: add folder upload to desktop UI"
```

---

### Task 2: Mobile folder upload (on top of WIP)

**Files:**
- Modify: `mobile/mobile.html`
- Modify: `mobile/mobile.js`
- (Also commits pre-existing WIP: `app/main.py`, `mobile/mobile.css`)

- [ ] **Step 1: Add "Folder upload" option to the create sheet**

In `mobile/mobile.html`, the create modal's `.m-sheet-grid` (lines 107-120) currently has Folder, Upload, Scan. Add a fourth option after the Upload button:

```html
        <button class="m-sheet-option" id="m-opt-upload-folder">
          <div class="option-icon bg-blue"><i class="ph-bold ph-folder-open"></i></div>
          <span>Folder upload</span>
        </button>
```

- [ ] **Step 2: Add the mobile folder input**

In `mobile/mobile.html`, replace the line `<input type="file" id="m-hidden-file-input" multiple hidden>` with:

```html
  <input type="file" id="m-hidden-file-input" multiple hidden>
  <input type="file" id="m-hidden-folder-input" webkitdirectory multiple hidden>
```

- [ ] **Step 3: Add folder-upload helpers**

In `mobile/mobile.js`, add these functions after `uploadFiles` (after line 175):

```javascript
async function findChildFolder(folderId, name) {
  const res = await fetch("/folders");
  if (!res.ok) return null;
  const tree = await res.json();
  const findNode = (nodes, id) => {
    for (const n of nodes) {
      if (n.id === id) return n;
      if (n.children) {
        const found = findNode(n.children, id);
        if (found) return found;
      }
    }
    return null;
  };
  const node = findNode(tree, folderId);
  const children = folderId ? (node ? node.children || [] : []) : tree;
  return children.find((c) => c.name === name) || null;
}

async function ensureFolderPath(parts, rootParentId) {
  let parentId = rootParentId;
  for (const part of parts) {
    const existing = await findChildFolder(parentId, part);
    if (existing) {
      parentId = existing.id;
      continue;
    }
    const res = await fetch("/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: part, parent_id: parentId }),
    });
    if (!res.ok) throw new Error(`Failed to create folder ${part}`);
    const folder = await res.json();
    parentId = folder.id;
  }
  return parentId;
}

async function uploadFolder(fileList) {
  const rootParentId = currentFolderId;
  const grouped = {};
  for (const file of Array.from(fileList)) {
    const rel = file.webkitRelativePath || file.name;
    const parts = rel.split("/");
    parts.pop();
    const key = parts.join("/");
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(file);
  }
  const folderIdCache = {};
  for (const key of Object.keys(grouped)) {
    const parts = key ? key.split("/") : [];
    let leafId = rootParentId;
    if (parts.length) {
      if (!(key in folderIdCache)) {
        try {
          folderIdCache[key] = await ensureFolderPath(parts, rootParentId);
        } catch (err) {
          showToast("Failed to create folder structure");
          continue;
        }
      }
      leafId = folderIdCache[key];
    }
    for (const file of grouped[key]) {
      const formData = new FormData();
      formData.append("file", file);
      const folderParam = leafId ? `?folder_id=${leafId}` : "";
      try {
        showToast(`Uploading ${file.name}...`);
        const res = await fetch(`/files/upload${folderParam}`, { method: "POST", body: formData });
        showToast(res.ok ? `Uploaded ${file.name}` : `Failed to upload ${file.name}`);
      } catch (err) {
        showToast("Upload error");
      }
    }
  }
  await refreshFiles();
  await loadFolderTree();
}
```

- [ ] **Step 4: Wire the folder option and input**

In `mobile/mobile.js`, in the `DOMContentLoaded` handler, after the `m-hidden-file-input` change handler (after line 253), add:

```javascript
  document.getElementById("m-opt-upload-folder")?.addEventListener("click", () => {
    closeCreateModal();
    document.getElementById("m-hidden-folder-input").click();
  });
  document.getElementById("m-hidden-folder-input")?.addEventListener("change", (e) => {
    if (e.target.files.length) uploadFolder(e.target.files);
    e.target.value = "";
  });
```

- [ ] **Step 5: Verify JS syntax**

Run: `gjs-console -c "$(cat mobile/mobile.js)" 2>&1 | head -3`
Expected: a runtime error mentioning `document` is not defined (confirms parse OK).

- [ ] **Step 6: Run full test suite**

Run: `/home/devisdd/s3/.venv/bin/pytest tests -q`
Expected: 57 passed, 0 failures.

- [ ] **Step 7: Commit (includes WIP files)**

```bash
git add mobile/mobile.html mobile/mobile.js app/main.py mobile/mobile.css
git commit -m "feat: add folder upload to mobile app"
```

---

### Task 3: Manual verification

- [ ] **Step 1: Restart server**

```bash
cd /home/devisdd/s3
pkill -f "uvicorn app.asgi:app" || true
nohup .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000 > .data/uvicorn.log 2>&1 &
```

- [ ] **Step 2: Verify pages still load**

```bash
curl -s -c /tmp/cj -d "username=admin&password=demo1234" -o /dev/null -w "login:%{http_code}\n" http://localhost:8000/login
curl -s -b /tmp/cj -o /dev/null -w "root:%{http_code}\n" http://localhost:8000/
curl -s -b /tmp/cj -o /dev/null -w "mobile:%{http_code}\n" http://localhost:8000/mobile
```
Expected: `login:303`, `root:200`, `mobile:200`.

- [ ] **Step 3: Manual browser check (desktop)**

Open `http://localhost:8000/` (logged in). Click New → **Folder upload**, pick a local folder with subfolders. Confirm: the tree is recreated, files land in the correct folders, and re-uploading the same folder does NOT create duplicate folders.

- [ ] **Step 4: Manual browser check (mobile)**

Open `http://localhost:8000/mobile` (logged in, Android Chrome). FAB → **Folder upload**, pick a folder. Confirm tree + files land correctly.
