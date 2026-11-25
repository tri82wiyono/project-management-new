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
    planned: "Planned",
    active: "Active",
    done: "Done",
  };

  const TASK_STATUS = [
    { value: "todo", label: "To Do" },
    { value: "in_progress", label: "In Progress" },
    { value: "review", label: "Review" },
    { value: "done", label: "Done" },
  ];

  const TASK_STATUS_LABEL = Object.fromEntries(TASK_STATUS.map((s) => [s.value, s.label]));

  const state = {
    projectId: null,
    project: null,
    sprints: [],
    selectedId: null,
    detail: null,
    backlog: [],
    projectTasks: [],
    canManage: true,
  };

  const els = {
    subtitle: document.getElementById("sprints-subtitle"),
    needProject: document.getElementById("sprints-need-project"),
    workspace: document.getElementById("sprints-workspace"),
    projectName: document.getElementById("sprints-project-name"),
    statusFilter: document.getElementById("sprint-status-filter"),
    list: document.getElementById("sprints-list"),
    count: document.getElementById("sprints-count"),
    detailEmpty: document.getElementById("sprint-detail-empty"),
    detailBody: document.getElementById("sprint-detail-body"),
    btnNew: document.getElementById("btn-new-sprint"),
    btnBack: document.getElementById("btn-back-project"),
    btnTasks: document.getElementById("btn-open-tasks"),
    formPanel: document.getElementById("sprint-form-panel"),
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

  function slaText(sprint) {
    if (sprint.status === "done") return "Sprint selesai";
    if (sprint.sla_overdue) {
      const late = Math.abs(Number(sprint.sla_days_left) || 0);
      return `SLA terlambat ${late} hari`;
    }
    const left = sprint.sla_days_left;
    if (left == null) return "SLA —";
    if (left === 0) return "SLA berakhir hari ini";
    return `Sisa SLA ${left} hari`;
  }

  function syncHeader() {
    const name = state.project?.name || `Project #${state.projectId}`;
    if (els.subtitle) {
      els.subtitle.textContent = `Modul prioritas untuk “${name}” — pilih task yang dikerjakan dalam periode SLA.`;
    }
    if (els.projectName) els.projectName.textContent = name;
    if (els.btnBack) els.btnBack.href = `/projects/${state.projectId}`;
    if (els.btnTasks) els.btnTasks.href = `/tasks?project_id=${state.projectId}`;
  }

  function renderList() {
    if (!els.list) return;
    if (!state.sprints.length) {
      els.list.innerHTML = `<div class="sprints-empty" style="min-height:160px;padding:28px 16px">Belum ada sprint.<br/>Tekan tombol <strong>+</strong> untuk menambah.</div>`;
      if (els.count) els.count.textContent = "0 sprint";
      return;
    }
    if (els.count) els.count.textContent = `${state.sprints.length} sprint`;
    els.list.innerHTML = state.sprints
      .map((s) => {
        const pct = Math.min(100, Math.max(0, Number(s.progress) || 0));
        const active = String(s.id) === String(state.selectedId) ? " is-active" : "";
        return `
        <button type="button" class="sprint-card${active}" data-sprint-id="${s.id}">
          <div class="sprint-card-top">
            <div>
              <strong>${escapeHtml(s.name)}</strong>
              <span class="muted">${s.done_count}/${s.task_count} modul · ${formatDate(s.start_date)} → ${formatDate(s.end_date)}</span>
            </div>
            <span class="sprint-badge ${escapeHtml(s.status)}">${STATUS_LABEL[s.status] || s.status}</span>
          </div>
          <div class="sprint-sla${s.sla_overdue ? " is-overdue" : ""}">${escapeHtml(slaText(s))}</div>
          <div class="sprint-progress"><span style="width:${pct}%"></span></div>
        </button>`;
      })
      .join("");
  }

  function taskStatusOptions(current) {
    return TASK_STATUS.map(
      (s) =>
        `<option value="${s.value}"${s.value === current ? " selected" : ""}>${s.label}</option>`
    ).join("");
  }

  function renderTaskCard(task, { inSprint }) {
    return `
      <article class="sprint-task" data-task-id="${task.id}">
        <strong>${escapeHtml(task.title)}</strong>
        <div class="sprint-task-foot">
          <select data-task-status="${task.id}" ${state.canManage ? "" : "disabled"}>
            ${taskStatusOptions(task.status)}
          </select>
          ${
            state.canManage
              ? inSprint
                ? `<button type="button" class="btn-mini" data-remove-task="${task.id}">Keluarkan</button>`
                : `<button type="button" class="btn-mini" data-add-task="${task.id}">Masukkan ke sprint</button>`
              : ""
          }
        </div>
      </article>`;
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
    if (els.detailEmpty) els.detailEmpty.hidden = true;
    if (!els.detailBody) return;
    els.detailBody.hidden = false;
    const pct = Math.min(100, Math.max(0, Number(s.progress) || 0));
    els.detailBody.innerHTML = `
      <div class="sprint-detail-head">
        <h2>${escapeHtml(s.name)}</h2>
        <div class="sprint-detail-meta">
          <span class="sprint-badge ${escapeHtml(s.status)}">${STATUS_LABEL[s.status] || s.status}</span>
          <span>${formatDate(s.start_date)} → ${formatDate(s.end_date)}</span>
          <span class="${s.sla_overdue ? "sprint-sla is-overdue" : ""}">${escapeHtml(slaText(s))}</span>
          <span>${s.done_count}/${s.task_count} selesai · ${pct}%</span>
        </div>
        ${s.goal ? `<p class="muted" style="margin:8px 0 0;font-size:0.8rem">${escapeHtml(s.goal)}</p>` : ""}
      </div>
      <div class="sprint-detail-actions">
        <button type="button" class="btn btn-ghost btn-sm" id="btn-edit-sprint">Edit sprint</button>
        <button type="button" class="btn btn-ghost btn-sm" id="btn-delete-sprint">Hapus</button>
        <a class="btn btn-ghost btn-sm" href="/tasks?project_id=${s.project_id}">Buka Tasks</a>
      </div>
      <div class="sprint-progress"><span style="width:${pct}%"></span></div>
      <div class="sprint-board">
        <div class="sprint-column">
          <div class="sprint-column-head">
            <span>Di Sprint (prioritas)</span>
            <span>${(s.tasks || []).length}</span>
          </div>
          <div class="sprint-column-body">
            ${(s.tasks || []).length
              ? (s.tasks || []).map((t) => renderTaskCard(t, { inSprint: true })).join("")
              : `<div class="sprints-empty" style="padding:24px 12px">Belum ada modul. Masukkan dari backlog kanan.</div>`}
          </div>
        </div>
        <div class="sprint-column">
          <div class="sprint-column-head">
            <span>Belum di sprint</span>
            <span>${state.backlog.length}</span>
          </div>
          <div class="sprint-column-body">
            ${state.backlog.length
              ? state.backlog.map((t) => renderTaskCard(t, { inSprint: false })).join("")
              : `<div class="sprints-empty" style="padding:24px 12px">Semua modul sudah masuk sprint, atau belum ada task di project ini.</div>`}
          </div>
        </div>
      </div>
    `;
  }

  function renderTaskPicker(selectedIds = []) {
    if (!els.taskPicker) return;
    const selected = new Set(selectedIds.map(String));
    const tasks = state.projectTasks || [];
    if (!tasks.length) {
      els.taskPicker.innerHTML = `<div class="sprints-empty" style="padding:16px">Belum ada task di project ini. Buat task dulu di menu Tasks.</div>`;
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
              <small>${escapeHtml(TASK_STATUS_LABEL[t.status] || t.status)}${
                already ? ` · sudah di sprint lain` : ""
              }</small>
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
    syncHeader();
  }

  async function loadProjectTasks() {
    state.projectTasks = await api(`/api/tasks?project_id=${state.projectId}`);
  }

  async function loadSprints() {
    const params = new URLSearchParams({ project_id: String(state.projectId) });
    if (els.statusFilter?.value) params.set("status", els.statusFilter.value);
    state.sprints = await api(`/api/sprints?${params.toString()}`);
    if (state.selectedId && !state.sprints.some((s) => s.id === state.selectedId)) {
      state.selectedId = state.sprints[0]?.id || null;
      state.detail = null;
    } else if (!state.selectedId && state.sprints.length) {
      state.selectedId = state.sprints[0].id;
    }
    renderList();
    if (state.selectedId) await selectSprint(state.selectedId);
    else renderDetail();
  }

  async function selectSprint(id) {
    state.selectedId = Number(id);
    renderList();
    state.detail = await api(`/api/sprints/${id}`);
    state.backlog = await api(
      `/api/tasks?project_id=${state.projectId}&unassigned_sprint=true`
    );
    renderDetail();
  }

  async function openForm(sprint = null) {
    els.formError.hidden = true;
    els.fieldProject.value = String(state.projectId);
    await loadProjectTasks();

    if (sprint) {
      els.modalTitle.textContent = "Edit sprint";
      els.modalSubtitle.textContent = "Ubah periode SLA. Modul bisa diatur di board di atas.";
      els.fieldId.value = String(sprint.id);
      els.fieldName.value = sprint.name || "";
      els.fieldGoal.value = sprint.goal || "";
      els.fieldStart.value = sprint.start_date || "";
      els.fieldEnd.value = sprint.end_date || "";
      els.fieldStatus.value = sprint.status || "active";
      if (els.taskPickerWrap) els.taskPickerWrap.hidden = true;
    } else {
      els.modalTitle.textContent = "Sprint baru";
      els.modalSubtitle.textContent = "Isi periode SLA dan centang modul prioritas dari Tasks project ini.";
      els.fieldId.value = "";
      els.fieldName.value = "";
      els.fieldGoal.value = "";
      els.fieldStart.value = todayISO();
      els.fieldEnd.value = plusDaysISO(7);
      els.fieldStatus.value = "active";
      if (els.taskPickerWrap) els.taskPickerWrap.hidden = false;
      renderTaskPicker([]);
    }

    if (els.formPanel) els.formPanel.hidden = false;
    els.btnNew?.classList.add("is-open");
    els.formPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    els.fieldName?.focus();
  }

  function closeForm() {
    if (els.formPanel) els.formPanel.hidden = true;
    els.btnNew?.classList.remove("is-open");
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
    if (!id) {
      payload.task_ids = selectedTaskIdsFromPicker();
    }
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
    const editBtn = event.target.closest("#btn-edit-sprint");
    if (editBtn && state.detail) {
      await openForm(state.detail);
      return;
    }
    const delBtn = event.target.closest("#btn-delete-sprint");
    if (delBtn && state.detail) {
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
      const taskId = Number(addBtn.dataset.addTask);
      await api(`/api/sprints/${state.detail.id}/tasks`, {
        method: "POST",
        body: JSON.stringify({ task_ids: [taskId] }),
      });
      await selectSprint(state.detail.id);
      await loadSprints();
      return;
    }
    const removeBtn = event.target.closest("[data-remove-task]");
    if (removeBtn && state.detail) {
      const taskId = Number(removeBtn.dataset.removeTask);
      await api(`/api/sprints/${state.detail.id}/tasks/${taskId}`, { method: "DELETE" });
      await selectSprint(state.detail.id);
      await loadSprints();
    }
  }

  async function onDetailChange(event) {
    const select = event.target.closest("[data-task-status]");
    if (!select || !state.detail) return;
    const taskId = Number(select.dataset.taskStatus);
    const status = select.value;
    try {
      await api(`/api/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await selectSprint(state.detail.id);
      await loadSprints();
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
      if (els.formPanel && !els.formPanel.hidden && !els.fieldId.value) {
        closeForm();
        return;
      }
      openForm().catch((err) => alert(err.message || "Gagal membuka form"));
    });
    els.btnClose?.addEventListener("click", closeForm);
    els.btnCancel?.addEventListener("click", closeForm);
    els.form?.addEventListener("submit", saveSprint);
    els.statusFilter?.addEventListener("change", () => loadSprints());
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
  }

  document.addEventListener("DOMContentLoaded", () => {
    boot().catch((err) => {
      if (els.list) {
        els.list.innerHTML = `<div class="sprints-empty">${escapeHtml(err.message || "Gagal memuat sprint")}</div>`;
      } else if (els.needProject) {
        els.needProject.hidden = false;
        els.needProject.querySelector("p").textContent = err.message || "Gagal memuat sprint.";
      }
    });
  });
})();
