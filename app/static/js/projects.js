const api = async (path, options = {}) => {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message = typeof detail === "string"
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

const STATUS_VALUES = Object.keys(STATUS_LABEL);

const PAGE_SIZE = 10;

const TRASH_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 7l1 12a2 2 0 0 0 2 1.8h2a2 2 0 0 0 2-1.8L16 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`;

const MAX_DOCS = 3;
const MAX_DOC_BYTES = 10 * 1024 * 1024;
const DOC_EXT = new Set([
  ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
  ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".zip",
]);

const state = {
  projects: [],
  users: [],
  divisions: [],
  bidangsByDivision: {},
  selectedPicIds: [],
  suggestions: [],
  highlightIndex: -1,
  query: "",
  status: "",
  ownerType: "",
  picSearch: "",
  page: 1,
  pages: 1,
  total: 0,
  pageSize: PAGE_SIZE,
  canDelete: false,
  isAdmin: false,
  scopeStatus: null,
  pendingDocs: [],
  existingDocs: [],
  workspacesEnabled: false,
  workspaces: [],
  workspaceDivision: null,
  workspaceId: null,
  workspace: null,
};

const els = {
  page: document.getElementById("projects-page"),
  stats: document.getElementById("projects-stats"),
  list: document.getElementById("projects-list"),
  pagination: document.getElementById("projects-pagination"),
  search: document.getElementById("project-search"),
  filter: document.getElementById("project-status-filter"),
  ownerFilter: document.getElementById("project-owner-filter"),
  ownerType: document.getElementById("field-owner-type"),
  ownerDivision: document.getElementById("field-owner-division"),
  ownerBidang: document.getElementById("field-owner-bidang"),
  ownerDivisionField: document.getElementById("owner-division-field"),
  ownerBidangField: document.getElementById("owner-bidang-field"),
  modal: document.getElementById("project-modal"),
  form: document.getElementById("project-form"),
  formError: document.getElementById("form-error"),
  modalTitle: document.getElementById("project-modal-title"),
  modalSubtitle: document.getElementById("project-modal-subtitle"),
  btnNew: document.getElementById("btn-new-project"),
  btnClose: document.getElementById("btn-close-modal"),
  btnCancel: document.getElementById("btn-cancel-modal"),
  picWrap: document.getElementById("pic-input-wrap"),
  picDropdown: document.getElementById("pic-dropdown"),
  picSearch: document.getElementById("pic-search"),
  picOptions: document.getElementById("pic-options"),
  picChips: document.getElementById("pic-chips"),
  fieldPic: document.getElementById("field-pic"),
  docDropzone: document.getElementById("doc-dropzone"),
  docInput: document.getElementById("field-documents"),
  docList: document.getElementById("doc-file-list"),
  docUrl: document.getElementById("field-doc-url"),
  docUrlTitle: document.getElementById("field-doc-url-title"),
  btnAddDocUrl: document.getElementById("btn-add-doc-url"),
  workspacePicker: document.getElementById("workspace-picker"),
  workspaceGrid: document.getElementById("workspace-grid"),
  workspacePickerSub: document.getElementById("workspace-picker-subtitle"),
  listView: document.getElementById("projects-list-view"),
  workspaceCrumb: document.getElementById("workspace-crumb"),
  workspaceCrumbName: document.getElementById("workspace-crumb-name"),
  btnBackWorkspaces: document.getElementById("btn-back-workspaces"),
  projectsHeading: document.getElementById("projects-heading"),
  pageSubtitle: document.getElementById("projects-page-subtitle"),
  projectsHero: document.querySelector("#projects-list-view .projects-hero"),
};

const WORKSPACE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 20h18"/><path d="M6 20V9.5L12 5l6 4.5V20"/><path d="M10 20v-4h4v4"/></svg>`;

function readWorkspaceFromUrl() {
  const raw = new URLSearchParams(window.location.search).get("workspace");
  const id = Number(raw);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function setWorkspaceUrl(workspaceId) {
  const url = new URL(window.location.href);
  if (workspaceId) url.searchParams.set("workspace", String(workspaceId));
  else url.searchParams.delete("workspace");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function formatDate(value) {
  if (!value) return "-";
  const d = new Date(`${value}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function plusDaysISO(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function initials(name = "") {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("") || "P";
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function plainText(html) {
  return String(html ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
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
  const users = selectedUsers();
  els.picChips.innerHTML = users
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
      state.picSearch.trim()
        ? "Tidak ada nama yang cocok."
        : "Semua user sudah dipilih."
    }</div>`;
    return;
  }

  if (state.highlightIndex < 0 || state.highlightIndex >= state.suggestions.length) {
    state.highlightIndex = 0;
  }

  els.picOptions.innerHTML = state.suggestions
    .map((user, index) => `
      <button
        type="button"
        class="pic-option${index === state.highlightIndex ? " active" : ""}"
        role="option"
        data-pic-id="${user.id}"
        data-index="${index}"
      >
        <span>${escapeHtml(user.name)}</span>
        <small>${escapeHtml(user.role || "")}</small>
      </button>`)
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
  state.highlightIndex = -1;
}

function addPic(userId) {
  const id = Number(userId);
  if (!id || state.selectedPicIds.includes(id)) return;
  state.selectedPicIds.push(id);
  state.picSearch = "";
  els.picSearch.value = "";
  syncPicField();
  openPicDropdown();
  els.picSearch.focus();
}

function removePic(userId) {
  const id = Number(userId);
  state.selectedPicIds = state.selectedPicIds.filter((x) => x !== id);
  syncPicField();
  if (!els.picDropdown.hidden) renderPicOptions();
}

function setSelectedPicsFromNames(picText) {
  const names = String(picText || "")
    .split(",")
    .map((n) => n.trim().toLowerCase())
    .filter(Boolean);
  state.selectedPicIds = state.users
    .filter((u) => names.includes(String(u.name).trim().toLowerCase()))
    .map((u) => u.id);
  syncPicField();
  if (names.length && !state.selectedPicIds.length && picText) {
    els.fieldPic.value = picText;
  }
}

function renderStats(stats) {
  els.stats.innerHTML = `
    <article class="stat-card">
      <div>
        <span>Total Projects</span>
        <strong>${stats.total}</strong>
      </div>
      <div class="stat-icon purple">▣</div>
    </article>
    <article class="stat-card">
      <div>
        <span>In Progress</span>
        <strong>${stats.in_progress}</strong>
      </div>
      <div class="stat-icon green">⏱</div>
    </article>
    <article class="stat-card">
      <div>
        <span>Release</span>
        <strong>${stats.completed}</strong>
      </div>
      <div class="stat-icon blue">✓</div>
    </article>
  `;
}

function pageWindow(current, totalPages) {
  const pages = [];
  const windowSize = 5;
  let start = Math.max(1, current - Math.floor(windowSize / 2));
  let end = Math.min(totalPages, start + windowSize - 1);
  start = Math.max(1, end - windowSize + 1);
  for (let i = start; i <= end; i += 1) pages.push(i);
  return pages;
}

function renderPagination() {
  if (!els.pagination) return;
  if (!state.total) {
    els.pagination.innerHTML = "";
    return;
  }

  const from = (state.page - 1) * state.pageSize + 1;
  const to = Math.min(state.page * state.pageSize, state.total);
  const pages = pageWindow(state.page, state.pages);

  els.pagination.innerHTML = `
    <div class="pagination-meta">
      Menampilkan <strong>${from}–${to}</strong> dari <strong>${state.total}</strong> project
    </div>
    <div class="pagination-controls">
      <button type="button" class="btn btn-ghost btn-sm" data-page="prev" ${state.page <= 1 ? "disabled" : ""}>‹ Prev</button>
      ${pages
        .map(
          (p) => `
        <button type="button" class="btn btn-sm ${p === state.page ? "btn-primary" : "btn-ghost"}" data-page="${p}">${p}</button>`
        )
        .join("")}
      <button type="button" class="btn btn-ghost btn-sm" data-page="next" ${state.page >= state.pages ? "disabled" : ""}>Next ›</button>
    </div>
  `;
}

function picPeople(project) {
  const fromMembers = (project.members || [])
    .map((m) => m.user)
    .filter(Boolean);
  if (fromMembers.length) return fromMembers;

  const names = String(project.pic || "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  if (!names.length) return [];

  const matched = [];
  const seen = new Set();
  for (const name of names) {
    const user = state.users.find((u) => u.name.toLowerCase() === name);
    if (user && !seen.has(user.id)) {
      seen.add(user.id);
      matched.push(user);
    }
  }
  return matched;
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

function renderPicCell(project) {
  const people = picPeople(project);
  const label = people.map((u) => u.name).join(", ") || project.pic || "Tidak ada PIC";

  if (!people.length) {
    return `
      <div class="pic-avatar-stack" title="${escapeHtml(label)}">
        ${picIcon(label)}
      </div>`;
  }

  const shown = people.slice(0, 4);
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
      ${extra > 0 ? `<span class="pic-avatar-extra" title="+${extra} lagi">+${extra}</span>` : ""}
    </div>`;
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

function renderList() {
  if (!state.projects.length) {
    els.list.innerHTML = `
      <tr>
        <td colspan="10" class="list-empty">No projects found. Click <strong>+ New Project</strong> to create one.</td>
      </tr>`;
    renderPagination();
    return;
  }

  els.list.innerHTML = state.projects
    .map((p) => {
      const pct = Math.round(p.progress || 0);
      const owner = ownershipLabel(p);
      return `
      <tr class="project-row" data-id="${p.id}" tabindex="0" role="link" aria-label="Open ${escapeHtml(p.name)}">
        <td>
          <a class="project-cell-copy project-name-link" href="/projects/${p.id}" title="${escapeHtml(p.name)}">
            <strong>${escapeHtml(p.name)}</strong>
            ${plainText(p.description) ? `<span>${escapeHtml(plainText(p.description))}</span>` : ""}
          </a>
        </td>
        <td><span class="owner-pill ${escapeHtml(p.owner_type || "unassigned")}" title="${escapeHtml(owner)}">${escapeHtml(owner)}</span></td>
        <td class="col-pic">${renderPicCell(p)}</td>
        <td><span class="status-badge ${p.status}">${STATUS_LABEL[p.status] || p.status}</span></td>
        <td>
          <div class="table-progress">
            <div class="table-progress-bar"><span style="width:${Math.min(100, Math.max(0, pct))}%;background:${p.color || "#4F7CFF"}"></span></div>
            <em>${pct}%</em>
          </div>
        </td>
        <td>${formatDate(p.start_date)}</td>
        <td>${formatDate(p.end_date)}</td>
        <td>${Number(p.task_count || 0)}</td>
        <td class="col-actions">
          <div class="table-actions">
            <button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-id="${p.id}">Edit</button>
            <a class="btn btn-primary btn-sm" href="/tasks?project_id=${p.id}" data-action="tasks">Tasks</a>
          </div>
        </td>
        <td class="col-delete">
          ${state.canDelete
            ? `<button type="button" class="icon-action danger" data-action="delete" data-id="${p.id}" title="Hapus project" aria-label="Hapus project">${TRASH_ICON}</button>`
            : ""}
        </td>
      </tr>`;
    })
    .join("");
  renderPagination();
}

async function deleteProject(projectId) {
  const project = state.projects.find((p) => p.id === Number(projectId));
  if (!project) return;
  const ok = window.pmConfirm
    ? await window.pmConfirm({
        title: "Hapus project?",
        message:
          "Project beserta task dan catatan terkait akan dihapus. Tindakan ini tidak bisa dibatalkan.",
        meta: project.name,
        tone: "danger",
        icon: "!",
        okText: "Hapus Project",
        cancelText: "Batal",
      })
    : window.confirm(`Hapus project "${project.name}"?`);
  if (!ok) return;
  try {
    await api(`/api/projects/${project.id}`, { method: "DELETE" });
    if (state.projects.length <= 1 && state.page > 1) state.page -= 1;
    await Promise.all([loadStats(), loadProjects()]);
  } catch (err) {
    if (window.pmNotice) {
      await window.pmNotice({
        title: "Gagal menghapus project",
        message: err.message || "Gagal menghapus project.",
        tone: "danger",
        icon: "!",
      });
    } else {
      window.alert(err.message || "Gagal menghapus project.");
    }
  }
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

  const full = totalDocSlotsUsed() >= MAX_DOCS;
  els.docDropzone?.classList.toggle("is-full", full);
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

function notifyDoc(message, { title = "Perhatian", tone = "warn", icon = "!" } = {}) {
  if (window.pmNotice) {
    window.pmNotice({ title, message, tone, icon, okText: "Mengerti" });
    return;
  }
  if (els.formError) {
    els.formError.hidden = false;
    els.formError.textContent = message;
  }
}

function addPendingUrl() {
  const url = (els.docUrl?.value || "").trim();
  const title = (els.docUrlTitle?.value || "").trim();
  if (!url) {
    notifyDoc("Isi URL dokumen terlebih dahulu.", { title: "URL dokumen" });
    return;
  }
  if (!/^https?:\/\//i.test(url)) {
    notifyDoc("URL harus dimulai dengan http:// atau https://", { title: "URL tidak valid" });
    return;
  }
  if (totalDocSlotsUsed() >= MAX_DOCS) {
    notifyDoc(`Maksimal ${MAX_DOCS} dokumen per project.`, { title: "Batas dokumen" });
    return;
  }
  const exists = state.pendingDocs.some((d) => d.type === "url" && d.url === url)
    || state.existingDocs.some((d) => d.kind === "url" && d.external_url === url);
  if (exists) {
    notifyDoc("URL tersebut sudah ditambahkan.", { title: "URL dokumen" });
    return;
  }
  if (els.formError) els.formError.hidden = true;
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

    els.docDropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        els.docDropzone.click();
      }
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
    els.docDropzone.addEventListener("drop", (e) => {
      addPendingFiles(e.dataTransfer?.files);
    });
    els.docInput.addEventListener("change", () => addPendingFiles(els.docInput.files));
  }

  els.docList?.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-remove-doc]");
    if (!btn) return;
    const [kind, idRaw] = String(btn.dataset.removeDoc || "").split(":");
    if (kind === "pending") {
      const idx = Number(idRaw);
      state.pendingDocs = state.pendingDocs.filter((_, i) => i !== idx);
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

function syncOwnershipFields() {
  const kind = els.ownerType?.value || "unassigned";
  if (els.ownerDivisionField) {
    els.ownerDivisionField.hidden = kind === "unassigned";
  }
  if (els.ownerBidangField) {
    els.ownerBidangField.hidden = kind !== "bidang";
  }
  if (kind === "unassigned") {
    if (els.ownerDivision) els.ownerDivision.value = "";
    if (els.ownerBidang) els.ownerBidang.value = "";
  }
  if (kind === "division" && els.ownerBidang) {
    els.ownerBidang.value = "";
  }
}

function fillDivisionOptions(selectedId = "") {
  if (!els.ownerDivision) return;
  const options = ['<option value="">— Pilih Divisi —</option>'].concat(
    state.divisions.map(
      (d) =>
        `<option value="${d.id}" ${String(d.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(d.name)}</option>`
    )
  );
  els.ownerDivision.innerHTML = options.join("");
}

async function loadBidangsForDivision(divisionId, selectedBidangId = "") {
  if (!els.ownerBidang) return;
  if (!divisionId) {
    els.ownerBidang.innerHTML = '<option value="">— Pilih Bidang —</option>';
    return;
  }
  let items = state.bidangsByDivision[divisionId] || state.bidangsByDivision[String(divisionId)];
  if (!items) {
    // Fallback: refresh ownership options (no organization.view required).
    await loadOrganizationOptions();
    items = state.bidangsByDivision[divisionId] || state.bidangsByDivision[String(divisionId)] || [];
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

async function applyOwnershipToForm(project = null) {
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

async function openModal(project = null) {
  els.form.reset();
  els.formError.hidden = true;
  els.formError.textContent = "";
  state.selectedPicIds = [];
  state.picSearch = "";
  els.picSearch.value = "";
  closePicDropdown();
  resetDocs();

  if (project) {
    els.modalTitle.textContent = "Edit Project";
    els.modalSubtitle.textContent = "Update the essential details for your project.";
    document.getElementById("project-id").value = project.id;
    document.getElementById("field-name").value = project.name || "";
    document.getElementById("field-description").value = project.description || "";
    document.getElementById("field-start").value = project.start_date || "";
    document.getElementById("field-end").value = project.end_date || "";
    document.getElementById("field-status").value = STATUS_VALUES.includes(project.status)
      ? project.status
      : "backlog";
    syncReleaseOption(project.progress);
    setSelectedPicsFromNames(project.pic || "");
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
  } else {
    els.modalTitle.textContent = "New Project";
    els.modalSubtitle.textContent = "Add the essential details for your project.";
    document.getElementById("project-id").value = "";
    document.getElementById("field-start").value = todayISO();
    document.getElementById("field-end").value = plusDaysISO(90);
    document.getElementById("field-status").value = "backlog";
    syncReleaseOption(0);
    syncPicField();
    await applyOwnershipToForm(null);
  }

  // Portal to <body> so position:fixed centers on the viewport.
  if (els.modal && els.modal.parentElement !== document.body) {
    document.body.appendChild(els.modal);
  }
  els.modal.hidden = false;
  document.body.classList.add("modal-open");
  document.getElementById("field-name").focus();
}

function syncReleaseOption(progress) {
  const select = document.getElementById("field-status");
  const releaseOpt = select?.querySelector('option[value="release"]');
  const hint = document.getElementById("status-release-hint");
  const ready = Math.round(Number(progress) || 0) >= 100;
  if (releaseOpt) {
    releaseOpt.disabled = !ready;
    if (!ready && select.value === "release") {
      select.value = "izin";
    }
  }
  if (hint) hint.hidden = ready;
}

function closeModal() {
  closePicDropdown();
  resetDocs();
  els.modal.hidden = true;
  document.body.classList.remove("modal-open");
}

async function loadStats() {
  const stats = await api("/api/projects/stats");
  renderStats(stats);
}

function renderWorkspacePicker() {
  if (!els.workspaceGrid) return;
  if (!state.workspaces.length) {
    els.workspaceGrid.innerHTML =
      `<div class="workspace-empty">Belum ada Bidang aktif di Divisi Anda.</div>`;
    return;
  }
  els.workspaceGrid.innerHTML = state.workspaces
    .map(
      (ws) => `
    <button type="button" class="workspace-card" data-workspace-id="${ws.id}">
      <div class="workspace-card-top">
        <span class="workspace-card-icon">${WORKSPACE_ICON}</span>
        <span class="workspace-card-count">${Number(ws.project_count || 0)} project</span>
      </div>
      <h3>${escapeHtml(ws.label || ws.name)}</h3>
      <p>${
        ws.leader_name
          ? `PIC Bidang: ${escapeHtml(ws.leader_name)}`
          : "Belum ada pemimpin Bidang"
      }</p>
    </button>`
    )
    .join("");
}

function syncWorkspaceView() {
  const usePicker = state.workspacesEnabled && !state.workspaceId;
  if (els.workspacePicker) els.workspacePicker.hidden = !usePicker;
  if (els.listView) els.listView.hidden = usePicker;

  const ws = state.workspace;
  const inWorkspace = Boolean(state.workspacesEnabled && ws);
  if (els.workspaceCrumb) els.workspaceCrumb.hidden = !inWorkspace;
  if (els.workspaceCrumbName && ws) {
    els.workspaceCrumbName.textContent = ws.label || ws.name;
  }
  if (els.projectsHero) els.projectsHero.classList.toggle("is-workspace", inWorkspace);
  if (els.projectsHeading) {
    els.projectsHeading.textContent = "Semua Project";
    els.projectsHeading.hidden = inWorkspace;
  }
  if (els.pageSubtitle) {
    els.pageSubtitle.textContent = usePicker
      ? "Pilih workspace Bidang"
      : "Kelola dan pantau project.";
  }
  if (els.workspacePickerSub) {
    els.workspacePickerSub.textContent = state.workspaceDivision?.name
      ? state.workspaceDivision.name
      : "Bidang di Divisi Anda";
  }
  if (els.btnNew) {
    const href = state.workspaceId
      ? `/projects/new?workspace=${state.workspaceId}`
      : "/projects/new";
    els.btnNew.setAttribute("href", href);
  }
}

async function loadWorkspaces() {
  try {
    const data = await api("/api/projects/workspaces");
    state.workspacesEnabled = Boolean(data.enabled);
    state.workspaces = Array.isArray(data.items) ? data.items : [];
    state.workspaceDivision = data.division || null;
  } catch {
    state.workspacesEnabled = false;
    state.workspaces = [];
    state.workspaceDivision = null;
  }

  const fromUrl = readWorkspaceFromUrl();
  if (state.workspacesEnabled && fromUrl) {
    state.workspace =
      state.workspaces.find((w) => Number(w.id) === Number(fromUrl)) || null;
    state.workspaceId = state.workspace ? Number(state.workspace.id) : null;
    if (!state.workspaceId) setWorkspaceUrl(null);
  } else {
    state.workspaceId = null;
    state.workspace = null;
  }
  renderWorkspacePicker();
  syncWorkspaceView();
}

function enterWorkspace(workspaceId) {
  const ws = state.workspaces.find((w) => Number(w.id) === Number(workspaceId));
  if (!ws) return;
  state.workspace = ws;
  state.workspaceId = Number(ws.id);
  state.page = 1;
  setWorkspaceUrl(state.workspaceId);
  syncWorkspaceView();
  return Promise.all([loadStats(), loadProjects()]);
}

function exitWorkspace() {
  state.workspace = null;
  state.workspaceId = null;
  state.page = 1;
  state.query = "";
  state.status = "";
  if (els.search) els.search.value = "";
  if (els.filter) els.filter.value = "";
  setWorkspaceUrl(null);
  syncWorkspaceView();
}

async function loadProjects() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.status) params.set("status", state.status);
  if (state.ownerType) params.set("owner_type", state.ownerType);
  if (state.workspaceId) {
    params.set("owner_type", "bidang");
    params.set("owner_bidang_id", String(state.workspaceId));
  }
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  const data = await api(`/api/projects?${params.toString()}`);
  state.projects = data.items || [];
  state.total = Number(data.total || 0);
  state.page = Number(data.page || 1);
  state.pages = Number(data.pages || 1);
  state.pageSize = Number(data.page_size || PAGE_SIZE);
  renderList();
}

async function goToPage(page) {
  const next = Math.max(1, Math.min(state.pages, Number(page) || 1));
  if (next === state.page) return;
  state.page = next;
  await loadProjects();
}

async function loadUsers() {
  state.users = await api("/api/team?active_only=true");
}

async function loadOrganizationOptions() {
  try {
    const data = await api("/api/organization/ownership-options");
    state.divisions = Array.isArray(data.divisions) ? data.divisions : [];
    state.bidangsByDivision = {};
    for (const b of Array.isArray(data.bidangs) ? data.bidangs : []) {
      const key = String(b.division_id);
      if (!state.bidangsByDivision[key]) state.bidangsByDivision[key] = [];
      state.bidangsByDivision[key].push(b);
    }
  } catch {
    state.divisions = [];
    state.bidangsByDivision = {};
  }
}

async function loadScopeStatus() {
  try {
    state.scopeStatus = await api("/api/projects/scope-status");
  } catch {
    state.scopeStatus = null;
  }
  if (els.ownerFilter) {
    els.ownerFilter.hidden = !state.isAdmin;
  }
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
  if (payload.end_date < payload.start_date) {
    els.formError.hidden = false;
    els.formError.textContent = "Target date must be on or after start date.";
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
    const saved = await (id
      ? api(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : api("/api/projects", { method: "POST", body: JSON.stringify(payload) }));

    if (state.pendingDocs.length) {
      await uploadPendingDocs(saved.id);
    }

    closeModal();
    if (!id) state.page = 1;
    await Promise.all([loadStats(), loadProjects()]);
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

  els.picSearch.addEventListener("focus", () => {
    openPicDropdown();
  });

  els.picSearch.addEventListener("input", () => {
    state.picSearch = els.picSearch.value;
    state.highlightIndex = 0;
    openPicDropdown();
  });

  els.picSearch.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !els.picSearch.value && state.selectedPicIds.length) {
      e.preventDefault();
      removePic(state.selectedPicIds[state.selectedPicIds.length - 1]);
      openPicDropdown();
      return;
    }

    if (els.picDropdown.hidden) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        openPicDropdown();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!state.suggestions.length) return;
      state.highlightIndex = (state.highlightIndex + 1) % state.suggestions.length;
      renderPicOptions();
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!state.suggestions.length) return;
      state.highlightIndex =
        (state.highlightIndex - 1 + state.suggestions.length) % state.suggestions.length;
      renderPicOptions();
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      const pick = state.suggestions[state.highlightIndex];
      if (pick) addPic(pick.id);
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      closePicDropdown();
    }
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
  // New/Edit project use dedicated pages (/projects/new, /projects/{id}/edit).

  els.list.addEventListener("click", (e) => {
    const editBtn = e.target.closest('[data-action="edit"]');
    if (editBtn) {
      e.preventDefault();
      e.stopPropagation();
      const id = Number(editBtn.dataset.id);
      if (id) window.location.href = `/projects/${id}/edit`;
      return;
    }

    const deleteBtn = e.target.closest('[data-action="delete"]');
    if (deleteBtn) {
      e.preventDefault();
      e.stopPropagation();
      deleteProject(deleteBtn.dataset.id);
      return;
    }

    if (e.target.closest("[data-action='tasks'], a.project-name-link")) return;

    const row = e.target.closest("tr.project-row[data-id]");
    if (!row) return;
    window.location.href = `/projects/${row.dataset.id}`;
  });

  els.list.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const row = e.target.closest("tr.project-row[data-id]");
    if (!row) return;
    e.preventDefault();
    window.location.href = `/projects/${row.dataset.id}`;
  });

  let searchTimer;
  els.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      state.query = els.search.value.trim();
      state.page = 1;
      await loadProjects();
    }, 250);
  });

  els.filter.addEventListener("change", async () => {
    state.status = els.filter.value;
    state.page = 1;
    await loadProjects();
  });

  els.ownerFilter?.addEventListener("change", async () => {
    state.ownerType = els.ownerFilter.value;
    state.page = 1;
    await loadProjects();
  });

  els.ownerType?.addEventListener("change", async () => {
    syncOwnershipFields();
    // Switching Divisi → Bidang must reload options for the already-selected division.
    if ((els.ownerType?.value || "") === "bidang") {
      await loadBidangsForDivision(els.ownerDivision?.value || "");
    }
  });

  els.ownerDivision?.addEventListener("change", async () => {
    if ((els.ownerType?.value || "") === "bidang") {
      await loadBidangsForDivision(els.ownerDivision.value || "");
    }
  });

  els.pagination?.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-page]");
    if (!btn || btn.disabled) return;
    const raw = btn.dataset.page;
    if (raw === "prev") await goToPage(state.page - 1);
    else if (raw === "next") await goToPage(state.page + 1);
    else await goToPage(raw);
  });

  els.workspaceGrid?.addEventListener("click", async (e) => {
    const card = e.target.closest("[data-workspace-id]");
    if (!card) return;
    try {
      await enterWorkspace(card.dataset.workspaceId);
    } catch (err) {
      els.list.innerHTML = `<tr><td colspan="10" class="list-empty">${escapeHtml(err.message || "Gagal membuka workspace")}</td></tr>`;
    }
  });

  els.btnBackWorkspaces?.addEventListener("click", () => {
    exitWorkspace();
  });

  const globalSearch = document.getElementById("search-input");
  globalSearch?.addEventListener("input", () => {
    els.search.value = globalSearch.value;
    els.search.dispatchEvent(new Event("input"));
  });
}

function resolveCanDelete(meRole) {
  const fromDom = els.page?.dataset?.canDelete === "1";
  const role = String(meRole || "").trim().toLowerCase();
  const fromApi = role === "admin" || role === "administrator";
  return Boolean(fromDom || fromApi);
}

async function loadCurrentUser() {
  // Server flag dulu (paling andal), API sebagai pelengkap
  state.canDelete = resolveCanDelete();
  state.isAdmin = state.canDelete;
  try {
    const me = await api("/api/auth/me");
    state.canDelete = resolveCanDelete(me.role);
    const role = String(me.role || "").trim().toLowerCase();
    state.isAdmin = state.canDelete || role === "admin" || role === "administrator";
  } catch {
    state.canDelete = resolveCanDelete();
    state.isAdmin = state.canDelete;
  }
}

async function boot() {
  wireEvents();
  try {
    await loadCurrentUser();
    await loadWorkspaces();
    const jobs = [loadUsers(), loadOrganizationOptions(), loadScopeStatus()];
    if (!state.workspacesEnabled || state.workspaceId) {
      jobs.unshift(loadStats(), loadProjects());
    }
    await Promise.all(jobs);
  } catch (err) {
    if (els.list) {
      els.list.innerHTML = `<tr><td colspan="10" class="list-empty">Failed to load projects: ${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

document.addEventListener("DOMContentLoaded", boot);
