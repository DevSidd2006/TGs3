let currentFolderId = null;
let allFilesCache = [];
let allFoldersCache = [];
let viewMode = 'list';
let selectedFileId = null;
let activeTab = 'home';

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024, sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatDate(iso) {
  if (!iso) return "Today";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "Today" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function getBadgeInfo(mime = "", name = "") {
  const m = mime.toLowerCase();
  const n = name.toLowerCase();

  if (m.includes("spreadsheet") || n.endsWith(".xlsx")) return { class: "sheet", icon: "ph-file-xls" };
  if (m.includes("pdf") || n.endsWith(".pdf")) return { class: "pdf", icon: "ph-file-pdf" };
  if (m.startsWith("image/") || n.endsWith(".png") || n.endsWith(".jpg")) return { class: "img", icon: "ph-image" };
  if (m.includes("ipynb") || n.endsWith(".py")) return { class: "code", icon: "ph-code-simple" };
  return { class: "doc", icon: "ph-file-text" };
}

function showToast(msg) {
  const toast = document.getElementById("m-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 3000);
}

function initTheme() {
  const saved = localStorage.getItem("drive_theme") || "light";
  applyTheme(saved);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("drive_theme", theme);
  const icon = document.getElementById("m-theme-icon");
  if (icon) {
    icon.className = theme === "dark" ? "ph-bold ph-sun" : "ph-bold ph-moon";
  }
}

function toggleTheme() {
  const curr = document.documentElement.getAttribute("data-theme") || "light";
  applyTheme(curr === "dark" ? "light" : "dark");
}

async function loadFolderTree() {
  try {
    const res = await fetch("/folders");
    if (res.ok) {
      allFoldersCache = await res.json();
      renderFolders();
    }
  } catch (err) {
    console.error("Error loading folders:", err);
  }
}

function renderFolders() {
  const grid = document.getElementById("m-folders-grid");
  const sec = document.getElementById("m-folders-section");
  if (!grid || !sec) return;

  let currentSubfolders = [];
  if (!currentFolderId) {
    currentSubfolders = allFoldersCache;
  } else {
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
    const current = findNode(allFoldersCache, currentFolderId);
    currentSubfolders = current ? (current.children || []) : [];
  }

  if (currentSubfolders.length === 0) {
    sec.style.display = "none";
    return;
  }
  sec.style.display = "block";

  grid.innerHTML = currentSubfolders.map(folder => `
    <div class="m-folder-card" data-id="${folder.id}">
      <i class="ph-fill ph-folder m-folder-icon"></i>
      <span class="m-folder-name">${folder.name}</span>
    </div>
  `).join("");
}

async function refreshFiles(query = "") {
  try {
    const url = query
      ? `/files/search?q=${encodeURIComponent(query)}`
      : `/files?folder_id=${currentFolderId || ""}`;
    const res = await fetch(url);
    if (res.status === 401) { window.location.href = "/login"; return; }
    allFilesCache = await res.json();
    renderFiles();
  } catch (err) {
    console.error("Error refreshing files:", err);
  }
}

function renderFiles() {
  const list = document.getElementById("m-files-list");
  const empty = document.getElementById("m-empty-state");
  const count = document.getElementById("m-file-count");
  if (!list) return;

  let displayFiles = [...allFilesCache];
  if (activeTab === "starred") {
    displayFiles = displayFiles.filter(f => f.starred);
  }

  if (count) count.textContent = `${displayFiles.length} items`;
  if (empty) empty.hidden = displayFiles.length > 0;

  list.className = `m-files-list ${viewMode}-mode`;

  list.innerHTML = displayFiles.map(file => {
    const badge = getBadgeInfo(file.mime_type, file.name);
    return `
      <div class="m-file-card" data-id="${file.id}">
        <div class="m-file-icon-box ${badge.class}">
          <i class="ph-fill ${badge.icon}"></i>
        </div>
        <div class="m-file-info">
          <div class="m-file-title">${file.name}</div>
          <div class="m-file-sub">${formatBytes(file.size_bytes)} • ${formatDate(file.uploaded_at)}</div>
        </div>
        <button class="m-file-more" data-action="options" data-id="${file.id}" data-name="${file.name}">
          <i class="ph-bold ph-dots-three-vertical"></i>
        </button>
      </div>
    `;
  }).join("");
}

async function uploadFiles(fileList) {
  for (const file of Array.from(fileList)) {
    const formData = new FormData();
    formData.append("file", file);
    const folderParam = currentFolderId ? `?folder_id=${currentFolderId}` : "";
    try {
      showToast(`Uploading ${file.name}...`);
      const res = await fetch(`/files/upload${folderParam}`, { method: "POST", body: formData });
      if (res.ok) {
        showToast(`Uploaded ${file.name}`);
      } else {
        showToast(`Failed to upload ${file.name}`);
      }
    } catch (err) {
      showToast("Upload error");
    }
  }
  await refreshFiles();
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

function openCreateModal() {
  document.getElementById("m-create-modal").hidden = false;
}
function closeCreateModal() {
  document.getElementById("m-create-modal").hidden = true;
}

function openOptionsModal(fileId, fileName) {
  selectedFileId = fileId;
  document.getElementById("m-options-title").textContent = fileName || "File Options";
  document.getElementById("m-options-modal").hidden = false;
}
function closeOptionsModal() {
  document.getElementById("m-options-modal").hidden = true;
  selectedFileId = null;
}

async function promptCreateFolder() {
  closeCreateModal();
  const name = window.prompt("Enter folder name:");
  if (!name || !name.trim()) return;
  try {
    const res = await fetch("/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), parent_id: currentFolderId })
    });
    if (res.ok) {
      showToast(`Created folder "${name}"`);
      await loadFolderTree();
    } else {
      showToast("Failed to create folder");
    }
  } catch (err) {
    showToast("Error creating folder");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  refreshFiles();
  loadFolderTree();

  // Search
  document.getElementById("m-search-input")?.addEventListener("input", (e) => {
    refreshFiles(e.target.value.trim());
  });

  // View mode toggles
  document.getElementById("m-btn-list")?.addEventListener("click", () => {
    viewMode = 'list';
    document.getElementById("m-btn-list").classList.add("active");
    document.getElementById("m-btn-grid").classList.remove("active");
    renderFiles();
  });

  document.getElementById("m-btn-grid")?.addEventListener("click", () => {
    viewMode = 'grid';
    document.getElementById("m-btn-grid").classList.add("active");
    document.getElementById("m-btn-list").classList.remove("active");
    renderFiles();
  });

  // Theme toggle
  document.getElementById("m-theme-btn")?.addEventListener("click", toggleTheme);

  // FAB & Create modal
  document.getElementById("m-fab-btn")?.addEventListener("click", openCreateModal);
  document.getElementById("m-create-close")?.addEventListener("click", closeCreateModal);
  document.getElementById("m-opt-folder")?.addEventListener("click", promptCreateFolder);
  document.getElementById("m-opt-upload")?.addEventListener("click", () => {
    closeCreateModal();
    document.getElementById("m-hidden-file-input").click();
  });
  document.getElementById("m-hidden-file-input")?.addEventListener("change", (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
  });
  document.getElementById("m-opt-upload-folder")?.addEventListener("click", () => {
    closeCreateModal();
    document.getElementById("m-hidden-folder-input").click();
  });
  document.getElementById("m-hidden-folder-input")?.addEventListener("change", (e) => {
    if (e.target.files.length) uploadFolder(e.target.files);
    e.target.value = "";
  });

  // Options sheet actions
  document.getElementById("m-options-close")?.addEventListener("click", closeOptionsModal);
  document.getElementById("m-action-preview")?.addEventListener("click", () => {
    if (selectedFileId) window.location.href = `/view/files/${selectedFileId}`;
  });
  document.getElementById("m-action-download")?.addEventListener("click", () => {
    if (selectedFileId) window.location.href = `/files/${selectedFileId}/download`;
  });
  document.getElementById("m-action-logout")?.addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    window.location.href = "/login";
  });

  // Folder click navigation
  document.getElementById("m-folders-grid")?.addEventListener("click", (e) => {
    const card = e.target.closest(".m-folder-card");
    if (card) {
      currentFolderId = parseInt(card.dataset.id, 10);
      renderFolders();
      refreshFiles();
    }
  });

  // File item click / options
  document.getElementById("m-files-list")?.addEventListener("click", (e) => {
    const more = e.target.closest("[data-action='options']");
    if (more) {
      e.stopPropagation();
      return openOptionsModal(more.dataset.id, more.dataset.name);
    }
    const card = e.target.closest(".m-file-card");
    if (card) {
      window.location.href = `/view/files/${card.dataset.id}`;
    }
  });

  // Bottom Navigation Tabs
  document.querySelectorAll(".m-bottom-nav .nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".m-bottom-nav .nav-item").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.tab;
      refreshFiles();
    });
  });
});
