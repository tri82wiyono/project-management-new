(() => {
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
    planned: "Rencana",
    active: "Aktif",
    done: "Selesai",
  };

  const TASK_STATUS = [
    { value: "todo", label: "To Do" },
    { value: "in_progress", label: "In Progress" },
    { value: "review", label: "Review" },
    { value: "done", label: "Done" },
  ];

  const TASK_STATUS_LABEL = Object.fromEntries(TASK_STATUS.map((s) => [s.value, s.label]));
  const PRIO_LABEL = { high: "Tinggi", medium: "Sedang", low: "Rendah" };

  const state = {
    projectId: null,
    project: null,
    sprints: [],
    selectedId: null,
    detail: null,
    backlog: [],
    projectTasks: [],
    activeTab: "board",
    boardFilter: "all",
    canManage: true,
  };

  const els = {
    subtitle: document.getElementById("sprints-subtitle"),
    needProject: document.getElementById("sprints-need-project"),
    workspace: document.getElementById("sprints-workspace"),
    hero: document.getElementById("sp-hero"),
    list: document.getElementById("sprints-list"),
    count: document.getElementById("sprints-count"),
    detailEmpty: document.getElementById("sprint-detail-empty"),
    detailBody: document.getElementById("sprint-detail-body"),
    btnNew: document.getElementById("btn-new-sprint"),
    btnBack: document.getElementById("btn-back-project"),
    btnTasks: document.getElementById("btn-open-tasks"),
    modal: document.getElementById("sprint-modal"),
    form: document.getElementById("sprint-form"),
    formError: document.getElementById("sprint-form-error"),
    fieldId: document.getElementById("sprint-id"),
    fieldProject: document.getElementById("field-sprint-project"),
    fieldName: document.getElementById("field-sprint-name"),
    fieldGoal: document.getElementById("field-sprint-goal"),
    fieldStart: document.getElementById("field-sprint-start"),
    fieldEnd: document.getElementById("field-sprint-end"),
    fieldStatus: document.getElementById("field-sprint-status"),
    taskPickerWrap: document.getElementById("sprint-task-picker-wrap"),
    taskPicker: document.getElementById("sprint-task-picker"),
    btnClose: document.getElementById("btn-close-sprint-modal"),
    btnCancel: document.getElementById("btn-cancel-sprint"),
    modalTitle: document.getElementById("sprint-modal-title"),
    modalSubtitle: document.getElementById("sprint-modal-subtitle"),
  };

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  function plusDaysISO(days) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function formatDate(value) {
    if (!value) return "—";
    try {
      return new Date(`${value}T00:00:00`).toLocaleDateString("id-ID", {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
    } catch {
      return value;
    }
  }

  function formatDateShort(value) {
    if (!value) return "—";
    try {
      return new Date(`${value}T00:00:00`).toLocaleDateString("id-ID", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return value;
    }
  }

  function projectPrefix() {
    const name = String(state.project?.name || "PRJ").replace(/[^A-Za-z0-9]/g, "");
    return (name.slice(0, 3) || "PRJ").toUpperCase();
  }

  function taskCode(task) {
    return `${projectPrefix()}-${task.id}`;
  }

  function taskStats(tasks) {
    const list = tasks || [];
    const total = list.length;
    const done = list.filter((t) => t.status === "done").length;
    const run = list.filter((t) => t.status === "in_progress" || t.status === "review").length;
    const wait = list.filter((t) => t.status === "todo").length;
    const pct = total ? Math.round((done / total) * 100) : 0;
    return { total, done, run, wait, pct };
  }

  function collectAssignees(tasks) {
    const map = new Map();
    for (const t of tasks || []) {
      const people = Array.isArray(t.assignees) && t.assignees.length
        ? t.assignees
        : t.assignee
          ? [t.assignee]
          : [];
      for (const u of people) {
        if (u?.id && !map.has(u.id)) map.set(u.id, u);
      }
    }
    return [...map.values()];
  }

  function activeSprintSummary() {
    const active =
      state.sprints.find((s) => s.id === state.selectedId) ||
      state.sprints.find((s) => s.status === "active") ||
      state.sprints[0] ||
      null;
    return active;
  }

  function syncHeaderLinks() {
    const name = state.project?.name || `Project #${state.projectId}`;
    if (els.subtitle) {
      els.subtitle.textContent = `Kelola sprint & modul prioritas untuk “${name}”.`;
    }
    if (els.btnBack) els.btnBack.href = `/projects/${state.projectId}`;
    if (els.btnTasks) els.btnTasks.href = `/tasks?project_id=${state.projectId}`;
  }

  function renderHero() {
    if (!els.hero) return;
    const projectName = state.project?.name || `Project #${state.projectId}`;
    const projectDesc =
      state.project?.description ||
      "Sprint & modul prioritas project ini";
    const active = activeSprintSummary();
    const stats = taskStats(state.detail?.tasks || []);
    const pct = state.detail ? stats.pct : Math.round(Number(active?.progress) || 0);

    els.hero.innerHTML = `
      <div class="sp-hero-project">
        <div class="sp-hero-icon" aria-hidden="true">📁</div>
        <div>
          <strong>Project: ${escapeHtml(projectName)}</strong>
          <span>${escapeHtml(projectDesc)}</span>
        </div>
      </div>
      <div class="sp-hero-active">
        ${active ? `<span class="sp-pill-aktif">Sprint Aktif</span>` : `<span class="sp-pill-aktif" style="background:#f1f5f9;color:#64748b">Belum ada</span>`}
        <strong>${escapeHtml(active?.name || "—")}</strong>
        <span>${active ? `${formatDate(active.start_date)} – ${formatDate(active.end_date)}` : "Buat sprint untuk memulai"}</span>
      </div>
      <div class="sp-hero-stats">
        <div class="sp-stat-mini"><span>Total Task</span><strong>${stats.total}</strong></div>
        <div class="sp-stat-mini is-done"><span>Selesai</span><strong>${stats.done}</strong></div>
        <div class="sp-stat-mini is-run"><span>Berjalan</span><strong>${stats.run}</strong></div>
        <div class="sp-stat-mini is-wait"><span>Tertunda</span><strong>${stats.wait}</strong></div>
      </div>
      <div class="sp-hero-progress">
        <div class="sp-hero-progress-top">
          <span>Progress Sprint</span>
          <strong>${pct}%</strong>
        </div>
        <div class="sp-bar"><span style="width:${pct}%"></span></div>
      </div>
    `;
  }

  function renderList() {
    if (!els.list) return;
    if (els.count) els.count.textContent = String(state.sprints.length);
    if (!state.sprints.length) {
      els.list.innerHTML = `<div class="sprints-empty" style="min-height:180px;padding:24px 12px">Belum ada sprint.<br/>Tekan <strong>+</strong> untuk menambah.</div>`;
      return;
    }
    els.list.innerHTML = state.sprints
      .map((s) => {
        const pct = Math.min(100, Math.max(0, Math.round(Number(s.progress) || 0)));
        const active = String(s.id) === String(state.selectedId) ? " is-active" : "";
        return `
        <button type="button" class="sp-sprint-card${active}" data-sprint-id="${s.id}">
          <div class="sp-sprint-card-top">
            <div class="sp-sprint-card-title">
              <span class="sp-sprint-bolt" aria-hidden="true">⚡</span>
              <div>
                <strong>${escapeHtml(s.name)}</strong>
                <span class="meta">${formatDateShort(s.start_date)} – ${formatDateShort(s.end_date)}</span>
                <span class="meta">${s.task_count || 0} Tasks</span>
              </div>
            </div>
            <span class="sp-badge ${escapeHtml(s.status)}">${STATUS_LABEL[s.status] || s.status}</span>
          </div>
          <div class="sp-bar${s.status === "done" ? " is-done" : ""}"><span style="width:${pct}%"></span></div>
        </button>`;
      })
      .join("");
  }

  function initials(name) {
    const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
  }

  function renderAvatars(users) {
    if (!users.length) return `<span style="font-size:0.76rem;color:var(--sp-muted)">Belum ada assignee</span>`;
    const shown = users.slice(0, 4);
    const extra = users.length - shown.length;
    return `
      <div class="sp-avatar-row">
        ${shown
          .map((u) => {
            const name = u.name || u.full_name || u.username || "?";
            if (u.avatar_url) {
              return `<img class="sp-avatar" src="${escapeHtml(u.avatar_url)}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" />`;
            }
            return `<span class="sp-avatar sp-avatar-initials" title="${escapeHtml(name)}">${escapeHtml(initials(name))}</span>`;
          })
          .join("")}
        ${extra > 0 ? `<span class="sp-avatar-more">+${extra}</span>` : ""}
      </div>`;
  }

  function renderAssigneeChip(user) {
    if (!user) return "";
    const name = user.name || user.full_name || user.username || "?";
    if (user.avatar_url) {
      return `<img class="sp-avatar" src="${escapeHtml(user.avatar_url)}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" />`;
    }
    return `<span class="sp-avatar sp-avatar-initials" title="${escapeHtml(name)}">${escapeHtml(initials(name))}</span>`;
  }

  function renderTaskCard(task) {
    const prio = task.priority || "medium";
    const people = Array.isArray(task.assignees) && task.assignees.length
      ? task.assignees
      : task.assignee
        ? [task.assignee]
        : [];
    const avatar = people[0];
    return `
      <article class="sp-task" data-task-id="${task.id}">
        <div class="sp-task-top">
          <span class="sp-task-code">${escapeHtml(taskCode(task))}</span>
          <a class="sp-task-link" href="/tasks?project_id=${state.projectId}">↗ Dari Tasks Project</a>
        </div>
        <h4>${escapeHtml(task.title)}</h4>
        <div class="sp-task-foot">
          <span class="sp-prio ${escapeHtml(prio)}">${PRIO_LABEL[prio] || prio}</span>
          <span class="sp-due">📅 ${task.due_date ? formatDateShort(task.due_date) : "Tanpa due"}</span>
          ${renderAssigneeChip(avatar)}
        </div>
        ${
          state.canManage
            ? `<select class="sp-task-status" data-task-status="${task.id}" title="Ubah status">
                ${TASK_STATUS.map(
                  (s) =>
                    `<option value="${s.value}"${s.value === task.status ? " selected" : ""}>${s.label}</option>`
                ).join("")}
              </select>`
            : ""
        }
      </article>`;
  }

  function renderBoard(tasks) {
    const filter = state.boardFilter || "all";
    return `
      <div class="sp-alert"><strong>Informasi:</strong> Task tetap ada di Tasks project dan juga muncul di Sprint. Ubah status di sini = berubah juga di Tasks.</div>
      <div class="sp-board">
        ${TASK_STATUS.map((col) => {
          const items = (tasks || []).filter((t) => t.status === col.value);
          const hidden = filter !== "all" && filter !== col.value ? " hidden" : "";
          return `
            <div class="sp-col ${col.value}"${hidden}>
              <div class="sp-col-head">
                <span class="sp-col-head-left"><span class="sp-col-dot"></span>${col.label}</span>
                <span class="n">${items.length}</span>
              </div>
              <div class="sp-col-body">
                ${items.length ? items.map(renderTaskCard).join("") : `<div class="sp-col-empty">Kosong</div>`}
              </div>
            </div>`;
        }).join("")}
      </div>
      <div class="sp-backlog-panel">
        <h4>Belum di sprint (${state.backlog.length})</h4>
        ${
          state.backlog.length
            ? state.backlog
                .map(
                  (t) => `
              <div class="sp-backlog-item">
                <span>${escapeHtml(t.title)}</span>
                ${
                  state.canManage
                    ? `<button type="button" data-add-task="${t.id}">+ Masukkan</button>`
                    : ""
                }
              </div>`
                )
                .join("")
            : `<div class="sp-col-empty">Semua task sudah masuk sprint, atau belum ada task.</div>`
        }
      </div>`;
  }

  function renderListTab(tasks) {
    if (!(tasks || []).length) {
      return `<div class="sprints-empty" style="min-height:160px">Belum ada task di sprint ini.</div>`;
    }
    return `
      <table class="sp-list-table">
        <thead>
          <tr>
            <th>Kode</th>
            <th>Task</th>
            <th>Status</th>
            <th>Prioritas</th>
            <th>Due</th>
          </tr>
        </thead>
        <tbody>
          ${tasks
            .map(
              (t) => `
            <tr>
              <td>${escapeHtml(taskCode(t))}</td>
              <td>${escapeHtml(t.title)}</td>
              <td>
                <select data-task-status="${t.id}" ${state.canManage ? "" : "disabled"}>
                  ${TASK_STATUS.map(
                    (s) =>
                      `<option value="${s.value}"${s.value === t.status ? " selected" : ""}>${s.label}</option>`
                  ).join("")}
                </select>
              </td>
              <td>${escapeHtml(PRIO_LABEL[t.priority] || t.priority || "—")}</td>
              <td>${t.due_date ? formatDateShort(t.due_date) : "—"}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  function renderReport(s, stats) {
    const overdue = s.sla_overdue;
    return `
      <div class="sp-report">
        <div class="sp-report-card">
          <h4>Ringkasan progress</h4>
          <p>${stats.done} dari ${stats.total} task selesai (${stats.pct}%). ${stats.run} sedang berjalan, ${stats.wait} masih tertunda.</p>
        </div>
        <div class="sp-report-card">
          <h4>SLA</h4>
          <p>${formatDate(s.start_date)} → ${formatDate(s.end_date)}. ${
            s.status === "done"
              ? "Sprint sudah diselesaikan."
              : overdue
                ? `Terlambat ${Math.abs(Number(s.sla_days_left) || 0)} hari dari target.`
                : `Sisa ${s.sla_days_left ?? "—"} hari menuju akhir sprint.`
          }</p>
        </div>
        <div class="sp-report-card">
          <h4>Tujuan</h4>
          <p>${escapeHtml(s.goal || "Belum diisi.")}</p>
        </div>
      </div>`;
  }

  function renderDetail() {
    if (!state.detail) {
      if (els.detailEmpty) els.detailEmpty.hidden = false;
      if (els.detailBody) {
        els.detailBody.hidden = true;
        els.detailBody.innerHTML = "";
      }
      return;
    }

    const s = state.detail;
    const tasks = s.tasks || [];
    const stats = taskStats(tasks);
    const team = collectAssignees(tasks);
    if (els.detailEmpty) els.detailEmpty.hidden = true;
    if (!els.detailBody) return;
    els.detailBody.hidden = false;

    const tab = state.activeTab || "board";
    els.detailBody.innerHTML = `
      <div class="sp-detail-head">
        <div class="sp-detail-title">
          <div class="sp-detail-title-icon" aria-hidden="true">⚡</div>
          <div>
            <h2>${escapeHtml(s.name)}</h2>
            <p>${formatDate(s.start_date)} – ${formatDate(s.end_date)} <span class="sp-badge ${escapeHtml(s.status)}">${STATUS_LABEL[s.status] || s.status}</span></p>
          </div>
        </div>
        <div class="sp-detail-actions">
          <button type="button" class="sp-btn sp-btn-outline" id="btn-edit-sprint">Edit Sprint</button>
          ${
            s.status !== "done"
              ? `<button type="button" class="sp-btn sp-btn-primary" id="btn-complete-sprint">✓ Selesaikan Sprint</button>`
              : ""
          }
          <button type="button" class="sp-btn sp-btn-ghost" id="btn-delete-sprint">Hapus</button>
        </div>
      </div>

      <div class="sp-overview">
        <div class="sp-goal-block">
          <h4>Tujuan Sprint</h4>
          <p>${escapeHtml(s.goal || "Belum ada tujuan. Edit sprint untuk menambahkan goal.")}</p>
        </div>
        <div class="sp-progress-block">
          <h4>Progress Sprint</h4>
          <div class="sp-progress-big">
            <strong>${stats.pct}%</strong>
            <span>${stats.done} dari ${stats.total} task selesai</span>
          </div>
          <div class="sp-bar"><span style="width:${stats.pct}%"></span></div>
        </div>
      </div>

      <div class="sp-meta-row">
        <div class="sp-team-block">
          <h4>Tim Sprint</h4>
          ${renderAvatars(team)}
        </div>
        <div class="sp-stats-row">
          <div class="sp-stat-card"><div class="sp-stat-ico total">☰</div><div><span>Total Task</span><strong>${stats.total}</strong></div></div>
          <div class="sp-stat-card"><div class="sp-stat-ico done">✓</div><div><span>Selesai</span><strong>${stats.done}</strong></div></div>
          <div class="sp-stat-card"><div class="sp-stat-ico run">↻</div><div><span>Berjalan</span><strong>${stats.run}</strong></div></div>
          <div class="sp-stat-card"><div class="sp-stat-ico wait">!</div><div><span>Tertunda</span><strong>${stats.wait}</strong></div></div>
        </div>
      </div>

      <div class="sp-tabs-bar">
        <div class="sp-tabs" role="tablist">
          <button type="button" class="sp-tab${tab === "board" ? " is-active" : ""}" data-tab="board">Board</button>
          <button type="button" class="sp-tab${tab === "list" ? " is-active" : ""}" data-tab="list">Daftar Task</button>
          <button type="button" class="sp-tab${tab === "report" ? " is-active" : ""}" data-tab="report">Laporan</button>
        </div>
        ${
          tab === "board"
            ? `<select class="sp-board-filter" id="sp-board-filter" aria-label="Filter status">
                <option value="all"${state.boardFilter === "all" ? " selected" : ""}>Semua status</option>
                ${TASK_STATUS.map(
                  (s) =>
                    `<option value="${s.value}"${state.boardFilter === s.value ? " selected" : ""}>${s.label}</option>`
                ).join("")}
              </select>`
            : ""
        }
      </div>

      <div class="sp-tab-panel" data-panel="board" ${tab === "board" ? "" : "hidden"}>${renderBoard(tasks)}</div>
      <div class="sp-tab-panel" data-panel="list" ${tab === "list" ? "" : "hidden"}>${renderListTab(tasks)}</div>
      <div class="sp-tab-panel" data-panel="report" ${tab === "report" ? "" : "hidden"}>${renderReport(s, stats)}</div>
    `;
  }

  function renderAll() {
    renderHero();
    renderList();
    renderDetail();
  }

  function renderTaskPicker(selectedIds = []) {
    if (!els.taskPicker) return;
    const selected = new Set(selectedIds.map(String));
    const tasks = state.projectTasks || [];
    if (!tasks.length) {
      els.taskPicker.innerHTML = `<div class="sprints-empty" style="padding:16px;min-height:auto">Belum ada task di project ini.</div>`;
      return;
    }
    els.taskPicker.innerHTML = tasks
      .map((t) => {
        const checked = selected.has(String(t.id)) ? " checked" : "";
        const already = t.sprint_id && !selected.has(String(t.id));
        return `
          <label class="sprint-task-option${already ? " is-busy" : ""}">
            <input type="checkbox" name="sprint_task_ids" value="${t.id}"${checked}${already ? " disabled" : ""} />
            <span>
              <strong>${escapeHtml(t.title)}</strong>
              <small>${escapeHtml(TASK_STATUS_LABEL[t.status] || t.status)}${already ? " · sudah di sprint lain" : ""}</small>
            </span>
          </label>`;
      })
      .join("");
  }

  function selectedTaskIdsFromPicker() {
    return Array.from(
      els.taskPicker?.querySelectorAll('input[name="sprint_task_ids"]:checked') || []
    ).map((el) => Number(el.value));
  }

  async function loadProject() {
    state.project = await api(`/api/projects/${state.projectId}`);
    syncHeaderLinks();
  }

  async function loadProjectTasks() {
    state.projectTasks = await api(`/api/tasks?project_id=${state.projectId}`);
  }

  async function loadSprints() {
    state.sprints = await api(`/api/sprints?project_id=${state.projectId}`);
    if (state.selectedId && !state.sprints.some((s) => s.id === state.selectedId)) {
      state.selectedId = state.sprints[0]?.id || null;
      state.detail = null;
    } else if (!state.selectedId && state.sprints.length) {
      const preferred =
        state.sprints.find((s) => s.status === "active") || state.sprints[0];
      state.selectedId = preferred.id;
    }
    if (state.selectedId) await selectSprint(state.selectedId, false);
    else {
      state.detail = null;
      renderAll();
    }
  }

  async function selectSprint(id, rerenderList = true) {
    state.selectedId = Number(id);
    if (rerenderList) renderList();
    state.detail = await api(`/api/sprints/${id}`);
    state.backlog = await api(
      `/api/tasks?project_id=${state.projectId}&unassigned_sprint=true`
    );
    renderAll();
  }

  async function openForm(sprint = null) {
    els.formError.hidden = true;
    els.fieldProject.value = String(state.projectId);
    await loadProjectTasks();

    if (sprint) {
      els.modalTitle.textContent = "Edit sprint";
      els.modalSubtitle.textContent = "Ubah periode SLA dan status sprint.";
      els.fieldId.value = String(sprint.id);
      els.fieldName.value = sprint.name || "";
      els.fieldGoal.value = sprint.goal || "";
      els.fieldStart.value = sprint.start_date || "";
      els.fieldEnd.value = sprint.end_date || "";
      els.fieldStatus.value = sprint.status || "active";
      if (els.taskPickerWrap) els.taskPickerWrap.hidden = true;
    } else {
      els.modalTitle.textContent = "Sprint baru";
      els.modalSubtitle.textContent = "Isi periode SLA dan centang modul prioritas.";
      els.fieldId.value = "";
      els.fieldName.value = "";
      els.fieldGoal.value = "";
      els.fieldStart.value = todayISO();
      els.fieldEnd.value = plusDaysISO(7);
      els.fieldStatus.value = "active";
      if (els.taskPickerWrap) els.taskPickerWrap.hidden = false;
      renderTaskPicker([]);
    }

    if (els.modal && els.modal.parentElement !== document.body) {
      document.body.appendChild(els.modal);
    }
    els.modal.hidden = false;
    document.body.classList.add("modal-open");
    els.fieldName?.focus();
  }

  function closeForm() {
    if (els.modal) els.modal.hidden = true;
    document.body.classList.remove("modal-open");
  }

  async function saveSprint(event) {
    event.preventDefault();
    els.formError.hidden = true;
    const id = els.fieldId.value;
    const payload = {
      project_id: Number(state.projectId),
      name: els.fieldName.value.trim(),
      goal: els.fieldGoal.value.trim() || null,
      start_date: els.fieldStart.value,
      end_date: els.fieldEnd.value,
      status: els.fieldStatus.value,
    };
    if (!payload.name || !payload.project_id || !payload.start_date || !payload.end_date) {
      els.formError.hidden = false;
      els.formError.textContent = "Lengkapi field wajib.";
      return;
    }
    if (payload.end_date < payload.start_date) {
      els.formError.hidden = false;
      els.formError.textContent = "Tanggal selesai harus setelah tanggal mulai.";
      return;
    }
    if (!id) payload.task_ids = selectedTaskIdsFromPicker();

    try {
      let saved;
      if (id) {
        const { project_id, ...patch } = payload;
        saved = await api(`/api/sprints/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
      } else {
        saved = await api("/api/sprints", { method: "POST", body: JSON.stringify(payload) });
      }
      closeForm();
      state.selectedId = saved.id;
      await loadSprints();
    } catch (err) {
      els.formError.hidden = false;
      els.formError.textContent = err.message || "Gagal menyimpan sprint.";
    }
  }

  async function onDetailClick(event) {
    const tabBtn = event.target.closest("[data-tab]");
    if (tabBtn) {
      state.activeTab = tabBtn.dataset.tab;
      renderDetail();
      return;
    }
    if (event.target.closest("#btn-edit-sprint") && state.detail) {
      await openForm(state.detail);
      return;
    }
    if (event.target.closest("#btn-complete-sprint") && state.detail) {
      const ok = window.confirm(`Tandai sprint “${state.detail.name}” sebagai selesai?`);
      if (!ok) return;
      await api(`/api/sprints/${state.detail.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "done" }),
      });
      await loadSprints();
      return;
    }
    if (event.target.closest("#btn-delete-sprint") && state.detail) {
      const ok = window.confirm(`Hapus sprint “${state.detail.name}”? Modul tetap ada di Tasks.`);
      if (!ok) return;
      await api(`/api/sprints/${state.detail.id}`, { method: "DELETE" });
      state.selectedId = null;
      state.detail = null;
      await loadSprints();
      return;
    }
    const addBtn = event.target.closest("[data-add-task]");
    if (addBtn && state.detail) {
      await api(`/api/sprints/${state.detail.id}/tasks`, {
        method: "POST",
        body: JSON.stringify({ task_ids: [Number(addBtn.dataset.addTask)] }),
      });
      await selectSprint(state.detail.id);
    }
  }

  async function onDetailChange(event) {
    if (event.target.id === "sp-board-filter") {
      state.boardFilter = event.target.value || "all";
      renderDetail();
      return;
    }
    const select = event.target.closest("[data-task-status]");
    if (!select || !state.detail) return;
    try {
      await api(`/api/tasks/${Number(select.dataset.taskStatus)}`, {
        method: "PATCH",
        body: JSON.stringify({ status: select.value }),
      });
      await selectSprint(state.detail.id);
    } catch (err) {
      alert(err.message || "Gagal mengubah status task");
      await selectSprint(state.detail.id);
    }
  }

  async function boot() {
    const params = new URLSearchParams(window.location.search);
    const projectFromUrl = Number(params.get("project_id") || 0);
    if (!projectFromUrl) {
      if (els.needProject) els.needProject.hidden = false;
      if (els.workspace) els.workspace.hidden = true;
      return;
    }

    state.projectId = projectFromUrl;
    if (els.needProject) els.needProject.hidden = true;
    if (els.workspace) els.workspace.hidden = false;

    await loadProject();
    await loadSprints();

    els.btnNew?.addEventListener("click", () => {
      openForm().catch((err) => alert(err.message || "Gagal membuka form"));
    });
    els.btnClose?.addEventListener("click", closeForm);
    els.btnCancel?.addEventListener("click", closeForm);
    els.form?.addEventListener("submit", saveSprint);
    els.list?.addEventListener("click", (e) => {
      const card = e.target.closest("[data-sprint-id]");
      if (card) selectSprint(card.dataset.sprintId);
    });
    els.detailBody?.addEventListener("click", (e) => {
      onDetailClick(e).catch((err) => alert(err.message || "Gagal"));
    });
    els.detailBody?.addEventListener("change", (e) => {
      onDetailChange(e).catch((err) => alert(err.message || "Gagal"));
    });
    els.modal?.addEventListener("click", (e) => {
      if (e.target === els.modal) closeForm();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && els.modal && !els.modal.hidden) closeForm();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    boot().catch((err) => {
      if (els.list) {
        els.list.innerHTML = `<div class="sprints-empty">${escapeHtml(err.message || "Gagal memuat sprint")}</div>`;
      }
    });
  });
})();
