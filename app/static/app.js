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
  if (mimeType.startsWith('image/')) return { class: 'icon-img', icon: 'ph-image', label: 'JPEG/PNG' };
  if (mimeType.startsWith('video/')) return { class: 'icon-img', icon: 'ph-video-camera', label: 'VIDEO' };
  if (mimeType.includes('pdf')) return { class: 'icon-pdf', icon: 'ph-file-pdf', label: 'PDF' };
  if (mimeType.includes('zip') || mimeType.includes('compressed')) return { class: 'icon-zip', icon: 'ph-file-zip', label: 'ZIP' };
  return { class: 'icon-doc', icon: 'ph-file-text', label: mimeType.split('/')[1]?.toUpperCase() || 'FILE' };
}

function renderFileList(files) {
  const tbody = document.getElementById("file-table-body");
  const countEl = document.getElementById("storage-active-count");
  if (countEl) {
    countEl.textContent = `${files.length} files`;
  }
  if (!tbody) return;

  if (files.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">
          No matching files found.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = files.map((file) => {
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
            <a href="/files/${file.id}/download" class="link-action">Download</a>
            <button class="icon-action-btn"><i class="ph-bold ph-dots-three-vertical"></i></button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function refreshFiles(query = "") {
  try {
    const url = query ? `/files/search?q=${encodeURIComponent(query)}` : "/files";
    const response = await fetch(url);
    const files = await response.json();
    renderFileList(files);
  } catch (err) {
    console.error("Error refreshing file list:", err);
  }
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/files/upload", {
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
  } else if (mimeType === "application/pdf") {
    body.innerHTML = PREVIEW_BODY.embed(src);
  } else if (mimeType) {
    body.innerHTML = PREVIEW_BODY.embed(src);
  } else {
    body.innerHTML = PREVIEW_BODY.missing(fileName);
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

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-input");
  const fileInputHeader = document.getElementById("file-input-header");
  const fileInputDrop = document.getElementById("file-input-drop");
  const dropZone = document.getElementById("drop-zone");

  searchInput?.addEventListener("input", (e) => {
    refreshFiles(e.target.value);
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
    if (!trigger) return;
    openPreview(trigger.dataset.id, trigger.dataset.name, trigger.dataset.mime);
  });

  document.getElementById("preview-close")?.addEventListener("click", closePreview);
  document.getElementById("preview-overlay")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closePreview();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePreview();
  });
});
