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

  const state = {
    projects: [],
    sprints: [],
    selectedId: null,
    detail: null,
    backlog: [],
    canManage: true,
  };

  const els = {
    projectFilter: document.getElementById("sprint-project-filter"),
    statusFilter: document.getElementById("sprint-status-filter"),
    list: document.getElementById("sprints-list"),
    count: document.getElementById("sprints-count"),
    detailEmpty: document.getElementById("sprint-detail-empty"),
    detailBody: document.getElementById("sprint-detail-body"),
    btnNew: document.getElementById("btn-new-sprint"),
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
    btnClose: document.getElementById("btn-close-sprint-modal"),
    btnCancel: document.getElementById("btn-cancel-sprint"),
    modalTitle: document.getElementById("sprint-modal-title"),
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

  function fillProjectSelects() {
    const options = state.projects
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)
      .join("");
    if (els.projectFilter) {
      const current = els.projectFilter.value;
      els.projectFilter.innerHTML = `<option value="">Semua Project</option>${options}`;
      els.projectFilter.value = current;
    }
    if (els.fieldProject) {
      els.fieldProject.innerHTML = options || `<option value="">Tidak ada project</option>`;
    }
  }

  function renderList() {
    if (!els.list) return;
    if (!state.sprints.length) {
      els.list.innerHTML = `<div class="sprints-empty">Belum ada sprint. Buat sprint untuk mulai fokus modul prioritas.</div>`;
      if (els.count) els.count.textContent = "0";
      return;
    }
    if (els.count) els.count.textContent = String(state.sprints.length);
    els.list.innerHTML = state.sprints
      .map((s) => {
        const pct = Math.min(100, Math.max(0, Number(s.progress) || 0));
        const active = String(s.id) === String(state.selectedId) ? " is-active" : "";
        return `
        <button type="button" class="sprint-card${active}" data-sprint-id="${s.id}">
          <div class="sprint-card-top">
            <div>
              <strong>${escapeHtml(s.name)}</strong>
              <span class="muted">${escapeHtml(s.project_name || "Project")} · ${s.done_count}/${s.task_count} modul</span>
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
          <span>${escapeHtml(s.project_name || "")}</span>
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
            <span>Di Sprint</span>
            <span>${(s.tasks || []).length}</span>
          </div>
          <div class="sprint-column-body">
            ${(s.tasks || []).length
              ? (s.tasks || []).map((t) => renderTaskCard(t, { inSprint: true })).join("")
              : `<div class="sprints-empty" style="padding:24px 12px">Belum ada modul. Geser dari backlog.</div>`}
          </div>
        </div>
        <div class="sprint-column">
          <div class="sprint-column-head">
            <span>Backlog project (belum di sprint)</span>
            <span>${state.backlog.length}</span>
          </div>
          <div class="sprint-column-body">
            ${state.backlog.length
              ? state.backlog.map((t) => renderTaskCard(t, { inSprint: false })).join("")
              : `<div class="sprints-empty" style="padding:24px 12px">Semua modul sudah masuk sprint atau belum ada task.</div>`}
          </div>
        </div>
      </div>
    `;
  }

  async function loadProjects() {
    const data = await api("/api/projects?page_size=200");
    state.projects = Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : [];
    fillProjectSelects();
  }

  async function loadSprints() {
    const params = new URLSearchParams();
    if (els.projectFilter?.value) params.set("project_id", els.projectFilter.value);
    if (els.statusFilter?.value) params.set("status", els.statusFilter.value);
    const qs = params.toString();
    state.sprints = await api(`/api/sprints${qs ? `?${qs}` : ""}`);
    if (state.selectedId && !state.sprints.some((s) => s.id === state.selectedId)) {
      state.selectedId = state.sprints[0]?.id || null;
      state.detail = null;
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
      `/api/tasks?project_id=${state.detail.project_id}&unassigned_sprint=true`
    );
    renderDetail();
  }

  function openModal(sprint = null) {
    els.formError.hidden = true;
    fillProjectSelects();
    if (sprint) {
      els.modalTitle.textContent = "Edit Sprint";
      els.fieldId.value = String(sprint.id);
      els.fieldProject.value = String(sprint.project_id);
      els.fieldProject.disabled = true;
      els.fieldName.value = sprint.name || "";
      els.fieldGoal.value = sprint.goal || "";
      els.fieldStart.value = sprint.start_date || "";
      els.fieldEnd.value = sprint.end_date || "";
      els.fieldStatus.value = sprint.status || "active";
    } else {
      els.modalTitle.textContent = "New Sprint";
      els.fieldId.value = "";
      els.fieldProject.disabled = false;
      els.fieldProject.value =
        els.projectFilter?.value || (state.projects[0] ? String(state.projects[0].id) : "");
      els.fieldName.value = "";
      els.fieldGoal.value = "";
      els.fieldStart.value = todayISO();
      els.fieldEnd.value = plusDaysISO(14);
      els.fieldStatus.value = "active";
    }
    if (els.modal.parentElement !== document.body) document.body.appendChild(els.modal);
    els.modal.hidden = false;
    document.body.classList.add("modal-open");
  }

  function closeModal() {
    els.modal.hidden = true;
    document.body.classList.remove("modal-open");
    els.fieldProject.disabled = false;
  }

  async function saveSprint(event) {
    event.preventDefault();
    els.formError.hidden = true;
    const id = els.fieldId.value;
    const payload = {
      project_id: Number(els.fieldProject.value),
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
    try {
      let saved;
      if (id) {
        const { project_id, ...patch } = payload;
        saved = await api(`/api/sprints/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
      } else {
        saved = await api("/api/sprints", { method: "POST", body: JSON.stringify(payload) });
      }
      closeModal();
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
      openModal(state.detail);
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
    if (!els.list) return;
    const params = new URLSearchParams(window.location.search);
    const projectFromUrl = params.get("project_id");
    await loadProjects();
    if (projectFromUrl && els.projectFilter) els.projectFilter.value = projectFromUrl;
    await loadSprints();

    els.btnNew?.addEventListener("click", () => openModal());
    els.btnClose?.addEventListener("click", closeModal);
    els.btnCancel?.addEventListener("click", closeModal);
    els.form?.addEventListener("submit", saveSprint);
    els.projectFilter?.addEventListener("change", () => loadSprints());
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
    els.modal?.addEventListener("click", (e) => {
      if (e.target === els.modal) closeModal();
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
