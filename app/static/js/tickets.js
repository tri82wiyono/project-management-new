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

const PRIORITY_LABEL = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const STATUS_LABEL = {
  open: "Open",
  in_progress: "In Progress",
  done: "Resolved",
  closed: "Closed",
};

const state = {
  page: 1,
  pageSize: 10,
  q: "",
  projectId: "",
  moduleName: "",
  status: "",
  projects: [],
  users: [],
  filterModules: [],
  selectedPicIds: [],
  modules: [],
  pendingFiles: [],
  existingAttachments: [],
  suggestions: [],
  highlightIndex: -1,
  picSearch: "",
  editingId: null,
  openMenuId: null,
  suppressBackdropCloseUntil: 0,
};

const els = {
  list: document.getElementById("tickets-list"),
  pagination: document.getElementById("tickets-pagination"),
  statsTotal: document.getElementById("stat-total"),
  statsOpen: document.getElementById("stat-open"),
  statsProgress: document.getElementById("stat-progress"),
  statsResolved: document.getElementById("stat-resolved"),
  search: document.getElementById("ticket-search"),
  topSearch: document.getElementById("search-input"),
  projectFilter: document.getElementById("ticket-project-filter"),
  moduleFilter: document.getElementById("ticket-module-filter"),
  statusFilter: document.getElementById("ticket-status-filter"),
  btnNew: document.getElementById("btn-new-ticket"),
  modal: document.getElementById("ticket-modal"),
  form: document.getElementById("ticket-form"),
  modalTitle: document.getElementById("ticket-modal-title"),
  modalSubtitle: document.getElementById("ticket-modal-subtitle"),
  btnClose: document.getElementById("btn-close-modal"),
  btnCancel: document.getElementById("btn-cancel-modal"),
  formError: document.getElementById("form-error"),
  ticketId: document.getElementById("ticket-id"),
  ticketNumberField: document.getElementById("ticket-number-field"),
  ticketNumber: document.getElementById("field-ticket-number"),
  recordType: document.getElementById("field-record-type"),
  project: document.getElementById("field-project"),
  module: document.getElementById("field-module"),
  title: document.getElementById("field-title"),
  description: document.getElementById("field-description"),
  priority: document.getElementById("field-priority"),
  environment: document.getElementById("field-environment"),
  followUp: document.getElementById("field-follow-up"),
  status: document.getElementById("field-status"),
  picWrap: document.getElementById("pic-input-wrap"),
  picDropdown: document.getElementById("pic-dropdown"),
  picSearch: document.getElementById("pic-search"),
  picOptions: document.getElementById("pic-options"),
  picChips: document.getElementById("pic-chips"),
  dropzone: document.getElementById("attach-dropzone"),
  fileInput: document.getElementById("field-attachments"),
  fileList: document.getElementById("attach-file-list"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTarget(value) {
  if (!value) return "";
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}

function debounce(fn, wait = 280) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function safeUrl(url) {
  const value = String(url || "").trim();
  if (!value) return "";
  if (value.startsWith("/") || value.startsWith("https://") || value.startsWith("http://")) {
    return value;
  }
  return "";
}

function availableUsers(query = "") {
  const q = query.trim().toLowerCase();
  return state.users.filter((u) => {
    if (state.selectedPicIds.includes(u.id)) return false;
    if (!q) return true;
    return (
      String(u.name || "").toLowerCase().includes(q) ||
      String(u.email || "").toLowerCase().includes(q)
    );
  });
}

function syncPicPlaceholder() {
  if (!els.picSearch) return;
  els.picSearch.placeholder = state.selectedPicIds.length
    ? "Tambah PIC…"
    : "Ketik nama lalu pilih…";
}

function renderPicChips() {
  if (!els.picChips) return;
  const users = state.users.filter((u) => state.selectedPicIds.includes(u.id));
  els.picChips.innerHTML = users
    .map(
      (user) => `
    <span class="pic-chip">
      <span>${escapeHtml(user.name)}</span>
      <button type="button" data-remove-pic="${user.id}" aria-label="Hapus ${escapeHtml(user.name)}">×</button>
    </span>`
    )
    .join("");
  syncPicPlaceholder();
}

function renderPicOptions() {
  state.suggestions = availableUsers(state.picSearch).slice(0, 12);
  if (!state.suggestions.length) {
    els.picOptions.innerHTML = `<div class="pic-empty">${
      state.picSearch.trim() ? "Tidak ada hasil" : "Semua user sudah dipilih"
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
        <span>${escapeHtml(user.email || user.role || "")}</span>
      </button>`
    )
    .join("");
}

function openPicDropdown() {
  els.picDropdown.hidden = false;
  els.picWrap.classList.add("open");
  els.picSearch.setAttribute("aria-expanded", "true");
  state.highlightIndex = state.suggestions.length ? 0 : -1;
  renderPicOptions();
}

function closePicDropdown() {
  if (!els.picDropdown || !els.picWrap || !els.picSearch) return;
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
  renderPicChips();
  renderPicOptions();
  els.picSearch.focus();
}

function removePic(userId) {
  const id = Number(userId);
  state.selectedPicIds = state.selectedPicIds.filter((x) => x !== id);
  renderPicChips();
  if (!els.picDropdown.hidden) renderPicOptions();
}

function fillProjectSelects() {
  const options = state.projects
    .map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)
    .join("");
  els.projectFilter.innerHTML = `<option value="">Semua Project</option>${options}`;
  els.project.innerHTML = `<option value="">Pilih project…</option>${options}`;
}

function fillModuleFilter() {
  const current = state.moduleName;
  const options = state.filterModules
    .map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`)
    .join("");
  els.moduleFilter.innerHTML = `<option value="">Semua Modul</option>${options}`;
  if (current && state.filterModules.includes(current)) {
    els.moduleFilter.value = current;
  } else {
    state.moduleName = "";
    els.moduleFilter.value = "";
  }
}

function renderModules(selected = "") {
  if (!els.module) return;
  const projectId = els.project?.value || "";
  if (!projectId) {
    els.module.disabled = true;
    els.module.innerHTML = `<option value="">Pilih project dulu…</option>`;
    return;
  }

  const options = [...state.modules];
  const selectedValue = (selected || "").trim();
  if (selectedValue && !options.some((m) => m.casefold() === selectedValue.casefold())) {
    options.unshift(selectedValue);
  }

  if (!options.length) {
    els.module.disabled = true;
    els.module.innerHTML = `<option value="">Belum ada modul di project ini</option>`;
    return;
  }

  els.module.disabled = false;
  els.module.innerHTML =
    `<option value="">Pilih modul…</option>` +
    options.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("");
  if (selectedValue) {
    els.module.value = selectedValue;
    if (els.module.value !== selectedValue) {
      // Fallback if browser option matching is strict
      const match = options.find((m) => m.casefold() === selectedValue.casefold());
      if (match) els.module.value = match;
    }
  } else {
    els.module.value = "";
  }
}

async function loadModulesForProject(projectId, selected = "") {
  state.modules = [];
  if (!projectId) {
    renderModules();
    return;
  }
  try {
    const data = await api(`/api/tickets/modules?project_id=${projectId}`);
    state.modules = data.modules || [];
  } catch {
    state.modules = [];
  }
  renderModules(selected);
}

async function loadFilterModules() {
  try {
    const params = new URLSearchParams();
    if (state.projectId) params.set("project_id", state.projectId);
    const qs = params.toString();
    const data = await api(`/api/tickets/modules${qs ? `?${qs}` : ""}`);
    state.filterModules = data.modules || [];
  } catch {
    state.filterModules = [];
  }
  fillModuleFilter();
}

function renderAttachments() {
  if (!els.fileList) return;
  const pending = state.pendingFiles.map((file, index) => ({
    kind: "pending",
    index,
    name: file.name,
    size: file.size,
  }));
  const existing = state.existingAttachments.map((a) => ({
    kind: "existing",
    id: a.id,
    name: a.original_name,
    size: a.size_bytes,
    url: a.download_url,
  }));
  const items = [...existing, ...pending];
  if (!items.length) {
    els.fileList.hidden = true;
    els.fileList.innerHTML = "";
    return;
  }
  els.fileList.hidden = false;
  els.fileList.innerHTML = items
    .map((item) => {
      const sizeKb = item.size ? `${Math.max(1, Math.round(item.size / 1024))} KB` : "";
      const link =
        item.kind === "existing" && item.url
          ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.name)}</a>`
          : `<span>${escapeHtml(item.name)}</span>`;
      const removeAttr =
        item.kind === "pending"
          ? `data-remove-pending="${item.index}"`
          : `data-remove-existing="${item.id}"`;
      return `<li>${link}<em>${sizeKb}</em><button type="button" ${removeAttr} aria-label="Hapus">×</button></li>`;
    })
    .join("");
}

function addPendingFiles(fileList) {
  const incoming = Array.from(fileList || []);
  const maxTotal = 5;
  const room = maxTotal - (state.existingAttachments.length + state.pendingFiles.length);
  if (room <= 0) {
    showError(`Maksimal ${maxTotal} lampiran`);
    return;
  }
  state.pendingFiles.push(...incoming.slice(0, room));
  renderAttachments();
}

function showError(message) {
  if (!els.formError) return;
  els.formError.hidden = !message;
  els.formError.textContent = message || "";
}

function priorityBadge(priority) {
  const icons = {
    low: `<svg viewBox="0 0 24 24" fill="none"><path d="m7 10 5 5 5-5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    medium: `<svg viewBox="0 0 24 24" fill="none"><path d="M7 12h10" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`,
    high: `<svg viewBox="0 0 24 24" fill="none"><path d="m7 14 5-5 5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    critical: `<svg viewBox="0 0 24 24" fill="none"><path d="m7 16 5-5 5 5M7 11l5-5 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  };
  return `<span class="tk-prio prio-${escapeHtml(priority)}">${icons[priority] || ""}${escapeHtml(
    PRIORITY_LABEL[priority] || priority
  )}</span>`;
}

function statusBadge(status) {
  return `<span class="tk-status status-${escapeHtml(status)}">${escapeHtml(
    STATUS_LABEL[status] || status
  )}</span>`;
}

function nameInitials(name) {
  const parts = String(name || "?")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

function hasPhoto(url) {
  const value = String(url || "").trim().toLowerCase();
  if (!value) return false;
  if (value.includes("dicebear.com")) return false;
  if (value.startsWith("data:image/svg")) return false;
  return true;
}

function picCell(item) {
  const pics = item.pics || [];
  if (!pics.length) return `<span class="tk-pic-more">—</span>`;
  const first = pics[0];
  const avatar = safeUrl(first.avatar_url);
  const extra = pics.length > 1 ? `<span class="tk-pic-more">+${pics.length - 1}</span>` : "";
  const initial = escapeHtml(nameInitials(first.name));
  const img = hasPhoto(avatar)
    ? `<img src="${escapeHtml(avatar)}" alt="${escapeHtml(first.name)}" />`
    : `<span class="tk-pic-fallback">${initial}</span>`;
  return `<div class="tk-pic" title="${escapeHtml(pics.map((p) => p.name).join(", "))}">${img}<span>${escapeHtml(
    first.name
  )}</span>${extra}</div>`;
}

function targetCell(value) {
  const label = formatTarget(value);
  if (!label) {
    return `<span class="tk-target is-empty">—</span>`;
  }
  return `<span class="tk-target"><svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="5" width="17" height="15" rx="2.5" stroke="currentColor" stroke-width="1.7"/><path d="M8 3.5v3M16 3.5v3M3.5 9.5h17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>${escapeHtml(
    label
  )}</span>`;
}

function closeActionMenus() {
  state.openMenuId = null;
}

function mountModalToBody() {
  if (!els.modal) return;
  if (els.modal.parentElement !== document.body) {
    document.body.appendChild(els.modal);
  }
}

function openModal(edit = null) {
  if (!els.modal) return;
  closeActionMenus();
  mountModalToBody();
  state.editingId = edit?.id || null;
  state.selectedPicIds = edit?.pic_ids ? [...edit.pic_ids] : [];
  state.pendingFiles = [];
  state.existingAttachments = edit?.attachments ? [...edit.attachments] : [];
  state.picSearch = "";
  if (els.picSearch) els.picSearch.value = "";
  if (els.ticketId) els.ticketId.value = edit?.id || "";
  if (els.ticketNumberField && els.ticketNumber) {
    if (edit?.ticket_number) {
      els.ticketNumberField.hidden = false;
      els.ticketNumber.value = edit.ticket_number;
    } else {
      els.ticketNumberField.hidden = true;
      els.ticketNumber.value = "";
    }
  }
  if (els.recordType) els.recordType.value = edit?.record_type || "ticket_kendala";
  if (els.project) els.project.value = edit?.project_id ? String(edit.project_id) : "";
  if (els.title) els.title.value = edit?.title || "";
  if (els.description) els.description.value = edit?.description || "";
  if (els.priority) els.priority.value = edit?.priority || "medium";
  if (els.environment) els.environment.value = edit?.environment || "development";
  if (els.followUp) els.followUp.value = edit?.follow_up_target || "";
  if (els.status) els.status.value = edit?.status || "open";
  if (els.modalTitle) els.modalTitle.textContent = edit ? "Edit Tiket" : "Tambah Tiket";
  if (els.modalSubtitle) {
    els.modalSubtitle.textContent = edit
      ? "Perbarui detail pencatatan."
      : "Isi detail pencatatan untuk project yang dipilih.";
  }
  showError("");
  renderPicChips();
  closePicDropdown();
  renderAttachments();
  renderModules();
  loadModulesForProject(els.project?.value || "", edit?.module_name || "");
  state.suppressBackdropCloseUntil = Date.now() + 800;
  els.modal.hidden = false;
  els.modal.classList.add("is-open");
  document.body.classList.add("tk-modal-open");
  // Focus first field so the open button doesn't keep focus / receive the next key/click.
  window.setTimeout(() => {
    if (els.project && !els.project.value) els.project.focus();
    else if (els.module && !els.module.disabled && !els.module.value) els.module.focus();
    else if (els.title) els.title.focus();
  }, 0);
}

function closeModal() {
  if (!els.modal) return;
  els.modal.classList.remove("is-open");
  els.modal.hidden = true;
  document.body.classList.remove("tk-modal-open");
  state.editingId = null;
  state.pendingFiles = [];
  state.existingAttachments = [];
  state.suppressBackdropCloseUntil = 0;
  showError("");
}

function renderStats(stats) {
  els.statsTotal.textContent = String(stats?.total ?? 0);
  els.statsOpen.textContent = String(stats?.open ?? 0);
  els.statsProgress.textContent = String(stats?.in_progress ?? 0);
  els.statsResolved.textContent = String(stats?.resolved ?? 0);
}

function renderRows(items) {
  if (!items.length) {
    els.list.innerHTML = `<tr><td colspan="9" class="tickets-empty">Belum ada tiket. Klik “Tambah Tiket” untuk menambah.</td></tr>`;
    return;
  }
  els.list.innerHTML = items
    .map(
      (item) => `
      <tr data-id="${item.id}">
        <td>
          <button type="button" class="ticket-number-link" data-edit="${item.id}">
            ${escapeHtml(item.ticket_number || "—")}
          </button>
        </td>
        <td class="ticket-title-cell"><strong>${escapeHtml(item.title)}</strong></td>
        <td class="tk-clip" title="${escapeHtml(item.project_name || "")}">${escapeHtml(item.project_name || "—")}</td>
        <td class="tk-clip" title="${escapeHtml(item.module_name || "")}">${escapeHtml(item.module_name || "—")}</td>
        <td>${priorityBadge(item.priority)}</td>
        <td>${statusBadge(item.status)}</td>
        <td>${picCell(item)}</td>
        <td>${targetCell(item.follow_up_target)}</td>
        <td class="col-actions">
          <div class="tk-actions-inline">
            <button type="button" class="tk-link-btn" data-edit="${item.id}">Edit</button>
            <button type="button" class="tk-link-btn is-danger" data-delete="${item.id}">Hapus</button>
          </div>
        </td>
      </tr>`
    )
    .join("");
}

function renderPagination(data) {
  const { page, pages, total, page_size: pageSize } = data;
  const start = total ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(page * pageSize, total);
  const info = `Menampilkan ${start} - ${end} dari ${total} tiket`;

  const pageButtons = [];
  const windowStart = Math.max(1, page - 2);
  const windowEnd = Math.min(pages || 1, windowStart + 4);
  for (let i = windowStart; i <= windowEnd; i += 1) {
    pageButtons.push(
      `<button type="button" class="tk-page-btn${i === page ? " is-active" : ""}" data-page="${i}">${i}</button>`
    );
  }

  els.pagination.innerHTML = `
    <span class="tk-page-info">${info}</span>
    <div class="tk-page-controls">
      <button type="button" class="tk-page-btn" data-page="${page - 1}" ${
        page <= 1 ? "disabled" : ""
      } aria-label="Sebelumnya">‹</button>
      ${pageButtons.join("")}
      <button type="button" class="tk-page-btn" data-page="${page + 1}" ${
        page >= (pages || 1) ? "disabled" : ""
      } aria-label="Berikutnya">›</button>
    </div>
  `;
}

async function loadStats() {
  try {
    const stats = await api("/api/tickets/stats");
    renderStats(stats);
  } catch {
    renderStats({ total: 0, open: 0, in_progress: 0, resolved: 0 });
  }
}

async function loadTickets() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  if (state.q) params.set("q", state.q);
  if (state.projectId) params.set("project_id", state.projectId);
  if (state.moduleName) params.set("module_name", state.moduleName);
  if (state.status) params.set("status", state.status);

  const data = await api(`/api/tickets?${params.toString()}`);
  renderRows(data.items || []);
  renderPagination(data);
}

async function refreshAll() {
  await Promise.all([loadTickets(), loadStats(), loadFilterModules()]);
}

async function uploadPending(ticketId) {
  if (!state.pendingFiles.length) return;
  const form = new FormData();
  state.pendingFiles.forEach((file) => form.append("files", file));
  const res = await fetch(`/api/tickets/${ticketId}/attachments`, {
    method: "POST",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Upload lampiran gagal (${res.status})`
    );
  }
}

async function saveTicket(event) {
  event.preventDefault();
  showError("");

  const projectId = Number(els.project.value);
  if (!projectId) {
    showError("Project wajib dipilih");
    return;
  }
  const moduleName = (els.module?.value || "").trim();
  if (!moduleName) {
    showError(
      els.module?.disabled
        ? "Project belum punya modul. Tambah task/modul di project dulu."
        : "Modul wajib dipilih dari project"
    );
    return;
  }
  if (!els.title.value.trim()) {
    showError("Judul kendala wajib diisi");
    return;
  }
  if (!state.selectedPicIds.length) {
    showError("Pilih minimal satu PIC");
    return;
  }

  const payload = {
    record_type: els.recordType.value,
    project_id: projectId,
    module_name: moduleName,
    title: els.title.value.trim(),
    description: els.description.value.trim() || null,
    priority: els.priority.value,
    environment: els.environment.value,
    follow_up_target: els.followUp.value || null,
    pic_ids: state.selectedPicIds,
  };
  if (state.editingId) {
    payload.status = els.status.value;
  }

  try {
    let ticket;
    if (state.editingId) {
      ticket = await api(`/api/tickets/${state.editingId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    } else {
      ticket = await api("/api/tickets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    await uploadPending(ticket.id);
    closeModal();
    await refreshAll();
  } catch (err) {
    showError(err.message || "Gagal menyimpan ticket");
  }
}

async function editTicket(id) {
  try {
    const ticket = await api(`/api/tickets/${id}`);
    openModal(ticket);
  } catch (err) {
    alert(err.message || "Gagal memuat ticket");
  }
}

async function deleteTicket(id) {
  if (!confirm("Hapus ticket ini?")) return;
  try {
    await api(`/api/tickets/${id}`, { method: "DELETE" });
    closeActionMenus();
    await refreshAll();
  } catch (err) {
    alert(err.message || "Gagal menghapus ticket");
  }
}

function bindEvents() {
  const onSearch = debounce(() => {
    state.q = (els.search.value || els.topSearch?.value || "").trim();
    state.page = 1;
    loadTickets().catch(console.error);
  });

  els.search?.addEventListener("input", onSearch);
  els.topSearch?.addEventListener("input", () => {
    if (els.search) els.search.value = els.topSearch.value;
    onSearch();
  });

  els.projectFilter?.addEventListener("change", async () => {
    state.projectId = els.projectFilter.value;
    state.moduleName = "";
    state.page = 1;
    await loadFilterModules();
    loadTickets().catch(console.error);
  });
  els.moduleFilter?.addEventListener("change", () => {
    state.moduleName = els.moduleFilter.value;
    state.page = 1;
    loadTickets().catch(console.error);
  });
  els.statusFilter?.addEventListener("change", () => {
    state.status = els.statusFilter.value;
    state.page = 1;
    loadTickets().catch(console.error);
  });

  els.btnNew?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openModal();
  });
  els.btnClose?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeModal();
  });
  els.btnCancel?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeModal();
  });
  // Backdrop click closed the modal immediately for some users; disable it.
  // Close only via × / Batal / Escape.
  els.form?.addEventListener("submit", (e) => {
    e.preventDefault();
    e.stopPropagation();
    saveTicket(e);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.modal && !els.modal.hidden) {
      if (els.picDropdown && !els.picDropdown.hidden) {
        closePicDropdown();
        return;
      }
      closeModal();
    }
  });

  els.project?.addEventListener("change", () => {
    loadModulesForProject(els.project.value, "");
  });

  els.picSearch?.addEventListener("focus", openPicDropdown);
  els.picSearch?.addEventListener("input", () => {
    state.picSearch = els.picSearch.value;
    openPicDropdown();
  });
  els.picSearch?.addEventListener("keydown", (e) => {
    if (els.picDropdown.hidden) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.highlightIndex = Math.min(
        state.highlightIndex + 1,
        state.suggestions.length - 1
      );
      renderPicOptions();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.highlightIndex = Math.max(state.highlightIndex - 1, 0);
      renderPicOptions();
    } else if (e.key === "Enter") {
      e.preventDefault();
      const pick = state.suggestions[state.highlightIndex];
      if (pick) addPic(pick.id);
    } else if (e.key === "Escape") {
      closePicDropdown();
    }
  });
  els.picOptions?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-pic-id]");
    if (btn) addPic(btn.dataset.picId);
  });
  els.picChips?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-pic]");
    if (btn) removePic(btn.dataset.removePic);
  });

  els.dropzone?.addEventListener("click", () => els.fileInput.click());
  els.fileInput?.addEventListener("change", () => {
    addPendingFiles(els.fileInput.files);
    els.fileInput.value = "";
  });
  els.dropzone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropzone.classList.add("dragover");
  });
  els.dropzone?.addEventListener("dragleave", () => {
    els.dropzone.classList.remove("dragover");
  });
  els.dropzone?.addEventListener("drop", (e) => {
    e.preventDefault();
    els.dropzone.classList.remove("dragover");
    addPendingFiles(e.dataTransfer.files);
  });
  els.fileList?.addEventListener("click", async (e) => {
    const pending = e.target.closest("[data-remove-pending]");
    if (pending) {
      const idx = Number(pending.dataset.removePending);
      state.pendingFiles = state.pendingFiles.filter((_, i) => i !== idx);
      renderAttachments();
      return;
    }
    const existing = e.target.closest("[data-remove-existing]");
    if (existing && state.editingId) {
      const id = Number(existing.dataset.removeExisting);
      try {
        await api(`/api/tickets/${state.editingId}/attachments/${id}`, {
          method: "DELETE",
        });
        state.existingAttachments = state.existingAttachments.filter((a) => a.id !== id);
        renderAttachments();
      } catch (err) {
        showError(err.message || "Gagal menghapus lampiran");
      }
    }
  });

  els.list?.addEventListener("click", (e) => {
    const editBtn = e.target.closest("[data-edit]");
    if (editBtn) {
      editTicket(Number(editBtn.dataset.edit));
      return;
    }
    const delBtn = e.target.closest("[data-delete]");
    if (delBtn) deleteTicket(Number(delBtn.dataset.delete));
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#pic-multiselect")) closePicDropdown();
  });

  els.pagination?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-page]");
    if (!btn || btn.disabled) return;
    state.page = Number(btn.dataset.page);
    loadTickets().catch(console.error);
  });
}

async function init() {
  bindEvents();
  try {
    const [projectsRes, users] = await Promise.all([
      api("/api/projects?page=1&page_size=100"),
      api("/api/team?active_only=true"),
    ]);
    state.projects = projectsRes.items || [];
    state.users = users || [];
    fillProjectSelects();
    await refreshAll();
  } catch (err) {
    els.list.innerHTML = `<tr><td colspan="9" class="tickets-empty">${escapeHtml(
      err.message || "Gagal memuat data"
    )}</td></tr>`;
  }
}

init();
