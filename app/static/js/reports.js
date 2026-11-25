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

  const els = {
    form: document.getElementById("reports-form"),
    divisionWrap: document.getElementById("filter-division-wrap"),
    workspaceWrap: document.getElementById("filter-workspace-wrap"),
    division: document.getElementById("filter-division"),
    workspace: document.getElementById("filter-workspace"),
    status: document.getElementById("filter-status"),
    note: document.getElementById("reports-scope-note"),
    error: document.getElementById("reports-error"),
    btn: document.getElementById("btn-download-report"),
  };

  const state = {
    options: null,
  };

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fillSelect(select, items, { valueKey = "id", labelKey = "name", emptyLabel = "Semua" } = {}) {
    if (!select) return;
    const options = [`<option value="">${escapeHtml(emptyLabel)}</option>`];
    for (const item of items) {
      const label = item.label || item[labelKey] || item.name || item.id;
      options.push(
        `<option value="${item[valueKey]}">${escapeHtml(label)}</option>`
      );
    }
    select.innerHTML = options.join("");
  }

  function workspacesForDivision(divisionId) {
    const all = state.options?.workspaces || [];
    if (!divisionId) return all;
    return all.filter((w) => String(w.division_id) === String(divisionId));
  }

  function applyOptions(data) {
    state.options = data;
    const mode = data.mode || "member";

    fillSelect(els.division, data.divisions || [], {
      emptyLabel: "Semua Divisi",
    });
    fillSelect(els.workspace, data.workspaces || [], {
      labelKey: "label",
      emptyLabel: "Semua Workspace",
    });

    if (els.divisionWrap) {
      els.divisionWrap.hidden = !(data.can_choose_division || (data.divisions || []).length > 1);
      // Admin always sees division picker when divisions exist
      if (mode === "admin" && (data.divisions || []).length) els.divisionWrap.hidden = false;
      if (mode === "division") els.divisionWrap.hidden = (data.divisions || []).length <= 1;
      if (mode === "bidang" || mode === "member") els.divisionWrap.hidden = true;
    }
    if (els.workspaceWrap) {
      if (mode === "member") els.workspaceWrap.hidden = true;
      else if (mode === "bidang" && (data.workspaces || []).length <= 1) {
        els.workspaceWrap.hidden = true;
      } else {
        els.workspaceWrap.hidden = false;
      }
    }

    if (data.locked_division_id && els.division) {
      els.division.value = String(data.locked_division_id);
      els.division.disabled = !data.can_choose_division && (data.divisions || []).length <= 1;
    }
    if (data.locked_bidang_id && els.workspace) {
      els.workspace.value = String(data.locked_bidang_id);
      els.workspace.disabled = (data.workspaces || []).length <= 1;
    }

    if (els.note) {
      if (mode === "bidang") {
        const ws = (data.workspaces || [])[0];
        els.note.hidden = false;
        els.note.textContent = ws
          ? `Cakupan Anda: Bidang/Workspace “${ws.label || ws.name}”. Export mencakup seluruh project di Bidang ini.`
          : "Cakupan Anda mengikuti Bidang yang terhubung ke akun.";
      } else if (mode === "division") {
        const div = (data.divisions || [])[0];
        els.note.hidden = false;
        els.note.textContent = div
          ? `Cakupan Anda: Divisi “${div.name}”. Pilih workspace/Bidang untuk mempersempit export.`
          : "Cakupan Anda mengikuti Divisi yang Anda pimpin.";
      } else if (mode === "member") {
        els.note.hidden = false;
        els.note.textContent =
          "Cakupan Anda: project tempat Anda menjadi anggota/assignee.";
      } else {
        els.note.hidden = false;
        els.note.textContent = "Admin: dapat memilih Divisi dan Workspace/Bidang.";
      }
    }
  }

  function syncWorkspaceOptions() {
    const divisionId = els.division?.value || "";
    const current = els.workspace?.value || "";
    const items = workspacesForDivision(divisionId);
    fillSelect(els.workspace, items, {
      labelKey: "label",
      emptyLabel: "Semua Workspace",
    });
    if (current && items.some((w) => String(w.id) === String(current))) {
      els.workspace.value = current;
    }
  }

  async function downloadReport(event) {
    event.preventDefault();
    if (els.error) els.error.hidden = true;
    const params = new URLSearchParams();
    const divisionId = els.division?.disabled ? state.options?.locked_division_id : els.division?.value;
    const workspaceId = els.workspace?.disabled ? state.options?.locked_bidang_id : els.workspace?.value;
    const status = els.status?.value || "";
    if (divisionId) params.set("division_id", String(divisionId));
    if (workspaceId) {
      params.set("workspace_id", String(workspaceId));
      params.set("bidang_id", String(workspaceId));
    }
    if (status) params.set("project_status", status);

    if (els.btn) {
      els.btn.disabled = true;
      els.btn.textContent = "Menyiapkan…";
    }
    try {
      const res = await fetch(`/api/reports/projects.xlsx?${params.toString()}`, {
        credentials: "same-origin",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Gagal download (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const stamp = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `project-report_${stamp}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (els.error) {
        els.error.hidden = false;
        els.error.textContent = err.message || "Gagal mengunduh report.";
      }
    } finally {
      if (els.btn) {
        els.btn.disabled = false;
        els.btn.textContent = "Download Excel";
      }
    }
  }

  async function boot() {
    if (!els.form) return;
    els.form.addEventListener("submit", downloadReport);
    els.division?.addEventListener("change", syncWorkspaceOptions);
    try {
      const data = await api("/api/reports/options");
      applyOptions(data);
    } catch (err) {
      if (els.error) {
        els.error.hidden = false;
        els.error.textContent = err.message || "Gagal memuat opsi report.";
      }
    }
  }

  boot();
})();
