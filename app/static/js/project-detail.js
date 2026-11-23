const api = async (path, options = {}) => {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
          : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
};

const STATUS_LABEL = {
  backlog: "Backlog",
  dev: "Dev",
  sit: "SIT",
  uat: "UAT",
  to: "TO",
  izin: "Izin",
  release: "Release",
};

const TASK_STATUS_LABEL = {
  todo: "To Do",
  in_progress: "In Progress",
  review: "Review",
  done: "Done",
};

const STATUS_VALUES = Object.keys(STATUS_LABEL);

const MAX_DOCS = 3;
const MAX_DOC_BYTES = 10 * 1024 * 1024;
const DOC_EXT = new Set([
  ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
  ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".zip",
]);

const state = {
  projectId: Number(document.getElementById("project-detail-page")?.dataset.projectId || 0),
  project: null,
  tasks: [],
  notes: [],
  users: [],
  divisions: [],
  bidangsByDivision: {},
  selectedPicIds: [],
  suggestions: [],
  highlightIndex: -1,
  picSearch: "",
  pendingDocs: [],
  existingDocs: [],
};

const els = {
  root: document.getElementById("project-detail-root"),
  pageTitle: document.getElementById("detail-page-title"),
  pageSubtitle: document.getElementById("detail-page-subtitle"),
  btnEdit: document.getElementById("btn-edit-project"),
  btnTasks: document.getElementById("btn-open-tasks"),
  modal: document.getElementById("project-modal"),
  form: document.getElementById("project-form"),
  formError: document.getElementById("form-error"),
  modalTitle: document.getElementById("project-modal-title"),
  btnClose: document.getElementById("btn-close-modal"),
  btnCancel: document.getElementById("btn-cancel-modal"),
  picWrap: document.getElementById("pic-input-wrap"),
  picDropdown: document.getElementById("pic-dropdown"),
  picSearch: document.getElementById("pic-search"),
  picOptions: document.getElementById("pic-options"),
  picChips: document.getElementById("pic-chips"),
  fieldPic: document.getElementById("field-pic"),
  ownerType: document.getElementById("field-owner-type"),
  ownerDivision: document.getElementById("field-owner-division"),
  ownerBidang: document.getElementById("field-owner-bidang"),
  ownerDivisionField: document.getElementById("owner-division-field"),
  ownerBidangField: document.getElementById("owner-bidang-field"),
  docDropzone: document.getElementById("doc-dropzone"),
  docInput: document.getElementById("field-documents"),
  docList: document.getElementById("doc-file-list"),
  docUrl: document.getElementById("field-doc-url"),
  docUrlTitle: document.getElementById("field-doc-url-title"),
  btnAddDocUrl: document.getElementById("btn-add-doc-url"),
};

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatNoteTime(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatDate(value) {
  if (!value) return "-";
  const d = new Date(`${value}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function hasPhoto(url) {
  return Boolean(String(url || "").trim());
}

function picIcon(title = "") {
  return `
    <span class="pic-avatar pic-avatar-icon" title="${escapeHtml(title)}" role="img" aria-label="${escapeHtml(title || "PIC")}">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 12a4.5 4.5 0 1 0-4.5-4.5A4.5 4.5 0 0 0 12 12Zm0 2.25c-3.6 0-6.75 1.8-6.75 4.05V20h13.5v-1.7c0-2.25-3.15-4.05-6.75-4.05Z"/>
      </svg>
    </span>`;
}

function picPeople(project) {
  const fromMembers = (project.members || []).map((m) => m.user).filter(Boolean);
  if (fromMembers.length) return fromMembers;
  return [];
}

function renderPicStack(project) {
  const people = picPeople(project);
  const label = people.map((u) => u.name).join(", ") || project.pic || "Tidak ada PIC";
  if (!people.length) {
    return `<div class="pic-avatar-stack" title="${escapeHtml(label)}">${picIcon(label)}</div>`;
  }
  const shown = people.slice(0, 6);
  const extra = people.length - shown.length;
  return `
    <div class="pic-avatar-stack" title="${escapeHtml(label)}">
      ${shown
        .map((u) =>
          hasPhoto(u.avatar_url)
            ? `<img class="pic-avatar" src="${escapeHtml(u.avatar_url)}" alt="${escapeHtml(u.name)}" title="${escapeHtml(u.name)}" />`
            : picIcon(u.name)
        )
        .join("")}
      ${extra > 0 ? `<span class="pic-avatar-extra">+${extra}</span>` : ""}
    </div>
    <div class="detail-pic-names">${escapeHtml(label)}</div>`;
}

function taskCounts(tasks) {
  const counts = { todo: 0, in_progress: 0, review: 0, done: 0 };
  for (const t of tasks) {
    if (counts[t.status] != null) counts[t.status] += 1;
  }
  return counts;
}

function renderDetail() {
  const p = state.project;
  if (!p) {
    els.root.innerHTML = `
      <div class="details-empty">
        <div class="details-empty-icon">!</div>
        Project tidak ditemukan.
      </div>`;
    return;
  }

  const pct = Math.round(p.progress || 0);
  const counts = taskCounts(state.tasks);
  const related = state.tasks.slice(0, 12);

  els.pageTitle.textContent = p.name;
  els.pageSubtitle.textContent = p.description || "Ringkasan project, PIC, progress, dan task terkait.";
  els.btnEdit.hidden = false;
  els.btnTasks.href = `/tasks?project_id=${p.id}`;

  els.root.innerHTML = `
    <section class="detail-hero panel">
      <div class="details-head">
        <div class="project-card-icon lg" style="background:${escapeHtml(p.color || "#4F7CFF")}20;color:${escapeHtml(p.color || "#4F7CFF")}">▣</div>
        <div class="details-head-text">
          <h3>${escapeHtml(p.name)}</h3>
          <span class="status-badge ${escapeHtml(p.status)}">${STATUS_LABEL[p.status] || p.status}</span>
        </div>
      </div>
      <p class="details-desc">${escapeHtml(p.description || "Tidak ada deskripsi.")}</p>
      <div class="details-actions">
        <button type="button" class="btn btn-ghost btn-sm" id="btn-edit-inline">Edit</button>
        <a class="btn btn-primary btn-sm" href="/tasks?project_id=${p.id}">Open Tasks</a>
        <a class="btn btn-ghost btn-sm" href="/timeline">Timeline</a>
      </div>
    </section>

    <section class="detail-grid-wrap detail-grid-3">
      <article class="panel detail-card">
        <h4>Overview</h4>
        <div class="details-grid">
          <div class="details-item">
            <span>PIC</span>
            ${renderPicStack(p)}
          </div>
          <div class="details-item">
            <span>Kepemilikan</span>
            <strong>${escapeHtml(ownershipLabel(p))}</strong>
          </div>
          <div class="details-item">
            <span>Start Date</span>
            <strong>${formatDate(p.start_date)}</strong>
          </div>
          <div class="details-item">
            <span>Target Date</span>
            <strong>${formatDate(p.end_date)}</strong>
          </div>
          <div class="details-item">
            <span>Tasks</span>
            <strong>${Number(p.task_count || state.tasks.length || 0)}</strong>
          </div>
        </div>
        <div class="details-progress">
          <div class="details-progress-label">
            <span>Progress</span>
            <strong>${pct}%</strong>
          </div>
          <div class="project-progress-bar">
            <span style="width:${Math.min(100, Math.max(0, pct))}%;background:${escapeHtml(p.color || "#4F7CFF")}"></span>
          </div>
        </div>
        ${
          Array.isArray(p.documents) && p.documents.length
            ? `<div class="details-docs">
                <span>Documents</span>
                <ul class="details-doc-list">
                  ${p.documents
                    .map(
                      (d) => `
                    <li>
                      <a href="${escapeHtml(d.open_url || d.download_url || d.external_url || `#`)}" target="_blank" rel="noopener">${escapeHtml(d.original_name)}${d.kind === "url" ? " ↗" : ""}</a>
                    </li>`
                    )
                    .join("")}
                </ul>
              </div>`
            : ""
        }
      </article>

      <article class="panel detail-card">
        <h4>Task breakdown</h4>
        <div class="task-breakdown">
          ${Object.entries(TASK_STATUS_LABEL)
            .map(
              ([key, label]) => `
            <div class="task-breakdown-item">
              <span>${label}</span>
              <strong>${counts[key] || 0}</strong>
            </div>`
            )
            .join("")}
        </div>
      </article>

      <article class="panel detail-card related-tasks">
        <div class="related-head">
          <h4>Related tasks</h4>
          <a href="/tasks?project_id=${p.id}">Lihat semua →</a>
        </div>
        ${
          related.length
            ? `<ul>${related
                .map(
                  (t) => `
              <li>
                <div>
                  <strong>${escapeHtml(t.title)}</strong>
                  <small>${escapeHtml(t.category || "General")}${t.due_date ? ` · due ${formatDate(t.due_date)}` : ""}${
                    t.notes_count > 0 ? ` · ${t.notes_count} catatan` : ""
                  }</small>
                </div>
                <span class="task-status">${TASK_STATUS_LABEL[t.status] || t.status}</span>
              </li>`
                )
                .join("")}</ul>`
            : `<div class="cal-empty details-empty" style="padding:18px 8px">Belum ada task untuk project ini.</div>`
        }
      </article>
    </section>

    <section class="panel project-notes">
      <div class="related-head">
        <h4>Catatan / Problem</h4>
        <span class="project-notes-count">${state.notes.length}</span>
      </div>
      ${
        state.notes.length
          ? `<div class="project-notes-list">${state.notes
              .map(
                (note) => `
            <article class="project-note-item kind-${escapeHtml(note.kind || "problem")}">
              <div class="project-note-meta">
                <span class="project-note-kind">${note.kind === "note" ? "Catatan" : "Problem"}</span>
                <a class="project-note-task" href="/tasks?project_id=${p.id}" title="Buka board task">${escapeHtml(note.task_title || `Task #${note.task_id}`)}</a>
                <span>${escapeHtml(formatNoteTime(note.created_at))}</span>
              </div>
              <p>${escapeHtml(note.body)}</p>
            </article>`
              )
              .join("")}</div>`
          : `<div class="cal-empty details-empty" style="padding:18px 8px">Belum ada catatan pada task di project ini.</div>`
      }
    </section>
  `;

  document.getElementById("btn-edit-inline")?.addEventListener("click", () => openModal(p));
}

function selectedUsers() {
  return state.users.filter((u) => state.selectedPicIds.includes(u.id));
}

function availableUsers(query = "") {
  const q = query.trim().toLowerCase();
  return state.users.filter((user) => {
    if (state.selectedPicIds.includes(user.id)) return false;
    if (!q) return true;
    return (
      user.name.toLowerCase().includes(q) ||
      String(user.email || "").toLowerCase().includes(q) ||
      String(user.role || "").toLowerCase().includes(q)
    );
  });
}

function syncPicField() {
  els.fieldPic.value = selectedUsers().map((u) => u.name).join(", ");
  els.picSearch.placeholder = state.selectedPicIds.length
    ? "Tambah nama…"
    : "Ketik nama lalu pilih…";
  renderPicChips();
}

function renderPicChips() {
  els.picChips.innerHTML = selectedUsers()
    .map(
      (user) => `
    <span class="pic-chip">
      <span>${escapeHtml(user.name)}</span>
      <button type="button" data-remove-pic="${user.id}" aria-label="Hapus ${escapeHtml(user.name)}">×</button>
    </span>`
    )
    .join("");
}

function renderPicOptions() {
  state.suggestions = availableUsers(state.picSearch).slice(0, 12);
  if (!state.suggestions.length) {
    state.highlightIndex = -1;
    els.picOptions.innerHTML = `<div class="pic-empty">${
      state.picSearch.trim() ? "Tidak ada nama yang cocok." : "Semua PIC sudah dipilih."
    }</div>`;
    return;
  }
  els.picOptions.innerHTML = state.suggestions
    .map(
      (user, index) => `
      <button
        type="button"
        class="pic-option${index === state.highlightIndex ? " active" : ""}"
        role="option"
        data-pic-id="${user.id}"
      >
        <strong>${escapeHtml(user.name)}</strong>
        <small>${escapeHtml(user.role || "")}</small>
      </button>`
    )
    .join("");
}

function openPicDropdown() {
  els.picDropdown.hidden = false;
  els.picWrap.classList.add("open");
  els.picSearch.setAttribute("aria-expanded", "true");
  renderPicOptions();
}

function closePicDropdown() {
  els.picDropdown.hidden = true;
  els.picWrap.classList.remove("open");
  els.picSearch.setAttribute("aria-expanded", "false");
}

function addPic(id) {
  const num = Number(id);
  if (!num || state.selectedPicIds.includes(num)) return;
  state.selectedPicIds.push(num);
  state.picSearch = "";
  els.picSearch.value = "";
  syncPicField();
  renderPicOptions();
  els.picSearch.focus();
}

function removePic(id) {
  const num = Number(id);
  state.selectedPicIds = state.selectedPicIds.filter((x) => x !== num);
  syncPicField();
  if (!els.picDropdown.hidden) renderPicOptions();
}

function setSelectedPicsFromProject(project) {
  const memberIds = (project.members || []).map((m) => m.user?.id).filter(Boolean);
  if (memberIds.length) {
    state.selectedPicIds = memberIds;
  } else {
    const names = String(project.pic || "")
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    state.selectedPicIds = state.users
      .filter((u) => names.includes(u.name.toLowerCase()))
      .map((u) => u.id);
  }
  syncPicField();
}

function formatBytes(n) {
  const size = Number(n) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function fileExt(name) {
  const m = String(name || "").toLowerCase().match(/\.[a-z0-9]+$/);
  return m ? m[0] : "";
}

function totalDocSlotsUsed() {
  return state.existingDocs.length + state.pendingDocs.length;
}

function setDocMode(mode) {
  const next = mode === "url" ? "url" : "file";
  document.querySelectorAll("[data-doc-mode]").forEach((btn) => {
    const active = btn.dataset.docMode === next;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-doc-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.docPanel !== next;
  });
}

function renderDocList() {
  if (!els.docList) return;
  const items = [
    ...state.existingDocs.map((d) => ({
      kind: "existing",
      id: d.id,
      name: d.original_name,
      meta: d.kind === "url" ? "URL / Drive" : formatBytes(d.size_bytes),
      url: d.open_url || d.download_url || d.external_url,
      actionLabel: d.kind === "url" ? "Buka" : "Download",
    })),
    ...state.pendingDocs.map((item, idx) => ({
      kind: "pending",
      id: idx,
      name: item.type === "url" ? (item.title || item.url) : item.file.name,
      meta: item.type === "url" ? "URL · siap ditambah" : `${formatBytes(item.file.size)} · siap diunggah`,
      url: item.type === "url" ? item.url : null,
      actionLabel: item.type === "url" ? "Buka" : null,
    })),
  ];

  if (!items.length) {
    els.docList.hidden = true;
    els.docList.innerHTML = "";
  } else {
    els.docList.hidden = false;
    els.docList.innerHTML = items.map((item) => `
      <li class="doc-file-item" data-kind="${item.kind}" data-id="${item.id}">
        <div class="doc-file-meta">
          <strong title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(item.meta)}</span>
        </div>
        <div class="doc-file-actions">
          ${item.url && item.actionLabel ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${item.actionLabel}</a>` : ""}
          <button type="button" class="is-danger" data-remove-doc="${item.kind}:${item.id}">Hapus</button>
        </div>
      </li>
    `).join("");
  }
  els.docDropzone?.classList.toggle("is-full", totalDocSlotsUsed() >= MAX_DOCS);
}

function resetDocs() {
  state.pendingDocs = [];
  state.existingDocs = [];
  if (els.docInput) els.docInput.value = "";
  if (els.docUrl) els.docUrl.value = "";
  if (els.docUrlTitle) els.docUrlTitle.value = "";
  setDocMode("file");
  renderDocList();
}

function addPendingFiles(fileList) {
  const incoming = Array.from(fileList || []);
  if (!incoming.length) return;
  const remaining = MAX_DOCS - totalDocSlotsUsed();
  if (remaining <= 0) {
    els.formError.hidden = false;
    els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
    return;
  }
  const accepted = [];
  for (const file of incoming.slice(0, remaining)) {
    const ext = fileExt(file.name);
    if (!DOC_EXT.has(ext)) {
      els.formError.hidden = false;
      els.formError.textContent = `Tipe file tidak diizinkan: ${file.name}`;
      continue;
    }
    if (file.size > MAX_DOC_BYTES) {
      els.formError.hidden = false;
      els.formError.textContent = `File terlalu besar (maks 10 MB): ${file.name}`;
      continue;
    }
    accepted.push({ type: "file", file });
  }
  if (accepted.length) {
    els.formError.hidden = true;
    state.pendingDocs.push(...accepted);
    renderDocList();
  }
  if (els.docInput) els.docInput.value = "";
}

function addPendingUrl() {
  const url = (els.docUrl?.value || "").trim();
  const title = (els.docUrlTitle?.value || "").trim();
  if (!url) {
    els.formError.hidden = false;
    els.formError.textContent = "Isi URL dokumen terlebih dahulu.";
    return;
  }
  if (!/^https?:\/\//i.test(url)) {
    els.formError.hidden = false;
    els.formError.textContent = "URL harus dimulai dengan http:// atau https://";
    return;
  }
  if (totalDocSlotsUsed() >= MAX_DOCS) {
    els.formError.hidden = false;
    els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
    return;
  }
  const exists = state.pendingDocs.some((d) => d.type === "url" && d.url === url)
    || state.existingDocs.some((d) => d.kind === "url" && d.external_url === url);
  if (exists) {
    els.formError.hidden = false;
    els.formError.textContent = "URL tersebut sudah ditambahkan.";
    return;
  }
  els.formError.hidden = true;
  state.pendingDocs.push({ type: "url", url, title });
  if (els.docUrl) els.docUrl.value = "";
  if (els.docUrlTitle) els.docUrlTitle.value = "";
  renderDocList();
}

async function removeExistingDoc(docId) {
  const projectId = document.getElementById("project-id").value;
  if (!projectId) return;
  await api(`/api/projects/${projectId}/documents/${docId}`, { method: "DELETE" });
  state.existingDocs = state.existingDocs.filter((d) => d.id !== docId);
  renderDocList();
}

async function uploadPendingDocs(projectId) {
  if (!state.pendingDocs.length) return;
  const files = state.pendingDocs.filter((d) => d.type === "file").map((d) => d.file);
  const urls = state.pendingDocs.filter((d) => d.type === "url");
  const created = [];

  if (files.length) {
    const body = new FormData();
    files.forEach((file) => body.append("files", file, file.name));
    const res = await fetch(`/api/projects/${projectId}/documents`, { method: "POST", body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      throw new Error(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
            : `Upload gagal (${res.status})`
      );
    }
    if (Array.isArray(data)) created.push(...data);
  }

  for (const item of urls) {
    const row = await api(`/api/projects/${projectId}/documents/url`, {
      method: "POST",
      body: JSON.stringify({ url: item.url, title: item.title || null }),
    });
    created.push(row);
  }

  state.pendingDocs = [];
  state.existingDocs = [...state.existingDocs, ...created];
}

function wireDocEvents() {
  document.querySelectorAll("[data-doc-mode]").forEach((btn) => {
    btn.addEventListener("click", () => setDocMode(btn.dataset.docMode));
  });
  els.btnAddDocUrl?.addEventListener("click", addPendingUrl);
  els.docUrl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addPendingUrl();
    }
  });
  els.docUrlTitle?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addPendingUrl();
    }
  });

  if (els.docDropzone && els.docInput) {
    els.docDropzone.addEventListener("click", () => {
      if (totalDocSlotsUsed() >= MAX_DOCS) {
        els.formError.hidden = false;
        els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
        return;
      }
      els.docInput.click();
    });
    ["dragenter", "dragover"].forEach((evt) => {
      els.docDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        els.docDropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((evt) => {
      els.docDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        els.docDropzone.classList.remove("dragover");
      });
    });
    els.docDropzone.addEventListener("drop", (e) => addPendingFiles(e.dataTransfer?.files));
    els.docInput.addEventListener("change", () => addPendingFiles(els.docInput.files));
  }

  els.docList?.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-remove-doc]");
    if (!btn) return;
    const [kind, idRaw] = String(btn.dataset.removeDoc || "").split(":");
    if (kind === "pending") {
      state.pendingDocs = state.pendingDocs.filter((_, i) => i !== Number(idRaw));
      renderDocList();
      return;
    }
    if (kind === "existing") {
      try {
        await removeExistingDoc(Number(idRaw));
      } catch (err) {
        els.formError.hidden = false;
        els.formError.textContent = err.message || "Gagal menghapus dokumen.";
      }
    }
  });
}

function ownershipLabel(project) {
  const kind = String(project.owner_type || "unassigned");
  if (kind === "division") {
    return project.owner_division_name
      ? `Divisi · ${project.owner_division_name}`
      : "Divisi";
  }
  if (kind === "bidang") {
    const bidang = project.owner_bidang_name || "";
    const division = project.owner_division_name || "";
    if (bidang && division) return `Bidang · ${bidang} (${division})`;
    if (bidang) return `Bidang · ${bidang}`;
    return "Bidang";
  }
  return "Belum diklasifikasi";
}

function syncOwnershipFields() {
  const kind = els.ownerType?.value || "unassigned";
  if (els.ownerDivisionField) els.ownerDivisionField.hidden = kind === "unassigned";
  if (els.ownerBidangField) els.ownerBidangField.hidden = kind !== "bidang";
  if (kind === "unassigned") {
    if (els.ownerDivision) els.ownerDivision.value = "";
    if (els.ownerBidang) els.ownerBidang.value = "";
  }
  if (kind === "division" && els.ownerBidang) els.ownerBidang.value = "";
}

function fillDivisionOptions(selectedId = "") {
  if (!els.ownerDivision) return;
  els.ownerDivision.innerHTML = ['<option value="">— Pilih Divisi —</option>']
    .concat(
      state.divisions.map(
        (d) =>
          `<option value="${d.id}" ${String(d.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(d.name)}</option>`
      )
    )
    .join("");
}

async function loadBidangsForDivision(divisionId, selectedBidangId = "") {
  if (!els.ownerBidang) return;
  if (!divisionId) {
    els.ownerBidang.innerHTML = '<option value="">— Pilih Bidang —</option>';
    return;
  }
  let items = state.bidangsByDivision[divisionId] || state.bidangsByDivision[String(divisionId)];
  if (!items) {
    try {
      const data = await api("/api/organization/ownership-options");
      state.divisions = Array.isArray(data.divisions) ? data.divisions : [];
      state.bidangsByDivision = {};
      for (const b of Array.isArray(data.bidangs) ? data.bidangs : []) {
        const key = String(b.division_id);
        if (!state.bidangsByDivision[key]) state.bidangsByDivision[key] = [];
        state.bidangsByDivision[key].push(b);
      }
      items = state.bidangsByDivision[String(divisionId)] || [];
    } catch {
      items = [];
    }
  }
  els.ownerBidang.innerHTML = ['<option value="">— Pilih Bidang —</option>']
    .concat(
      items.map(
        (b) =>
          `<option value="${b.id}" ${String(b.id) === String(selectedBidangId) ? "selected" : ""}>${escapeHtml(b.name)}</option>`
      )
    )
    .join("");
}

async function applyOwnershipToForm(project) {
  const kind = project?.owner_type || "unassigned";
  if (els.ownerType) els.ownerType.value = kind;
  fillDivisionOptions(project?.owner_division_id || "");
  syncOwnershipFields();
  if (kind === "bidang") {
    await loadBidangsForDivision(project?.owner_division_id || "", project?.owner_bidang_id || "");
  } else if (els.ownerBidang) {
    els.ownerBidang.innerHTML = '<option value="">— Pilih Bidang —</option>';
  }
}

async function openModal(project) {
  els.form.reset();
  els.formError.hidden = true;
  els.formError.textContent = "";
  state.selectedPicIds = [];
  state.picSearch = "";
  els.picSearch.value = "";
  closePicDropdown();
  resetDocs();

  els.modalTitle.textContent = "Edit Project";
  document.getElementById("project-id").value = project.id;
  document.getElementById("field-name").value = project.name || "";
  document.getElementById("field-description").value = project.description || "";
  document.getElementById("field-start").value = project.start_date || "";
  document.getElementById("field-end").value = project.end_date || "";
  document.getElementById("field-status").value = STATUS_VALUES.includes(project.status)
    ? project.status
    : "backlog";
  setSelectedPicsFromProject(project);
  await applyOwnershipToForm(project);
  try {
    const docs = project.documents?.length
      ? project.documents
      : await api(`/api/projects/${project.id}/documents`);
    state.existingDocs = Array.isArray(docs) ? docs : [];
    renderDocList();
  } catch {
    state.existingDocs = [];
    renderDocList();
  }
  els.modal.hidden = false;
  document.getElementById("field-name").focus();
}

function closeModal() {
  closePicDropdown();
  resetDocs();
  els.modal.hidden = true;
}

async function saveProject(event) {
  event.preventDefault();
  els.formError.hidden = true;
  syncPicField();

  const id = document.getElementById("project-id").value;
  const ownerType = els.ownerType?.value || "unassigned";
  const ownerDivisionId = els.ownerDivision?.value ? Number(els.ownerDivision.value) : null;
  const ownerBidangId = els.ownerBidang?.value ? Number(els.ownerBidang.value) : null;
  const payload = {
    name: document.getElementById("field-name").value.trim(),
    description: document.getElementById("field-description").value.trim() || null,
    pic: els.fieldPic.value.trim(),
    start_date: document.getElementById("field-start").value,
    end_date: document.getElementById("field-end").value,
    status: document.getElementById("field-status").value,
    member_ids: state.selectedPicIds.slice(),
    owner_type: ownerType,
    owner_division_id: ownerType === "division" || ownerType === "bidang" ? ownerDivisionId : null,
    owner_bidang_id: ownerType === "bidang" ? ownerBidangId : null,
  };

  if (!payload.name || !payload.pic || !payload.start_date || !payload.end_date) {
    els.formError.hidden = false;
    els.formError.textContent = "Lengkapi field wajib, termasuk minimal 1 PIC.";
    return;
  }
  if (ownerType === "division" && !ownerDivisionId) {
    els.formError.hidden = false;
    els.formError.textContent = "Pilih Divisi pemilik.";
    return;
  }
  if (ownerType === "bidang" && !ownerBidangId) {
    els.formError.hidden = false;
    els.formError.textContent = "Pilih Bidang pemilik.";
    return;
  }

  try {
    state.project = await api(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    if (state.pendingDocs.length) {
      await uploadPendingDocs(id);
      state.project.documents = state.existingDocs.slice();
    }
    closeModal();
    renderDetail();
  } catch (err) {
    els.formError.hidden = false;
    els.formError.textContent = err.message || "Failed to save project.";
  }
}

function wirePicEvents() {
  els.picWrap.addEventListener("click", (e) => {
    if (e.target.closest("[data-remove-pic]")) return;
    els.picSearch.focus();
    openPicDropdown();
  });
  els.picSearch.addEventListener("focus", openPicDropdown);
  els.picSearch.addEventListener("input", () => {
    state.picSearch = els.picSearch.value;
    state.highlightIndex = 0;
    openPicDropdown();
  });
  els.picOptions.addEventListener("mousedown", (e) => {
    const option = e.target.closest("[data-pic-id]");
    if (!option) return;
    e.preventDefault();
    addPic(option.dataset.picId);
  });
  els.picChips.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-pic]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    removePic(btn.dataset.removePic);
    els.picSearch.focus();
  });
  document.addEventListener("click", (e) => {
    const box = document.getElementById("pic-multiselect");
    if (!box || els.picDropdown.hidden) return;
    if (!box.contains(e.target)) closePicDropdown();
  });
}

function wireEvents() {
  els.btnEdit?.addEventListener("click", () => {
    if (state.project) openModal(state.project);
  });
  els.btnClose?.addEventListener("click", closeModal);
  els.btnCancel?.addEventListener("click", closeModal);
  els.modal?.addEventListener("click", (e) => {
    if (e.target === els.modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !els.modal.hidden && els.picDropdown.hidden) closeModal();
  });
  els.form?.addEventListener("submit", saveProject);
  els.ownerType?.addEventListener("change", async () => {
    syncOwnershipFields();
    if ((els.ownerType?.value || "") === "bidang") {
      await loadBidangsForDivision(els.ownerDivision?.value || "");
    }
  });
  els.ownerDivision?.addEventListener("change", async () => {
    if ((els.ownerType?.value || "") === "bidang") {
      await loadBidangsForDivision(els.ownerDivision.value || "");
    }
  });
  wirePicEvents();
  wireDocEvents();
}

async function boot() {
  wireEvents();
  if (!state.projectId) {
    els.root.innerHTML = `<div class="details-empty"><div class="details-empty-icon">!</div>Project ID tidak valid.</div>`;
    return;
  }
  try {
    const [project, tasks, notes, users, divisions] = await Promise.all([
      api(`/api/projects/${state.projectId}`),
      api(`/api/tasks?project_id=${state.projectId}`),
      api(`/api/projects/${state.projectId}/notes`),
      api("/api/team?active_only=true"),
      api("/api/organization/ownership-options").catch(() => ({ divisions: [], bidangs: [] })),
    ]);
    state.project = project;
    state.tasks = Array.isArray(tasks) ? tasks : [];
    state.notes = Array.isArray(notes) ? notes : [];
    state.users = Array.isArray(users) ? users : users.items || [];
    state.divisions = Array.isArray(divisions.divisions) ? divisions.divisions : [];
    state.bidangsByDivision = {};
    for (const b of Array.isArray(divisions.bidangs) ? divisions.bidangs : []) {
      const key = String(b.division_id);
      if (!state.bidangsByDivision[key]) state.bidangsByDivision[key] = [];
      state.bidangsByDivision[key].push(b);
    }
    renderDetail();
  } catch (err) {
    els.root.innerHTML = `
      <div class="details-empty">
        <div class="details-empty-icon">!</div>
        Gagal memuat detail: ${escapeHtml(err.message)}
        <div style="margin-top:12px"><a class="btn btn-ghost btn-sm" href="/projects">Kembali ke Projects</a></div>
      </div>`;
  }
}

document.addEventListener("DOMContentLoaded", boot);
