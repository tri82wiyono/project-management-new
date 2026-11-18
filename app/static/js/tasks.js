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

const STATUS_LABELS = {
  todo: "To Do",
  in_progress: "In Progress",
  review: "Review",
  done: "Done",
};

const STATUS_ORDER = ["todo", "in_progress", "review", "done"];

const state = {
  projectId: null,
  projects: [],
  users: [],
  columns: [],
  query: "",
  dragTaskId: null,
  selectedAssigneeIds: [],
  assigneeSearch: "",
  assigneeSuggestions: [],
  assigneeHighlight: -1,
};

const els = {
  board: document.getElementById("kanban-board"),
  stats: document.getElementById("tasks-stats"),
  count: document.getElementById("tasks-count"),
  info: document.getElementById("tasks-project-info"),
  subtitle: document.getElementById("tasks-subtitle"),
  filter: document.getElementById("tasks-project-filter"),
  search: document.getElementById("tasks-search"),
  btnNew: document.getElementById("btn-new-task"),
  modal: document.getElementById("task-modal"),
  form: document.getElementById("task-form"),
  formError: document.getElementById("task-form-error"),
  modalTitle: document.getElementById("task-modal-title"),
  modalSubtitle: document.getElementById("task-modal-subtitle"),
  btnClose: document.getElementById("btn-close-task-modal"),
  btnCancel: document.getElementById("btn-cancel-task-modal"),
  btnDelete: document.getElementById("btn-delete-task"),
  fieldId: document.getElementById("task-id"),
  fieldTitle: document.getElementById("field-task-title"),
  fieldDescription: document.getElementById("field-task-description"),
  fieldProject: document.getElementById("field-task-project"),
  fieldStatus: document.getElementById("field-task-status"),
  fieldCategory: document.getElementById("field-task-category"),
  fieldPriority: document.getElementById("field-task-priority"),
  fieldDue: document.getElementById("field-task-due"),
  duePicker: document.getElementById("due-datepicker"),
  dueTrigger: document.getElementById("due-datepicker-trigger"),
  dueValue: document.getElementById("due-datepicker-value"),
  duePanel: document.getElementById("due-datepicker-panel"),
  dueGrid: document.getElementById("due-datepicker-grid"),
  dueMonthLabel: document.getElementById("due-month-label"),
  duePrev: document.getElementById("due-prev-month"),
  dueNext: document.getElementById("due-next-month"),
  dueClear: document.getElementById("due-clear"),
  dueToday: document.getElementById("due-today"),
  assigneeWrap: document.getElementById("assignee-input-wrap"),
  assigneeSearch: document.getElementById("assignee-search"),
  assigneeDropdown: document.getElementById("assignee-dropdown"),
  assigneeOptions: document.getElementById("assignee-options"),
  assigneeChips: document.getElementById("assignee-chips"),
};

const MONTH_NAMES = [
  "Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember",
];

let dueView = new Date();
dueView.setDate(1);
dueView.setHours(0, 0, 0, 0);

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseISODate(value) {
  if (!value) return null;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDueDisplay(value) {
  const date = parseISODate(value);
  if (!date) return "Pilih tanggal";
  return `${date.getDate()} ${MONTH_NAMES[date.getMonth()]} ${date.getFullYear()}`;
}

function syncDueDisplay() {
  const value = els.fieldDue.value || "";
  els.dueValue.textContent = formatDueDisplay(value);
  els.dueValue.classList.toggle("is-placeholder", !value);
}

function setDueDate(iso) {
  els.fieldDue.value = iso || "";
  syncDueDisplay();
  if (iso) {
    const date = parseISODate(iso);
    if (date) {
      dueView = new Date(date.getFullYear(), date.getMonth(), 1);
    }
  }
  renderDueCalendar();
}

function isDueOpen() {
  return els.duePicker?.dataset.open === "true";
}

function openDuePicker() {
  if (!els.duePanel) return;
  const selected = parseISODate(els.fieldDue.value);
  dueView = selected
    ? new Date(selected.getFullYear(), selected.getMonth(), 1)
    : (() => {
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), 1);
      })();
  renderDueCalendar();
  els.duePanel.hidden = false;
  els.duePicker.dataset.open = "true";
  els.dueTrigger.setAttribute("aria-expanded", "true");
}

function closeDuePicker() {
  if (!els.duePanel) return;
  els.duePanel.hidden = true;
  els.duePicker.dataset.open = "false";
  els.dueTrigger.setAttribute("aria-expanded", "false");
}

function renderDueCalendar() {
  if (!els.dueGrid || !els.dueMonthLabel) return;
  const year = dueView.getFullYear();
  const month = dueView.getMonth();
  els.dueMonthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;

  const first = new Date(year, month, 1);
  // Monday-first offset: Mon=0 ... Sun=6
  const startOffset = (first.getDay() + 6) % 7;
  const start = new Date(year, month, 1 - startOffset);
  const selected = els.fieldDue.value;
  const today = toISODate(new Date());

  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const cell = new Date(start);
    cell.setDate(start.getDate() + i);
    const iso = toISODate(cell);
    const muted = cell.getMonth() !== month;
    const classes = ["datepicker-day"];
    if (muted) classes.push("is-muted");
    if (iso === today) classes.push("is-today");
    if (iso === selected) classes.push("is-selected");
    cells.push(
      `<button type="button" class="${classes.join(" ")}" data-date="${iso}" aria-label="${iso}">${cell.getDate()}</button>`
    );
  }
  els.dueGrid.innerHTML = cells.join("");
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function tagClass(category = "") {
  return category.toLowerCase().replace(/[^a-z]/g, "");
}

function getProjectIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("project_id");
  return raw ? Number(raw) : null;
}

function findTask(taskId) {
  for (const col of state.columns) {
    const task = col.tasks.find((t) => t.id === Number(taskId));
    if (task) return task;
  }
  return null;
}

function taskAssignees(task) {
  if (Array.isArray(task.assignees) && task.assignees.length) return task.assignees;
  return task.assignee ? [task.assignee] : [];
}

function selectedAssigneeUsers() {
  const selected = new Set(state.selectedAssigneeIds.map(Number));
  return state.users.filter((u) => selected.has(Number(u.id)));
}

function availableAssignees(query = "") {
  const q = query.trim().toLowerCase();
  const selected = new Set(state.selectedAssigneeIds.map(Number));
  return state.users.filter((user) => {
    if (selected.has(Number(user.id))) return false;
    if (!q) return true;
    return (
      user.name.toLowerCase().includes(q) ||
      String(user.email || "").toLowerCase().includes(q) ||
      String(user.role || "").toLowerCase().includes(q)
    );
  });
}

function renderAssigneeChips() {
  const users = selectedAssigneeUsers();
  els.assigneeChips.innerHTML = users
    .map(
      (user) => `
    <span class="assignee-chip">
      <span>${escapeHtml(user.name)}</span>
      <button type="button" data-remove-assignee="${user.id}" aria-label="Hapus ${escapeHtml(user.name)}">×</button>
    </span>`
    )
    .join("");
  els.assigneeSearch.placeholder = users.length ? "Tambah orang…" : "Ketik nama lalu pilih…";
}

function renderAssigneeOptions() {
  state.assigneeSuggestions = availableAssignees(state.assigneeSearch).slice(0, 12);
  if (!state.assigneeSuggestions.length) {
    state.assigneeHighlight = -1;
    els.assigneeOptions.innerHTML = `<div class="assignee-empty">${
      state.assigneeSearch.trim() ? "Tidak ada nama yang cocok." : "Semua user sudah dipilih."
    }</div>`;
    return;
  }
  if (state.assigneeHighlight < 0 || state.assigneeHighlight >= state.assigneeSuggestions.length) {
    state.assigneeHighlight = 0;
  }
  els.assigneeOptions.innerHTML = state.assigneeSuggestions
    .map(
      (user, index) => `
    <button
      type="button"
      class="assignee-option${index === state.assigneeHighlight ? " active" : ""}"
      data-assignee-id="${user.id}"
      data-index="${index}"
    >
      <span>${escapeHtml(user.name)}</span>
      <small>${escapeHtml(user.role || "")}</small>
    </button>`
    )
    .join("");
}

function openAssigneeDropdown() {
  els.assigneeDropdown.hidden = false;
  els.assigneeWrap.classList.add("open");
  renderAssigneeOptions();
}

function closeAssigneeDropdown() {
  els.assigneeDropdown.hidden = true;
  els.assigneeWrap.classList.remove("open");
  state.assigneeHighlight = -1;
}

function addAssignee(userId) {
  const id = Number(userId);
  if (!Number.isFinite(id) || id <= 0) return;
  if (state.selectedAssigneeIds.some((x) => Number(x) === id)) return;
  state.selectedAssigneeIds = [...state.selectedAssigneeIds.map(Number), id];
  state.assigneeSearch = "";
  els.assigneeSearch.value = "";
  renderAssigneeChips();
  openAssigneeDropdown();
  els.assigneeSearch.focus();
}

function commitAssigneeSearch() {
  const q = els.assigneeSearch.value.trim().toLowerCase();
  if (!q) return;
  const exact = state.users.find((u) => u.name.toLowerCase() === q);
  const partial = availableAssignees(q);
  if (exact) addAssignee(exact.id);
  else if (partial.length === 1) addAssignee(partial[0].id);
}

function removeAssignee(userId) {
  const id = Number(userId);
  state.selectedAssigneeIds = state.selectedAssigneeIds.filter((x) => x !== id);
  renderAssigneeChips();
  if (!els.assigneeDropdown.hidden) renderAssigneeOptions();
}

function setSelectedAssignees(task = null) {
  let ids = [];
  if (!task) {
    ids = [];
  } else if (Array.isArray(task.assignee_ids) && task.assignee_ids.length) {
    ids = task.assignee_ids;
  } else if (Array.isArray(task.assignees) && task.assignees.length) {
    ids = task.assignees.map((u) => u.id);
  } else if (task.assignee_id) {
    ids = [task.assignee_id];
  }
  state.selectedAssigneeIds = [...new Set(ids.map(Number).filter((n) => Number.isFinite(n) && n > 0))];
  state.assigneeSearch = "";
  els.assigneeSearch.value = "";
  renderAssigneeChips();
  closeAssigneeDropdown();
}

function filteredColumns() {
  const q = state.query.trim().toLowerCase();
  if (!q) return state.columns;

  return state.columns.map((col) => {
    const tasks = col.tasks.filter((task) => {
      const names = taskAssignees(task).map((u) => u.name).join(" ");
      const hay = `${task.title || ""} ${task.category || ""} ${task.project_name || ""} ${names}`.toLowerCase();
      return hay.includes(q);
    });
    return { ...col, tasks, count: tasks.length };
  });
}

function fillSelects() {
  els.fieldProject.innerHTML = state.projects
    .map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)
    .join("") || `<option value="">No projects</option>`;
}

function renderAssigneeAvatars(task) {
  const people = taskAssignees(task).slice(0, 3);
  if (!people.length) return "<span></span>";
  const extra = Math.max(0, taskAssignees(task).length - people.length);
  return `
    <div class="mini-avatar-stack" title="${escapeHtml(taskAssignees(task).map((u) => u.name).join(", "))}">
      ${people
        .map(
          (u) =>
            `<img class="mini-avatar" src="${escapeHtml(u.avatar_url)}" alt="${escapeHtml(u.name)}" title="${escapeHtml(u.name)}" />`
        )
        .join("")}
      ${extra ? `<span class="mini-avatar-extra">+${extra}</span>` : ""}
    </div>`;
}

function renderStats() {
  const cols = filteredColumns();
  const total = cols.reduce((sum, col) => sum + col.count, 0);
  const byStatus = Object.fromEntries(cols.map((col) => [col.status, col.count]));

  els.stats.innerHTML = `
    <article class="tasks-stat">
      <span>Total Tasks</span>
      <strong>${total}</strong>
    </article>
    ${STATUS_ORDER.map((status) => `
      <article class="tasks-stat status-${status}">
        <span>${STATUS_LABELS[status]}</span>
        <strong>${byStatus[status] || 0}</strong>
      </article>
    `).join("")}
  `;
  els.count.textContent = `${total} tasks`;
}

function renderBoard() {
  const cols = filteredColumns();
  const showProject = !state.projectId;

  els.board.innerHTML = cols
    .map((col) => `
    <div class="kanban-col status-${col.status}" data-status="${col.status}">
      <div class="kanban-col-head">
        <h3>
          <span class="kanban-status-label"><i class="kanban-dot" aria-hidden="true"></i>${STATUS_LABELS[col.status] || col.label}</span>
          <span class="kanban-count">${col.count}</span>
        </h3>
        <button type="button" class="btn-col-add" data-add-status="${col.status}" title="Add task">+</button>
      </div>
      <div class="kanban-dropzone" data-drop-status="${col.status}">
        ${col.tasks
          .map((task) => `
          <article
            class="task-card status-${col.status}"
            draggable="true"
            data-task-id="${task.id}"
            data-action="edit"
          >
            ${showProject && task.project_name
              ? `<span class="task-project">${escapeHtml(task.project_name)}</span>`
              : ""}
            <h4>${escapeHtml(task.title)}</h4>
            <div class="task-card-foot">
              <span class="tag ${tagClass(task.category)}">${escapeHtml(task.category || "General")}</span>
              ${renderAssigneeAvatars(task)}
            </div>
            <div class="task-card-hint">Drag to move · click to edit</div>
          </article>`)
          .join("") || `<div class="kanban-empty">No tasks</div>`}
      </div>
    </div>`)
    .join("");
}

function renderHeader() {
  const project = state.projectId
    ? state.projects.find((p) => p.id === state.projectId)
    : null;

  if (project) {
    els.info.innerHTML = `
      <strong>${escapeHtml(project.name)}</strong>
      <span>PIC: ${escapeHtml(project.pic || "-")} · ${Math.round(project.progress || 0)}% · status ${escapeHtml(project.status)}</span>
    `;
    els.subtitle.textContent = `Kanban untuk project: ${project.name}`;
  } else {
    const total = state.columns.reduce((sum, col) => sum + col.count, 0);
    els.info.innerHTML = `
      <strong>All Projects</strong>
      <span>${total} task · pilih project untuk fokus, atau tambah task baru</span>
    `;
    els.subtitle.textContent = "Kanban semua project";
  }
}

function openModal(task = null, presetStatus = "todo") {
  els.form.reset();
  els.formError.hidden = true;
  els.formError.textContent = "";
  fillSelects();
  setSelectedAssignees(task);

  if (task) {
    els.modalTitle.textContent = "Edit Task";
    els.modalSubtitle.textContent = "Ubah detail atau status task.";
    els.fieldId.value = task.id;
    els.fieldTitle.value = task.title || "";
    els.fieldDescription.value = task.description || "";
    els.fieldProject.value = String(task.project_id);
    els.fieldStatus.value = task.status || "todo";
    els.fieldCategory.value = task.category || "General";
    els.fieldPriority.value = task.priority || "medium";
    setDueDate(task.due_date || "");
    els.btnDelete.hidden = false;
  } else {
    els.modalTitle.textContent = "New Task";
    els.modalSubtitle.textContent = "Task akan muncul di board ini dan di dashboard.";
    els.fieldId.value = "";
    els.fieldStatus.value = presetStatus || "todo";
    els.fieldCategory.value = "General";
    els.fieldPriority.value = "medium";
    els.fieldProject.value = state.projectId
      ? String(state.projectId)
      : state.projects[0]
        ? String(state.projects[0].id)
        : "";
    setDueDate("");
    els.btnDelete.hidden = true;
  }

  closeDuePicker();
  els.modal.hidden = false;
  els.fieldTitle.focus();
}

function closeModal() {
  closeAssigneeDropdown();
  closeDuePicker();
  els.modal.hidden = true;
}

async function loadBoard() {
  const kanbanUrl = state.projectId
    ? `/api/dashboard/kanban?project_id=${state.projectId}`
    : "/api/dashboard/kanban";
  const requests = [api(kanbanUrl)];
  if (state.projectId) {
    requests.push(api(`/api/projects/${state.projectId}`));
  }
  const [kanban, project] = await Promise.all(requests);
  state.columns = kanban.columns || [];
  if (project) {
    const idx = state.projects.findIndex((p) => p.id === project.id);
    if (idx >= 0) state.projects[idx] = project;
    else state.projects.push(project);
  }
  renderHeader();
  renderStats();
  renderBoard();
}

async function saveTask(event) {
  event.preventDefault();
  els.formError.hidden = true;
  commitAssigneeSearch();

  const id = els.fieldId.value;
  const projectId = Number(els.fieldProject.value);
  const assigneeIds = [...new Set(state.selectedAssigneeIds.map(Number).filter((n) => n > 0))];
  const payload = {
    title: els.fieldTitle.value.trim(),
    description: els.fieldDescription.value.trim() || null,
    project_id: projectId,
    status: els.fieldStatus.value,
    category: els.fieldCategory.value.trim() || "General",
    priority: els.fieldPriority.value,
    assignee_ids: assigneeIds,
    assignee_id: assigneeIds[0] || null,
    due_date: els.fieldDue.value || null,
  };

  if (!payload.title || !payload.project_id) {
    els.formError.hidden = false;
    els.formError.textContent = "Title dan Project wajib diisi.";
    return;
  }

  try {
    await (id
      ? api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : api("/api/tasks", { method: "POST", body: JSON.stringify(payload) }));
    closeModal();
    await loadBoard();
  } catch (err) {
    els.formError.hidden = false;
    els.formError.textContent = err.message || "Gagal menyimpan task.";
  }
}

async function deleteTask() {
  const id = els.fieldId.value;
  if (!id) return;
  const ok = window.pmConfirm
    ? await window.pmConfirm({
        title: "Hapus task?",
        message: "Task akan dihapus dari board. Tindakan ini tidak bisa dibatalkan.",
        tone: "danger",
        icon: "!",
        okText: "Hapus",
        cancelText: "Batal",
      })
    : window.confirm("Hapus task ini?");
  if (!ok) return;
  try {
    await api(`/api/tasks/${id}`, { method: "DELETE" });
    closeModal();
    await loadBoard();
  } catch (err) {
    els.formError.hidden = false;
    els.formError.textContent = err.message || "Gagal menghapus task.";
  }
}

async function moveTask(taskId, nextStatus) {
  const task = findTask(taskId);
  if (!task || task.status === nextStatus) return;
  try {
    await api(`/api/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: nextStatus }),
    });
    await loadBoard();
  } catch (err) {
    if (window.pmNotice) {
      await window.pmNotice({
        title: "Gagal memindahkan",
        message: err.message || "Gagal memindahkan task.",
        tone: "danger",
        icon: "!",
      });
    } else {
      window.alert(err.message || "Gagal memindahkan task.");
    }
  }
}

function wireAssigneeEvents() {
  els.assigneeWrap.addEventListener("click", (e) => {
    if (e.target.closest("[data-remove-assignee]")) return;
    els.assigneeSearch.focus();
    openAssigneeDropdown();
  });

  els.assigneeSearch.addEventListener("focus", openAssigneeDropdown);
  els.assigneeSearch.addEventListener("input", () => {
    state.assigneeSearch = els.assigneeSearch.value;
    state.assigneeHighlight = 0;
    openAssigneeDropdown();
  });

  els.assigneeSearch.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !els.assigneeSearch.value && state.selectedAssigneeIds.length) {
      e.preventDefault();
      removeAssignee(state.selectedAssigneeIds[state.selectedAssigneeIds.length - 1]);
      openAssigneeDropdown();
      return;
    }
    if (els.assigneeDropdown.hidden) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        openAssigneeDropdown();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!state.assigneeSuggestions.length) return;
      state.assigneeHighlight = (state.assigneeHighlight + 1) % state.assigneeSuggestions.length;
      renderAssigneeOptions();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!state.assigneeSuggestions.length) return;
      state.assigneeHighlight =
        (state.assigneeHighlight - 1 + state.assigneeSuggestions.length) % state.assigneeSuggestions.length;
      renderAssigneeOptions();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const pick = state.assigneeSuggestions[state.assigneeHighlight];
      if (pick) addAssignee(pick.id);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      closeAssigneeDropdown();
    }
  });

  els.assigneeOptions.addEventListener("mousedown", (e) => {
    const option = e.target.closest("[data-assignee-id]");
    if (!option) return;
    e.preventDefault();
    addAssignee(option.dataset.assigneeId);
  });

  els.assigneeChips.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-assignee]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    removeAssignee(btn.dataset.removeAssignee);
    els.assigneeSearch.focus();
  });

  document.addEventListener("click", (e) => {
    const box = document.getElementById("assignee-multiselect");
    if (!box || els.assigneeDropdown.hidden) return;
    if (!box.contains(e.target)) closeAssigneeDropdown();
  });
}

function wireBoardEvents() {
  els.board.addEventListener("click", (e) => {
    const addBtn = e.target.closest("[data-add-status]");
    if (addBtn) {
      openModal(null, addBtn.dataset.addStatus);
      return;
    }
    const card = e.target.closest("[data-task-id][data-action='edit']");
    if (!card) return;
    const task = findTask(card.dataset.taskId);
    if (task) openModal(task);
  });

  els.board.addEventListener("dragstart", (e) => {
    const card = e.target.closest("[data-task-id]");
    if (!card) return;
    state.dragTaskId = Number(card.dataset.taskId);
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(state.dragTaskId));
  });

  els.board.addEventListener("dragend", (e) => {
    const card = e.target.closest("[data-task-id]");
    card?.classList.remove("dragging");
    state.dragTaskId = null;
    els.board.querySelectorAll(".kanban-dropzone.drag-over").forEach((el) => {
      el.classList.remove("drag-over");
    });
  });

  els.board.addEventListener("dragover", (e) => {
    const zone = e.target.closest("[data-drop-status]");
    if (!zone) return;
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  els.board.addEventListener("dragleave", (e) => {
    const zone = e.target.closest("[data-drop-status]");
    if (!zone) return;
    if (!zone.contains(e.relatedTarget)) zone.classList.remove("drag-over");
  });

  els.board.addEventListener("drop", async (e) => {
    const zone = e.target.closest("[data-drop-status]");
    if (!zone) return;
    e.preventDefault();
    zone.classList.remove("drag-over");
    const taskId = Number(e.dataTransfer.getData("text/plain") || state.dragTaskId);
    const nextStatus = zone.dataset.dropStatus;
    if (taskId && nextStatus) await moveTask(taskId, nextStatus);
  });
}

function wireDueDatePicker() {
  if (!els.duePicker) return;

  els.dueTrigger.addEventListener("click", (e) => {
    e.preventDefault();
    if (isDueOpen()) closeDuePicker();
    else openDuePicker();
  });

  els.duePrev.addEventListener("click", () => {
    dueView = new Date(dueView.getFullYear(), dueView.getMonth() - 1, 1);
    renderDueCalendar();
  });

  els.dueNext.addEventListener("click", () => {
    dueView = new Date(dueView.getFullYear(), dueView.getMonth() + 1, 1);
    renderDueCalendar();
  });

  els.dueGrid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-date]");
    if (!btn) return;
    setDueDate(btn.dataset.date);
    closeDuePicker();
  });

  els.dueClear.addEventListener("click", () => {
    setDueDate("");
    closeDuePicker();
  });

  els.dueToday.addEventListener("click", () => {
    setDueDate(toISODate(new Date()));
    closeDuePicker();
  });

  document.addEventListener("mousedown", (e) => {
    if (!isDueOpen()) return;
    if (els.duePicker.contains(e.target)) return;
    closeDuePicker();
  });
}

function wireModalEvents() {
  els.btnNew.addEventListener("click", async () => {
    if (!state.projects.length) {
      if (window.pmNotice) {
        await window.pmNotice({
          title: "Belum ada project",
          message: "Buat project dulu di menu Projects sebelum menambah task.",
          tone: "warn",
          icon: "i",
        });
      } else {
        window.alert("Belum ada project. Buat project dulu di menu Projects.");
      }
      return;
    }
    openModal(null, "todo");
  });
  els.btnClose.addEventListener("click", closeModal);
  els.btnCancel.addEventListener("click", closeModal);
  els.btnDelete.addEventListener("click", deleteTask);
  els.form.addEventListener("submit", saveTask);
  els.modal.addEventListener("click", (e) => {
    if (e.target === els.modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || els.modal.hidden) return;
    if (isDueOpen()) {
      closeDuePicker();
      return;
    }
    if (els.assigneeDropdown.hidden) closeModal();
  });
  wireDueDatePicker();
  syncDueDisplay();
}

async function boot() {
  state.projectId = getProjectIdFromUrl();
  const [projectsRes, users] = await Promise.all([
    api("/api/projects?page=1&page_size=100"),
    api("/api/team?active_only=true"),
  ]);
  state.projects = Array.isArray(projectsRes) ? projectsRes : projectsRes.items || [];
  state.users = users;

  els.filter.innerHTML =
    `<option value="">All Projects</option>` +
    state.projects
      .map(
        (p) =>
          `<option value="${p.id}" ${p.id === state.projectId ? "selected" : ""}>${escapeHtml(p.name)}</option>`
      )
      .join("");

  els.filter.addEventListener("change", () => {
    const next = els.filter.value;
    window.location.href = next ? `/tasks?project_id=${next}` : "/tasks";
  });

  let searchTimer;
  els.search.addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value || "";
      renderStats();
      renderBoard();
    }, 200);
  });

  wireModalEvents();
  wireAssigneeEvents();
  wireBoardEvents();
  await loadBoard();
}

document.addEventListener("DOMContentLoaded", () => {
  boot().catch((err) => {
    els.board.innerHTML =
      `<div class="list-empty">Failed to load tasks: ${escapeHtml(err.message)}</div>`;
  });
});
