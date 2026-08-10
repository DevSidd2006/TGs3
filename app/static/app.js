let allFilesCache = [];
let currentCategory = 'all';
let currentSort = 'date-desc';
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

function getFileBadgeDetails(mimeType) {
  if (!mimeType) return { class: 'icon-doc', icon: 'ph-file-text', label: 'FILE' };
  const mime = mimeType.toLowerCase();
  if (mime.includes('pdf')) return { class: 'icon-pdf', icon: 'ph-file-pdf', label: 'PDF' };
  if (mime.startsWith('image/')) return { class: 'icon-img', icon: 'ph-image', label: 'IMAGE' };
  if (mime.startsWith('video/')) return { class: 'icon-video', icon: 'ph-video-camera', label: 'VIDEO' };
  if (mime.includes('zip') || mime.includes('compressed')) return { class: 'icon-zip', icon: 'ph-file-zip', label: 'ZIP' };
  return { class: 'icon-doc', icon: 'ph-file-text', label: mime.split('/')[1]?.toUpperCase() || 'FILE' };
}

function getFileCategory(mimeType) {
  if (!mimeType) return 'other';
  const mime = mimeType.toLowerCase();
  if (mime.includes('pdf')) return 'pdf';
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('video/')) return 'video';
  return 'other';
}

function updateCategoryCounts(files) {
  const counts = { all: files.length, pdf: 0, image: 0, video: 0, other: 0 };
  files.forEach(f => {
    const cat = getFileCategory(f.mime_type);
    counts[cat] = (counts[cat] || 0) + 1;
  });

  Object.keys(counts).forEach(cat => {
    const countEl = document.getElementById(`count-${cat}`);
    if (countEl) countEl.textContent = counts[cat];
  });
}

function filterCategory(cat) {
  currentCategory = cat;

  // Update nav bar active state
  document.querySelectorAll('.sidebar .nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.category === cat);
  });

  // Update top tabs active state
  document.querySelectorAll('.cat-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.cat === cat);
  });

  // Update breadcrumb label
  const breadcrumbEl = document.getElementById('category-breadcrumb');
  if (breadcrumbEl) {
    const labels = {
      all: 'All Files',
      pdf: 'PDF Documents',
      image: 'Images & Photos',
      video: 'Videos & Movies',
      other: 'Other Documents'
    };
    breadcrumbEl.innerHTML = `&rsaquo; ${labels[cat] || 'Files'}`;
  }

  renderFileList();
}

function handleSortChange(sortValue) {
  currentSort = sortValue;
  renderFileList();
}

function toggleSort(field) {
  const sortSelect = document.getElementById('sort-select');
  if (!sortSelect) return;

  if (field === 'name') {
    currentSort = currentSort === 'name-asc' ? 'name-desc' : 'name-asc';
  } else if (field === 'size') {
    currentSort = currentSort === 'size-desc' ? 'size-asc' : 'size-desc';
  } else if (field === 'date') {
    currentSort = currentSort === 'date-desc' ? 'date-asc' : 'date-desc';
  }

  sortSelect.value = currentSort;
  renderFileList();
}

function sortFiles(files) {
  return [...files].sort((a, b) => {
    switch (currentSort) {
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'name-desc':
        return b.name.localeCompare(a.name);
      case 'size-asc':
        return a.size_bytes - b.size_bytes;
      case 'size-desc':
        return b.size_bytes - a.size_bytes;
      case 'date-asc':
        return new Date(a.uploaded_at || 0) - new Date(b.uploaded_at || 0);
      case 'date-desc':
      default:
        return new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0);
    }
  });
}

function renderFileList() {
  const tbody = document.getElementById("file-table-body");
  const countEl = document.getElementById("storage-active-count");
  if (!tbody) return;

  // Filter by category
  let filtered = allFilesCache;
  if (currentCategory !== 'all') {
    filtered = allFilesCache.filter(f => getFileCategory(f.mime_type) === currentCategory);
  }

  // Filter by search query if any
  const searchInput = document.getElementById("search-input");
  if (searchInput && searchInput.value.trim()) {
    const q = searchInput.value.trim().toLowerCase();
    filtered = filtered.filter(f => f.name.toLowerCase().includes(q) || (f.mime_type && f.mime_type.toLowerCase().includes(q)));
  }

  // Apply sorting
  filtered = sortFiles(filtered);

  if (countEl) {
    countEl.textContent = `${filtered.length} files`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">
          No files found in this section.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((file) => {
    const badge = getFileBadgeDetails(file.mime_type);
    const formattedSize = formatBytes(file.size_bytes);
    const dateStr = file.uploaded_at ? file.uploaded_at.substring(0, 10) : "Today";
    const statusLabel = file.status === 'ready' ? 'Synced' : file.status;

    return `
      <tr>
        <td>
          <div class="file-title-wrapper">
            <div class="file-badge-icon ${badge.class}">
              <i class="ph-bold ${badge.icon}"></i>
            </div>
            <a href="/view/files/${file.id}" class="file-name-text">${file.name}</a>
          </div>
        </td>
        <td><span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-muted);">${badge.label}</span></td>
        <td><span style="color: var(--text-muted); font-size: 12px;">${dateStr}</span></td>
        <td><span style="font-family: 'JetBrains Mono', monospace; font-size: 12px;">${formattedSize}</span></td>
        <td>
          <span class="pill-status pill-${file.status}">
            ${statusLabel}
          </span>
        </td>
        <td>
          <div class="table-actions">
            <button type="button" class="link-action preview-trigger" data-id="${file.id}" data-mime="${file.mime_type || ''}" data-name="${file.name}" style="cursor: pointer; background: none; border: none;">Preview</button>
            <button type="button" class="link-action move-trigger" data-id="${file.id}" style="cursor: pointer; background: none; border: none;">Move</button>
            <a href="/files/${file.id}/download" class="link-action">Download</a>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function refreshFiles(query = "") {
  try {
    const url = query
      ? `/files/search?q=${encodeURIComponent(query)}`
      : `/files?folder_id=${currentFolderId || ""}`;
    const response = await fetch(url);
    allFilesCache = await response.json();
    updateCategoryCounts(allFilesCache);
    renderFileList();
  } catch (err) {
    console.error("Error refreshing file list:", err);
  }
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const folderParam = currentFolderId ? `?folder_id=${currentFolderId}` : "";
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

const PREVIEW_BODY = {
  image: (src) => `<img class="preview-image" src="${src}" alt="Preview">`,
  video: (src, mime) => `<video class="preview-frame" controls autoplay src="${src}" type="${mime}"></video>`,
  embed: (src) => `<iframe class="preview-frame" src="${src}" title="Preview"></iframe>`,
  missing: (name) => `<div class="preview-missing"><i class="ph-bold ph-file-x"></i><p>No preview available for <strong>${name}</strong>.</p><a class="link-action" href="#" data-download>Download instead</a></div>`,
};

function openPreview(fileId, fileName, mimeType) {
  const overlay = document.getElementById("preview-overlay");
  const body = document.getElementById("preview-body");
  const nameEl = document.getElementById("preview-name");
  const download = document.getElementById("preview-download");
  const src = `/files/${fileId}/preview`;

  nameEl.textContent = fileName;
  download.href = `/files/${fileId}/download`;

  if (mimeType && mimeType.startsWith("image/")) {
    body.innerHTML = PREVIEW_BODY.image(src);
  } else if (mimeType && mimeType.startsWith("video/")) {
    body.innerHTML = PREVIEW_BODY.video(src, mimeType);
  } else if (mimeType === "application/pdf" || (mimeType && mimeType.includes("pdf"))) {
    body.innerHTML = PREVIEW_BODY.embed(src);
  } else {
    body.innerHTML = PREVIEW_BODY.embed(src);
  }

  body.querySelectorAll("[data-download]").forEach((link) => {
    link.href = download.href;
  });

  overlay.hidden = false;
  document.body.classList.add("preview-open");
}

function closePreview() {
  const overlay = document.getElementById("preview-overlay");
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  document.getElementById("preview-body").innerHTML = "";
  document.body.classList.remove("preview-open");
}

function buildTreeHtml(nodes, depth = 0) {
  return nodes.map((node) => `
    <div class="tree-node" style="--depth: ${depth}">
      <div class="tree-row">
        <button type="button" class="tree-folder" data-nav="${node.id}" title="${node.name}">
          <i class="ph-bold ph-folder"></i>
          <span>${node.name}</span>
        </button>
        <button type="button" class="icon-action-btn tree-menu" data-menu="${node.id}" title="Options">
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

function openFolderModal(mode, parentId) {
  folderModalMode = mode;
  folderModalParent = parentId ?? null;
  document.getElementById("folder-modal-title").textContent = mode === "create" ? "New Folder" : "Rename Folder";
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

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-input");
  const fileInputHeader = document.getElementById("file-input-header");
  const fileInputDrop = document.getElementById("file-input-drop");
  const dropZone = document.getElementById("drop-zone");

  const appFrame = document.querySelector(".app-frame");
  currentFolderId = appFrame?.dataset.currentFolder ? parseInt(appFrame.dataset.currentFolder, 10) : null;

  // Initial fetch to load files into memory
  refreshFiles();
  loadFolderTree();

  searchInput?.addEventListener("input", () => {
    renderFileList();
  });

  fileInputHeader?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  });

  fileInputDrop?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      Array.from(e.target.files).forEach(file => uploadFile(file));
    }
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

  const fileTableBody = document.getElementById("file-table-body");
  fileTableBody?.addEventListener("click", (e) => {
    const trigger = e.target.closest(".preview-trigger");
    if (trigger) return openPreview(trigger.dataset.id, trigger.dataset.name, trigger.dataset.mime);
    const move = e.target.closest(".move-trigger");
    if (move) return openMoveModal(move.dataset.id);
    const folderMenu = e.target.closest(".folder-menu-btn");
    if (folderMenu) {
      const id = folderMenu.dataset.folderId;
      const action = window.prompt(`Folder options for "${folderMenu.dataset.folderName}": type 'new' for subfolder, 'rename', or 'delete'`);
      if (action === "new") openFolderModal("create", id);
      else if (action === "rename") openFolderModal("rename", id);
      else if (action === "delete") {
        if (window.confirm(`Delete folder "${folderMenu.dataset.folderName}"? Only empty folders can be deleted.`)) {
          fetch(`/folders/${id}`, { method: "DELETE" }).then((res) => {
            if (res.status === 204) { loadFolderTree(); window.location.reload(); }
            else if (res.status === 409) alert("Folder is not empty.");
          });
        }
      }
    }
  });

  const folderTree = document.getElementById("folder-tree");
  folderTree?.addEventListener("click", (e) => {
    const nav = e.target.closest(".tree-folder");
    if (nav) return navigate(nav.dataset.nav);
    const menu = e.target.closest(".tree-menu");
    if (menu) {
      const id = menu.dataset.menu;
      const action = window.prompt("Folder options: type 'new' for subfolder, 'rename', or 'delete'");
      if (action === "new") openFolderModal("create", id);
      else if (action === "rename") openFolderModal("rename", id);
      else if (action === "delete") {
        if (window.confirm("Delete this folder? Only empty folders can be deleted.")) {
          fetch(`/folders/${id}`, { method: "DELETE" }).then((res) => {
            if (res.status === 204) { loadFolderTree(); window.location.reload(); }
            else if (res.status === 409) alert("Folder is not empty.");
          });
        }
      }
    }
  });

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      const target = el.dataset.nav;
      if (target === "root") return navigate(null);
      if (!isNaN(parseInt(target, 10))) { e.preventDefault(); return navigate(target); }
    });
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
