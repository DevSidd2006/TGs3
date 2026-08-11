let currentFolderId = null;
let allFilesCache = [];

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024, sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function typeIcon(mime, name) {
  if ((mime || "").includes("spreadsheet") || (name || "").endsWith(".xlsx")) return "📊";
  if ((mime || "").includes("pdf")) return "📕";
  if ((mime || "").startsWith("image/")) return "🖼️";
  if ((mime || "").startsWith("video/")) return "🎬";
  if ((mime || "").includes("zip")) return "🗜️";
  return "📄";
}

function showToast(msg) {
  const toast = document.getElementById("m-toast");
  toast.textContent = msg;
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 3000);
}

function renderBreadcrumb() {
  const nav = document.getElementById("m-breadcrumb");
  nav.innerHTML = `<a href="#" data-folder="">All Files</a>`;
  if (currentFolderId) nav.innerHTML += `<span>›</span><span>Folder ${currentFolderId}</span>`;
}

async function refreshFiles(query = "") {
  const url = query ? `/files/search?q=${encodeURIComponent(query)}` : `/files?folder_id=${currentFolderId || ""}`;
  const res = await fetch(url);
  if (res.status === 401) { window.location.href = "/login"; return; }
  allFilesCache = await res.json();
  renderFileList();
}

function renderFileList() {
  const list = document.getElementById("m-file-list");
  const empty = document.getElementById("m-empty");
  const files = allFilesCache;
  empty.hidden = files.length > 0;
  list.innerHTML = files.map((f) => `
    <li class="m-file-item" data-id="${f.id}">
      <div class="m-file-icon">${typeIcon(f.mime_type, f.name)}</div>
      <div class="m-file-meta">
        <div class="m-file-name">${f.name}</div>
        <div class="m-file-sub">${formatBytes(f.size_bytes)} • ${formatDate(f.uploaded_at)}</div>
      </div>
      <button class="m-file-action" data-action="download" data-id="${f.id}" title="Download">⬇</button>
    </li>
  `).join("");
}

async function uploadFiles(fileList) {
  for (const file of Array.from(fileList)) {
    const formData = new FormData();
    formData.append("file", file);
    const folderParam = currentFolderId ? `?folder_id=${currentFolderId}` : "";
    try {
      const res = await fetch(`/files/upload${folderParam}`, { method: "POST", body: formData });
      if (res.ok) {
        showToast(`Uploaded ${file.name}`);
      } else if (res.status === 401) {
        window.location.href = "/login"; return;
      } else {
        showToast(`Failed to upload ${file.name}`);
      }
    } catch (err) {
      showToast("You're offline. Upload failed.");
    }
  }
  await refreshFiles();
}

document.addEventListener("DOMContentLoaded", () => {
  refreshFiles();

  document.getElementById("m-search").addEventListener("input", (e) => {
    const q = e.target.value.trim();
    if (q) refreshFiles(q); else refreshFiles();
  });

  document.getElementById("m-upload-btn").addEventListener("click", () => {
    document.getElementById("m-upload-input").click();
  });
  document.getElementById("m-upload-input").addEventListener("change", (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
  });

  document.getElementById("m-logout").addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    window.location.href = "/login";
  });

  document.getElementById("m-main").addEventListener("click", (e) => {
    const downloadBtn = e.target.closest("[data-action='download']");
    if (downloadBtn) {
      e.stopPropagation();
      window.location.href = `/files/${downloadBtn.dataset.id}/download`;
      return;
    }
    const item = e.target.closest(".m-file-item");
    if (item) window.location.href = `/view/files/${item.dataset.id}`;
  });
});
