let allFilesCache = [];
let currentSort = 'name-asc';
let viewMode = 'list'; // 'list' or 'grid'
let currentFolderId = null;
let currentView = 'home'; // 'home' | 'starred' | 'shared' | 'recent' | 'trash'
let folderModalMode = null;
let folderModalParent = null;
let moveFileIds = [];
let shareFileId = null;
let selectedIds = new Set();

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formatBytes(bytes, decimals = 1) {
  if (!+bytes) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function getDriveBadgeDetails(mimeType, filename = '') {
  const mime = (mimeType || '').toLowerCase();
  const name = filename.toLowerCase();

  if (mime.includes('spreadsheet') || name.endsWith('.xlsx') || name.endsWith('.csv')) {
    return { class: 'icon-sheet', icon: 'ph-file-xls' };
  }
  if (mime.includes('ipynb') || name.endsWith('.py') || name.endsWith('.ipynb')) {
    return { class: 'icon-code', icon: 'ph-code-simple' };
  }
  if (mime.includes('pdf') || name.endsWith('.pdf')) {
    return { class: 'icon-pdf', icon: 'ph-file-pdf' };
  }
  if (mime.startsWith('image/') || name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg')) {
    return { class: 'icon-img', icon: 'ph-image' };
  }
  if (mime.startsWith('video/') || name.endsWith('.mp4')) {
    return { class: 'icon-video', icon: 'ph-video-camera' };
  }
  if (mime.includes('zip') || name.endsWith('.zip')) {
    return { class: 'icon-zip', icon: 'ph-file-zip' };
  }
  return { class: 'icon-doc', icon: 'ph-file-text' };
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function setViewMode(mode) {
  viewMode = mode;
  const listBtn = document.getElementById('btn-view-list');
  const gridBtn = document.getElementById('btn-view-grid');
  const container = document.getElementById('files-view-container');

  if (listBtn && gridBtn && container) {
    if (mode === 'list') {
      listBtn.classList.add('active');
      gridBtn.classList.remove('active');
      container.className = 'files-container list-view';
    } else {
      gridBtn.classList.add('active');
      listBtn.classList.remove('active');
      container.className = 'files-container grid-view';
    }
  }
  renderFileList();
}

function toggleSort(field) {
  if (field === 'name') {
    currentSort = currentSort === 'name-asc' ? 'name-desc' : 'name-asc';
  } else if (field === 'date') {
    currentSort = currentSort === 'date-desc' ? 'date-asc' : 'date-desc';
  }
  renderFileList();
}

function sortFiles(files) {
  return [...files].sort((a, b) => {
    if (currentSort === 'name-asc') return a.name.localeCompare(b.name);
    if (currentSort === 'name-desc') return b.name.localeCompare(a.name);
    return 0;
  });
}

function buildFileActionsMenu(file) {
  const id = file.id;
  if (currentView === 'trash') {
    return `
      <button class="restore-trigger" data-id="${id}"><i class="ph-bold ph-arrow-counter-clockwise"></i> Restore</button>
      <button class="delete-forever-trigger" data-id="${id}" data-name="${escapeHtml(file.name)}"><i class="ph-bold ph-trash"></i> Delete forever</button>
    `;
  }
  return `
    <button class="preview-trigger" data-id="${id}" data-mime="${escapeHtml(file.mime_type || '')}" data-name="${escapeHtml(file.name)}"><i class="ph-bold ph-eye"></i> Preview</button>
    <button class="star-trigger" data-id="${id}" data-starred="${file.starred ? 'true' : 'false'}"><i class="ph-bold ph-star"></i> ${file.starred ? 'Unstar' : 'Star'}</button>
    <button class="move-trigger" data-id="${id}"><i class="ph-bold ph-folder-notch"></i> Move</button>
    <button class="share-trigger" data-id="${id}" data-token="${escapeHtml(file.share_token || '')}" data-name="${escapeHtml(file.name)}"><i class="ph-bold ph-share-network"></i> Share</button>
    <a href="/files/${id}/download"><i class="ph-bold ph-download-simple"></i> Download</a>
    <button class="trash-trigger" data-id="${id}"><i class="ph-bold ph-trash"></i> Move to trash</button>
  `;
}

function folderMenuHtml(folder, { includeOpen = false } = {}) {
  const openBtn = includeOpen
    ? `<button class="folder-open-trigger" data-id="${folder.id}"><i class="ph-bold ph-folder-open"></i> Open</button>`
    : '';
  return `
    ${openBtn}
    <button class="folder-new-trigger" data-id="${folder.id}"><i class="ph-bold ph-folder-plus"></i> New subfolder</button>
    <button class="folder-rename-trigger" data-id="${folder.id}"><i class="ph-bold ph-pencil-simple"></i> Rename</button>
    <button class="folder-star-trigger" data-id="${folder.id}" data-starred="${folder.starred ? 'true' : 'false'}"><i class="ph-bold ph-star"></i> ${folder.starred ? 'Unstar' : 'Star'}</button>
    <button class="folder-delete-trigger" data-id="${folder.id}" data-name="${escapeHtml(folder.name)}"><i class="ph-bold ph-trash"></i> Delete</button>
  `;
}

function renderFileList() {
  const container = document.getElementById('files-view-container');
  if (!container) return;

  let displayFiles = [...allFilesCache];

  const searchInput = document.getElementById("search-input");
  if (searchInput && searchInput.value.trim()) {
    const q = searchInput.value.trim().toLowerCase();
    displayFiles = displayFiles.filter(f => f.name.toLowerCase().includes(q));
  }

  displayFiles = sortFiles(displayFiles);

  if (viewMode === 'list') {
    let rowsHtml = displayFiles.map(file => {
      const badge = getDriveBadgeDetails(file.mime_type, file.name);
      const name = escapeHtml(file.name);
      const starIndicator = file.starred ? '<i class="ph-fill ph-star star-indicator" title="Starred"></i>' : '';
      const checked = selectedIds.has(String(file.id)) ? 'checked' : '';

      return `
        <tr data-id="${file.id}">
          <td><input type="checkbox" class="row-select" data-id="${file.id}" ${checked}></td>
          <td>
            <div class="file-cell">
              <div class="file-type-icon ${badge.class}">
                <i class="ph-fill ${badge.icon}"></i>
              </div>
              <a href="/view/files/${file.id}" class="file-title-link" title="${name}">${name}</a>
              ${starIndicator}
            </div>
          </td>
          <td><span class="file-size-text">${formatBytes(file.size_bytes)}</span></td>
          <td><span class="file-modified-text">${formatDate(file.uploaded_at)}</span></td>
          <td style="text-align: right;">
            <div class="dropdown">
              <button class="action-menu-btn" onclick="toggleDropdown(event, 'file-menu-${file.id}')" title="More actions">
                <i class="ph-bold ph-dots-three-vertical"></i>
              </button>
              <div id="file-menu-${file.id}" class="dropdown-content">
                ${buildFileActionsMenu(file)}
              </div>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    container.innerHTML = `
      <table class="drive-file-table">
        <thead>
          <tr>
            <th class="col-select"><input type="checkbox" id="select-all-checkbox"></th>
            <th class="col-name" onclick="toggleSort('name')">Name <i class="ph-bold ph-caret-down"></i></th>
            <th class="col-size">Size</th>
            <th class="col-modified">Modified</th>
            <th class="col-actions"></th>
          </tr>
        </thead>
        <tbody id="file-table-body">
          ${rowsHtml || '<tr><td colspan="5" style="text-align: center; padding: 40px; color: #5f6368;">No files found</td></tr>'}
        </tbody>
      </table>
    `;
  } else {
    // Grid View
    let gridCardsHtml = displayFiles.map(file => {
      const badge = getDriveBadgeDetails(file.mime_type, file.name);
      const name = escapeHtml(file.name);
      const starIndicator = file.starred ? '<i class="ph-fill ph-star star-indicator" title="Starred"></i>' : '';
      const checked = selectedIds.has(String(file.id)) ? 'checked' : '';

      return `
        <div class="grid-file-card" data-id="${file.id}">
          <input type="checkbox" class="row-select grid-select" data-id="${file.id}" ${checked}>
          <div class="grid-file-header">
            <div class="file-type-icon ${badge.class}">
              <i class="ph-fill ${badge.icon}"></i>
            </div>
            <div class="dropdown">
              <button class="action-menu-btn" onclick="toggleDropdown(event, 'file-menu-${file.id}')" title="More actions">
                <i class="ph-bold ph-dots-three-vertical"></i>
              </button>
              <div id="file-menu-${file.id}" class="dropdown-content">
                ${buildFileActionsMenu(file)}
              </div>
            </div>
          </div>
          <div class="grid-file-title" title="${name}">${name}${starIndicator}</div>
          <div class="grid-file-preview-box">
            <i class="ph-fill ${badge.icon}" style="color: rgba(60,64,67,0.3)"></i>
          </div>
          <div class="grid-file-footer">
            <span>${formatBytes(file.size_bytes)}</span>
          </div>
        </div>
      `;
    }).join("");

    container.innerHTML = gridCardsHtml || '<div style="padding: 40px; color: #5f6368;">No files found</div>';
  }

  updateSelectionUI();
}

async function refreshFiles(query = "") {
  try {
    let url;
    if (query) {
      url = `/files/search?q=${encodeURIComponent(query)}`;
    } else if (currentView !== "home") {
      url = `/files?view=${currentView}`;
    } else {
      url = currentFolderId ? `/files?folder_id=${currentFolderId}` : "/files";
    }
    const response = await fetch(url);
    if (response.status === 401) { window.location.href = "/login"; return; }
    const data = await response.json();
    allFilesCache = Array.isArray(data) ? data : (data.files || []);
    renderFileList();
  } catch (err) {
    console.error("Error refreshing file list:", err);
  }
}

// ---- Selection & bulk actions ----

function toggleSelect(id, checked) {
  if (checked) selectedIds.add(String(id));
  else selectedIds.delete(String(id));
  updateSelectionUI();
}

function toggleSelectAll(checked) {
  document.querySelectorAll('.row-select').forEach((cb) => {
    cb.checked = checked;
    if (checked) selectedIds.add(cb.dataset.id);
    else selectedIds.delete(cb.dataset.id);
  });
  updateSelectionUI();
}

function clearSelection() {
  selectedIds.clear();
  document.querySelectorAll('.row-select').forEach((cb) => { cb.checked = false; });
  updateSelectionUI();
}

function updateSelectionUI() {
  const toolbar = document.getElementById('selection-toolbar');
  if (!toolbar) return;
  const normalBar = document.getElementById('section-title-bar-normal');
  const countEl = document.getElementById('selection-count');
  const count = selectedIds.size;

  toolbar.hidden = count === 0;
  if (normalBar) normalBar.hidden = count > 0;
  if (countEl) countEl.textContent = `${count} selected`;

  const selectAll = document.getElementById('select-all-checkbox');
  if (selectAll) {
    const total = document.querySelectorAll('.row-select').length;
    selectAll.checked = total > 0 && count >= total;
    selectAll.indeterminate = count > 0 && count < total;
  }
}

async function starFileApi(id, enabled) {
  await fetch(`/files/${id}/star`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

async function trashFileApi(id) {
  await fetch(`/files/${id}/trash`, { method: "POST" });
}

async function restoreFileApi(id) {
  await fetch(`/files/${id}/restore`, { method: "POST" });
}

async function deleteForeverApi(id) {
  await fetch(`/files/${id}`, { method: "DELETE" });
}

async function bulkAction(fn) {
  const ids = Array.from(selectedIds);
  for (const id of ids) {
    await fn(id);
  }
  clearSelection();
  await refreshFiles();
}

function bulkDownload() {
  const ids = Array.from(selectedIds);
  ids.forEach((id, i) => {
    setTimeout(() => {
      const a = document.createElement('a');
      a.href = `/files/${id}/download`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      a.remove();
    }, i * 300);
  });
}

async function handleStarToggle(id, currentlyStarred) {
  await starFileApi(id, !currentlyStarred);
  await refreshFiles();
}

async function handleTrash(id) {
  await trashFileApi(id);
  await refreshFiles();
}

async function handleRestore(id) {
  await restoreFileApi(id);
  await refreshFiles();
}

async function handleDeleteForever(id, name) {
  if (!confirm(`Permanently delete "${name}"? This cannot be undone.`)) return;
  await deleteForeverApi(id);
  await refreshFiles();
}

async function handleFolderStarToggle(id, currentlyStarred) {
  await fetch(`/folders/${id}/star`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: !currentlyStarred }),
  });
  window.location.reload();
}

function deleteFolderApi(id) {
  fetch(`/folders/${id}`, { method: "DELETE" }).then((res) => {
    if (res.status === 204) window.location.reload();
    else if (res.status === 409) alert("Folder is not empty.");
  });
}

// ---- Shared trigger handlers (used by row menus AND the context menu) ----

function handleFileTriggerClick(e) {
  const trigger = e.target.closest(".preview-trigger");
  if (trigger) { closeContextMenu(); return openPreview(trigger.dataset.id, trigger.dataset.name, trigger.dataset.mime); }
  const move = e.target.closest(".move-trigger");
  if (move) { closeContextMenu(); return openMoveModal(move.dataset.id); }
  const share = e.target.closest(".share-trigger");
  if (share) { closeContextMenu(); return openShareModal(share.dataset.id, share.dataset.token, share.dataset.name); }
  const star = e.target.closest(".star-trigger");
  if (star) { closeContextMenu(); return handleStarToggle(star.dataset.id, star.dataset.starred === "true"); }
  const trash = e.target.closest(".trash-trigger");
  if (trash) { closeContextMenu(); return handleTrash(trash.dataset.id); }
  const restore = e.target.closest(".restore-trigger");
  if (restore) { closeContextMenu(); return handleRestore(restore.dataset.id); }
  const del = e.target.closest(".delete-forever-trigger");
  if (del) { closeContextMenu(); return handleDeleteForever(del.dataset.id, del.dataset.name); }
}

function handleFolderTriggerClick(e) {
  const open = e.target.closest(".folder-open-trigger");
  if (open) { closeContextMenu(); return navigate(open.dataset.id); }
  const newSub = e.target.closest(".folder-new-trigger");
  if (newSub) { closeContextMenu(); return openFolderModal("create", newSub.dataset.id); }
  const rename = e.target.closest(".folder-rename-trigger");
  if (rename) { closeContextMenu(); return openFolderModal("rename", rename.dataset.id); }
  const star = e.target.closest(".folder-star-trigger");
  if (star) { closeContextMenu(); return handleFolderStarToggle(star.dataset.id, star.dataset.starred === "true"); }
  const del = e.target.closest(".folder-delete-trigger");
  if (del) {
    closeContextMenu();
    if (!confirm(`Delete folder "${del.dataset.name}"? Only empty folders can be deleted.`)) return;
    return deleteFolderApi(del.dataset.id);
  }
}

// ---- Right-click context menu ----

function openContextMenu(x, y, itemsHtml) {
  const menu = document.getElementById('context-menu');
  if (!menu) return;
  menu.innerHTML = itemsHtml;
  menu.style.display = 'block';
  menu.style.left = '0px';
  menu.style.top = '0px';
  const rect = menu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - rect.width - 8);
  const top = Math.min(y, window.innerHeight - rect.height - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
}

function closeContextMenu() {
  const menu = document.getElementById('context-menu');
  if (menu) menu.style.display = 'none';
}

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

function openPreview(fileId, fileName, mimeType) {
  const overlay = document.getElementById("preview-overlay");
  const body = document.getElementById("preview-body");
  const nameEl = document.getElementById("preview-name");
  const download = document.getElementById("preview-download");
  const src = `/files/${fileId}/preview`;

  nameEl.textContent = fileName;
  download.href = `/files/${fileId}/download`;

  if (mimeType && mimeType.startsWith("image/")) {
    body.innerHTML = `<img class="preview-image" src="${src}" alt="Preview">`;
  } else {
    body.innerHTML = `<iframe class="preview-frame" src="${src}" title="Preview"></iframe>`;
  }

  overlay.hidden = false;
}

function closePreview() {
  const overlay = document.getElementById("preview-overlay");
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  document.getElementById("preview-body").innerHTML = "";
}

function buildTreeHtml(nodes, depth = 0) {
  return nodes.map((node) => `
    <div class="tree-node" style="--depth: ${depth}">
      <div class="tree-row">
        <button type="button" class="tree-folder" data-nav="${node.id}" title="${escapeHtml(node.name)}">
          <i class="ph-fill ph-folder" style="color: #1a73e8;"></i>
          <span>${escapeHtml(node.name)}</span>
          ${node.starred ? '<i class="ph-fill ph-star star-indicator" title="Starred"></i>' : ''}
        </button>
        <button type="button" class="tree-menu" data-menu="${node.id}" data-starred="${node.starred ? 'true' : 'false'}" title="Options">
          <i class="ph-bold ph-dots-three-vertical"></i>
        </button>
      </div>
      ${node.children && node.children.length ? buildTreeHtml(node.children, depth + 1) : ''}
    </div>
  `).join("");
}

async function loadFolderTree() {
  try {
    const res = await fetch("/folders");
    const tree = await res.json();
    const container = document.getElementById("folder-tree");
    if (!container) return;
    container.innerHTML = buildTreeHtml(tree);
  } catch (err) {
    console.error("Error loading folder tree:", err);
  }
}

function navigate(folderId) {
  const url = folderId ? `/?folder_id=${folderId}` : "/";
  window.location.href = url;
}

function folderOptionsHtml() {
  const container = document.getElementById("folder-tree");
  if (!container) return "";
  const options = ['<option value="">All Files</option>'];
  container.querySelectorAll(".tree-folder").forEach((btn) => {
    const name = btn.querySelector("span").textContent;
    const depth = parseInt(btn.closest(".tree-node").style.getPropertyValue("--depth") || "0", 10);
    options.push(`<option value="${btn.dataset.nav}">${"&nbsp;".repeat(depth * 2)}${escapeHtml(name)}</option>`);
  });
  return options.join("");
}

function openMoveModal(fileId, bulkIds) {
  moveFileIds = bulkIds && bulkIds.length ? bulkIds : [fileId];
  const select = document.getElementById("move-modal-folder");
  select.innerHTML = folderOptionsHtml();
  document.getElementById("move-modal").hidden = false;
}

function closeMoveModal() {
  document.getElementById("move-modal").hidden = true;
  moveFileIds = [];
}

async function saveMove() {
  if (!moveFileIds.length) return;
  const folderId = document.getElementById("move-modal-folder").value || null;
  try {
    for (const id of moveFileIds) {
      const res = await fetch(`/files/${id}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: folderId }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to move file.");
      }
    }
    closeMoveModal();
    clearSelection();
    await refreshFiles();
  } catch (err) {
    alert(err.message || "Failed to move file(s).");
  }
}

function openFolderModal(mode, parentId) {
  folderModalMode = mode;
  folderModalParent = parentId ?? null;
  document.getElementById("folder-modal-title").textContent = mode === "create" ? "New folder" : "Rename folder";
  document.getElementById("folder-modal-name").value = "";
  document.getElementById("folder-modal").hidden = false;
  document.getElementById("folder-modal-name").focus();
}

function closeFolderModal() {
  document.getElementById("folder-modal").hidden = true;
  folderModalMode = null;
  folderModalParent = null;
}

async function saveFolder() {
  const name = document.getElementById("folder-modal-name").value.trim();
  if (!name) return;
  const mode = folderModalMode;
  const body = mode === "rename" ? { name } : { name, parent_id: folderModalParent };
  const url = mode === "rename" ? `/folders/${folderModalParent}` : "/folders";
  const res = await fetch(url, {
    method: mode === "rename" ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    closeFolderModal();
    await loadFolderTree();
    window.location.reload();
  } else {
    const err = await res.json();
    alert(err.detail || "Failed to save folder.");
  }
}

function openShareModal(fileId, shareToken, fileName) {
  shareFileId = fileId;
  document.getElementById("share-modal-filename").textContent = fileName;
  const toggle = document.getElementById("share-modal-toggle");
  toggle.checked = !!shareToken;
  updateShareModalUI(shareToken);
  document.getElementById("share-modal").hidden = false;
}

function closeShareModal() {
  document.getElementById("share-modal").hidden = true;
  shareFileId = null;
}

function updateShareModalUI(token) {
  const container = document.getElementById("share-link-container");
  const input = document.getElementById("share-modal-link");
  const aiInput = document.getElementById("share-modal-link-ai");
  const fileName = document.getElementById("share-modal-filename").textContent;

  if (token) {
    container.style.display = "block";
    input.value = window.location.origin + "/s/" + token;
    aiInput.value = window.location.origin + "/s/" + token + "/" + encodeURIComponent(fileName);
  } else {
    container.style.display = "none";
    input.value = "";
    aiInput.value = "";
  }
}

async function toggleShare() {
  if (!shareFileId) return;
  const enable = document.getElementById("share-modal-toggle").checked;
  const res = await fetch(`/files/${shareFileId}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: enable }),
  });
  if (res.ok) {
    const file = await res.json();
    updateShareModalUI(file.share_token);
    // Update local cache if available
    if (typeof allFilesCache !== 'undefined') {
      const idx = allFilesCache.findIndex(f => f.id === file.id);
      if (idx >= 0) allFilesCache[idx] = file;
      if (typeof renderFileList === 'function') renderFileList();
    }
  } else {
    alert("Failed to update share settings.");
    document.getElementById("share-modal-toggle").checked = !enable; // revert
  }
}

function copyShareLink() {
  const input = document.getElementById("share-modal-link");
  input.select();
  document.execCommand("copy");
  const btn = document.getElementById("share-modal-copy");
  const original = btn.innerHTML;
  btn.innerHTML = '<i class="ph-bold ph-check"></i> Copied';
  setTimeout(() => btn.innerHTML = original, 2000);
}

function copyShareLinkAi() {
  const input = document.getElementById("share-modal-link-ai");
  input.select();
  document.execCommand("copy");
  const btn = document.getElementById("share-modal-copy-ai");
  const original = btn.innerHTML;
  btn.innerHTML = '<i class="ph-bold ph-check"></i> Copied';
  setTimeout(() => btn.innerHTML = original, 2000);
}

function initTheme() {
  const savedTheme = localStorage.getItem('drive_theme') || 'light';
  applyTheme(savedTheme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('drive_theme', theme);
  const icon = document.getElementById('theme-toggle-icon');
  const btn = document.getElementById('theme-toggle-btn');
  if (icon) {
    if (theme === 'dark') {
      icon.className = 'ph-bold ph-sun';
      if (btn) btn.title = 'Switch to Light theme';
    } else {
      icon.className = 'ph-bold ph-moon';
      if (btn) btn.title = 'Switch to Dark theme';
    }
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

async function syncChannel() {
  const icon = document.getElementById('sync-icon');
  if (icon) icon.classList.add('ph-spin');
  try {
    const res = await fetch('/sync', { method: 'POST' });
    if (res.ok) {
      await refreshFiles();
      window.location.reload();
    } else {
      alert('Sync failed.');
    }
  } catch (err) {
    alert('Sync error: ' + err.message);
  } finally {
    if (icon) icon.classList.remove('ph-spin');
  }
}


document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  document.getElementById("theme-toggle-btn")?.addEventListener("click", toggleTheme);
  document.getElementById("theme-toggle-btn-immersive")?.addEventListener("click", toggleTheme);
  document.getElementById("immersive-menu-trigger")?.addEventListener("click", (e) => toggleDropdown(e, "immersiveMenu"));
  document.getElementById("immersiveMenu")?.addEventListener("click", (e) => {
    const share = e.target.closest(".share-trigger-immersive");
    if (share) return openShareModal(share.dataset.id, share.dataset.token, share.dataset.name);
  });

  const searchInput = document.getElementById("search-input");
  const fileInputHeader = document.getElementById("file-input-header");
  const fileInputDrop = document.getElementById("file-input-drop");
  const dropZone = document.getElementById("drop-zone");
  const newBtn = document.getElementById("btn-new-menu-trigger");
  const newDropdown = document.getElementById("new-dropdown-menu");

  const appFrame = document.querySelector(".drive-app");
  currentFolderId = appFrame?.dataset.currentFolder ? parseInt(appFrame.dataset.currentFolder, 10) : null;
  currentView = appFrame?.dataset.currentView || "home";

  if (appFrame) {
    refreshFiles();
    loadFolderTree();
  }

  // Toggle + New Menu
  if (newBtn && newDropdown) {
    newBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      newDropdown.hidden = !newDropdown.hidden;
    });

    document.addEventListener("click", () => {
      newDropdown.hidden = true;
    });
  }

  searchInput?.addEventListener("input", () => {
    renderFileList();
  });

  fileInputHeader?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      Array.from(e.target.files).forEach(file => uploadFile(file));
    }
  });

  fileInputDrop?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      Array.from(e.target.files).forEach(file => uploadFile(file));
    }
  });

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

  if (dropZone) {
    ["dragenter", "dragover"].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add("dragover");
      }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("dragover");
      }, false);
    });

    dropZone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        Array.from(files).forEach(file => uploadFile(file));
      }
    });
  }

  const filesView = document.getElementById("files-view-container");
  filesView?.addEventListener("click", (e) => {
    if (e.target.closest(".dropdown")) return handleFileTriggerClick(e);
    if (e.target.closest(".row-select")) return;
    const card = e.target.closest(".grid-file-card");
    if (card) window.location.href = `/view/files/${card.dataset.id}`;
  });
  filesView?.addEventListener("change", (e) => {
    const cb = e.target.closest(".row-select");
    if (cb) return toggleSelect(cb.dataset.id, cb.checked);
    if (e.target.id === "select-all-checkbox") return toggleSelectAll(e.target.checked);
  });
  filesView?.addEventListener("contextmenu", (e) => {
    const row = e.target.closest("[data-id]");
    if (!row || !filesView.contains(row)) return;
    const file = allFilesCache.find(f => String(f.id) === String(row.dataset.id));
    if (!file) return;
    e.preventDefault();
    openContextMenu(e.clientX, e.clientY, buildFileActionsMenu(file));
  });

  const foldersGrid = document.getElementById("folders-grid-container");
  foldersGrid?.addEventListener("click", (e) => {
    if (e.target.closest(".dropdown")) return handleFolderTriggerClick(e);
    const card = e.target.closest(".folder-card");
    if (card) window.location.href = `/?folder_id=${card.dataset.id}`;
  });
  foldersGrid?.addEventListener("contextmenu", (e) => {
    const card = e.target.closest(".folder-card");
    if (!card) return;
    e.preventDefault();
    const starTrigger = card.querySelector(".folder-star-trigger");
    const folder = {
      id: card.dataset.id,
      name: card.dataset.name,
      starred: starTrigger?.dataset.starred === "true",
    };
    openContextMenu(e.clientX, e.clientY, folderMenuHtml(folder, { includeOpen: true }));
  });

  document.getElementById("select-all-checkbox")?.addEventListener("change", (e) => toggleSelectAll(e.target.checked));
  document.getElementById("selection-clear")?.addEventListener("click", clearSelection);
  document.getElementById("selection-star")?.addEventListener("click", () => bulkAction((id) => starFileApi(id, true)));
  document.getElementById("selection-move")?.addEventListener("click", () => openMoveModal(null, Array.from(selectedIds)));
  document.getElementById("selection-download")?.addEventListener("click", bulkDownload);
  document.getElementById("selection-trash")?.addEventListener("click", () => {
    if (!confirm(`Move ${selectedIds.size} item(s) to trash?`)) return;
    bulkAction(trashFileApi);
  });
  document.getElementById("selection-restore")?.addEventListener("click", () => bulkAction(restoreFileApi));
  document.getElementById("selection-delete-forever")?.addEventListener("click", () => {
    if (!confirm(`Permanently delete ${selectedIds.size} item(s)? This cannot be undone.`)) return;
    bulkAction(deleteForeverApi);
  });

  document.getElementById("btn-empty-trash")?.addEventListener("click", async () => {
    if (!confirm("Permanently delete everything in Trash? This cannot be undone.")) return;
    await fetch("/trash/empty", { method: "POST" });
    await refreshFiles();
  });

  document.getElementById("context-menu")?.addEventListener("click", (e) => {
    handleFileTriggerClick(e);
    handleFolderTriggerClick(e);
  });

  const folderTree = document.getElementById("folder-tree");
  folderTree?.addEventListener("click", (e) => {
    const nav = e.target.closest(".tree-folder");
    if (nav) return navigate(nav.dataset.nav);
    const menu = e.target.closest(".tree-menu");
    if (menu) {
      e.stopPropagation();
      const id = menu.dataset.menu;
      const name = menu.closest(".tree-row")?.querySelector("span")?.textContent || "this folder";
      const starred = menu.dataset.starred === "true";
      const rect = menu.getBoundingClientRect();
      openContextMenu(rect.left, rect.bottom, folderMenuHtml({ id, name, starred }, { includeOpen: true }));
    }
  });

  document.getElementById("btn-new-folder")?.addEventListener("click", () => openFolderModal("create", currentFolderId));
  document.getElementById("folder-modal-close")?.addEventListener("click", closeFolderModal);
  document.getElementById("folder-modal-cancel")?.addEventListener("click", closeFolderModal);
  document.getElementById("folder-modal-save")?.addEventListener("click", saveFolder);
  document.getElementById("folder-modal-name")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveFolder();
  });
  document.getElementById("move-modal-close")?.addEventListener("click", closeMoveModal);
  document.getElementById("move-modal-cancel")?.addEventListener("click", closeMoveModal);
  document.getElementById("move-modal-save")?.addEventListener("click", saveMove);
  document.getElementById("folder-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeFolderModal();
  });
  document.getElementById("move-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeMoveModal();
  });

  document.getElementById("preview-close")?.addEventListener("click", closePreview);
  document.getElementById("preview-overlay")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closePreview();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closePreview(); closeContextMenu(); }
  });
  document.querySelector(".drive-main-workspace")?.addEventListener("scroll", closeContextMenu);
  window.addEventListener("resize", closeContextMenu);

  document.getElementById("share-modal-close")?.addEventListener("click", closeShareModal);
  document.getElementById("share-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeShareModal();
  });
  document.getElementById("share-modal-toggle")?.addEventListener("change", toggleShare);
  document.getElementById("share-modal-copy")?.addEventListener("click", copyShareLink);
  document.getElementById("share-modal-copy-ai")?.addEventListener("click", copyShareLinkAi);
});

window.toggleDropdown = function(event, menuId) {
  event.stopPropagation();
  closeContextMenu();
  const menu = document.getElementById(menuId);
  const isShowing = menu.classList.contains("show");

  // Close all open dropdowns
  const dropdowns = document.getElementsByClassName("dropdown-content");
  for (let i = 0; i < dropdowns.length; i++) {
    dropdowns[i].classList.remove('show');
  }

  // Toggle the clicked one
  if (!isShowing) {
    menu.classList.add("show");
  }
};

window.addEventListener("click", function(event) {
  if (!event.target.closest('.dropdown')) {
    const dropdowns = document.getElementsByClassName("dropdown-content");
    for (let i = 0; i < dropdowns.length; i++) {
      dropdowns[i].classList.remove('show');
    }
  }
  if (!event.target.closest('#context-menu')) {
    closeContextMenu();
  }
});
