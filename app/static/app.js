let allFilesCache = [];
let currentCategory = 'all';
let currentSort = 'name-asc';
let viewMode = 'list'; // 'list' or 'grid'
let currentFolderId = null;
let folderModalMode = null;
let folderModalParent = null;
let moveFileId = null;

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

function filterCategory(cat) {
  currentCategory = cat;
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.category === cat);
  });

  const heading = document.getElementById('page-heading');
  if (heading) {
    heading.textContent = 'Welcome to TGS3';
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

      return `
        <tr>
          <td>
            <div class="file-cell">
              <div class="file-type-icon ${badge.class}">
                <i class="ph-fill ${badge.icon}"></i>
              </div>
              <a href="/view/files/${file.id}" class="file-title-link" title="${file.name}">${file.name}</a>
            </div>
          </td>
          <td><span class="file-size-text">${formatBytes(file.size_bytes)}</span></td>
          <td><span class="file-modified-text">${formatDate(file.uploaded_at)}</span></td>
          <td style="text-align: right;">
            <button class="action-menu-btn preview-trigger" data-id="${file.id}" data-mime="${file.mime_type || ''}" data-name="${file.name}" title="Preview">
              <i class="ph-bold ph-eye"></i>
            </button>
            <button class="action-menu-btn move-trigger" data-id="${file.id}" title="Move">
              <i class="ph-bold ph-folder-notch"></i>
            </button>
          </td>
        </tr>
      `;
    }).join("");

    container.innerHTML = `
      <table class="drive-file-table">
        <thead>
          <tr>
            <th class="col-name" onclick="toggleSort('name')">Name <i class="ph-bold ph-caret-down"></i></th>
            <th class="col-size">Size</th>
            <th class="col-modified">Modified</th>
            <th class="col-actions"></th>
          </tr>
        </thead>
        <tbody id="file-table-body">
          ${rowsHtml || '<tr><td colspan="4" style="text-align: center; padding: 40px; color: #5f6368;">No files found</td></tr>'}
        </tbody>
      </table>
    `;
  } else {
    // Grid View
    let gridCardsHtml = displayFiles.map(file => {
      const badge = getDriveBadgeDetails(file.mime_type, file.name);

      return `
        <div class="grid-file-card" onclick="location.href='/view/files/${file.id}'">
          <div class="grid-file-header">
            <div class="file-type-icon ${badge.class}">
              <i class="ph-fill ${badge.icon}"></i>
            </div>
            <button class="action-menu-btn preview-trigger" data-id="${file.id}" data-mime="${file.mime_type || ''}" data-name="${file.name}" onclick="event.stopPropagation();">
              <i class="ph-bold ph-dots-three-vertical"></i>
            </button>
          </div>
          <div class="grid-file-title" title="${file.name}">${file.name}</div>
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
}

async function refreshFiles(query = "") {
  try {
    const url = query
      ? `/files/search?q=${encodeURIComponent(query)}`
      : `/files?folder_id=${currentFolderId || ""}`;
    const response = await fetch(url);
    allFilesCache = await response.json();
    renderFileList();
  } catch (err) {
    console.error("Error refreshing file list:", err);
  }
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
        <button type="button" class="tree-folder" data-nav="${node.id}" title="${node.name}">
          <i class="ph-fill ph-folder" style="color: #1a73e8;"></i>
          <span>${node.name}</span>
        </button>
        <button type="button" class="tree-menu" data-menu="${node.id}" title="Options">
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
    options.push(`<option value="${btn.dataset.nav}">${"&nbsp;".repeat(depth * 2)}${name}</option>`);
  });
  return options.join("");
}

function openMoveModal(fileId) {
  moveFileId = fileId;
  const select = document.getElementById("move-modal-folder");
  select.innerHTML = folderOptionsHtml();
  document.getElementById("move-modal").hidden = false;
}

function closeMoveModal() {
  document.getElementById("move-modal").hidden = true;
  moveFileId = null;
}

async function saveMove() {
  if (!moveFileId) return;
  const folderId = document.getElementById("move-modal-folder").value || null;
  const res = await fetch(`/files/${moveFileId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_id: folderId }),
  });
  if (res.ok) {
    closeMoveModal();
    await refreshFiles();
  } else {
    const err = await res.json();
    alert(err.detail || "Failed to move file.");
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

function folderActionMenu(folderId, folderName) {
  const action = window.prompt(`Folder options for "${folderName}": type 'new' for subfolder, 'rename', or 'delete'`);
  if (action === "new") openFolderModal("create", folderId);
  else if (action === "rename") openFolderModal("rename", folderId);
  else if (action === "delete") {
    if (window.confirm(`Delete folder "${folderName}"? Only empty folders can be deleted.`)) {
      fetch(`/folders/${folderId}`, { method: "DELETE" }).then((res) => {
        if (res.status === 204) { loadFolderTree(); window.location.reload(); }
        else if (res.status === 409) alert("Folder is not empty.");
      });
    }
  }
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

  const searchInput = document.getElementById("search-input");
  const fileInputHeader = document.getElementById("file-input-header");
  const fileInputDrop = document.getElementById("file-input-drop");
  const dropZone = document.getElementById("drop-zone");
  const newBtn = document.getElementById("btn-new-menu-trigger");
  const newDropdown = document.getElementById("new-dropdown-menu");

  const appFrame = document.querySelector(".drive-app");
  currentFolderId = appFrame?.dataset.currentFolder ? parseInt(appFrame.dataset.currentFolder, 10) : null;

  refreshFiles();
  loadFolderTree();

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
    const trigger = e.target.closest(".preview-trigger");
    if (trigger) return openPreview(trigger.dataset.id, trigger.dataset.name, trigger.dataset.mime);
    const move = e.target.closest(".move-trigger");
    if (move) return openMoveModal(move.dataset.id);
  });

  const foldersGrid = document.getElementById("folders-grid-container");
  foldersGrid?.addEventListener("click", (e) => {
    const menu = e.target.closest(".folder-menu-btn");
    if (menu) {
      e.stopPropagation();
      return folderActionMenu(menu.dataset.folderId, menu.dataset.folderName);
    }
  });

  const folderTree = document.getElementById("folder-tree");
  folderTree?.addEventListener("click", (e) => {
    const nav = e.target.closest(".tree-folder");
    if (nav) return navigate(nav.dataset.nav);
    const menu = e.target.closest(".tree-menu");
    if (menu) {
      const id = menu.dataset.menu;
      const name = menu.closest(".tree-row")?.querySelector("span")?.textContent || "this folder";
      folderActionMenu(id, name);
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
    if (e.key === "Escape") closePreview();
  });
});
