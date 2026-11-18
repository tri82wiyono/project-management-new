(() => {
  const $ = (id) => document.getElementById(id);

  const tabs = Array.from(document.querySelectorAll(".users-tab"));
  const panels = {
    users: $("panel-users"),
    roles: $("panel-roles"),
  };

  const btnNewUser = $("btn-new-user");
  const btnNewRole = $("btn-new-role");

  function activateTab(key) {
    const valid = panels[key] ? key : "users";
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === valid;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    Object.entries(panels).forEach(([name, panel]) => {
      if (!panel) return;
      const active = name === valid;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
    btnNewUser.hidden = valid !== "users";
    btnNewRole.hidden = valid !== "roles";
    history.replaceState(null, "", `#${valid}`);
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));
  activateTab((location.hash || "").replace("#", "") || "users");

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  // —— Users ——
  const tbody = $("users-tbody");
  const statsEl = $("users-stats");
  const searchEl = $("user-search");
  const roleFilterEl = $("user-role-filter");
  const activeFilterEl = $("user-active-filter");
  const modal = $("user-modal");
  const form = $("user-form");
  const formStatus = $("user-form-status");
  const titleEl = $("user-modal-title");
  const subtitleEl = $("user-modal-subtitle");
  const sendEmailWrap = $("send-email-wrap");
  const saveBtn = $("btn-save-user");

  let debounceTimer = null;
  let rolesList = [];

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
  }

  function fmtDate(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("id-ID", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "—";
    }
  }

  function roleBadge(role) {
    const raw = String(role || "Member");
    const key = raw.toLowerCase();
    const known = { admin: "admin", manager: "manager", member: "member" };
    const cls = known[key] || "role";
    return `<span class="badge badge-${cls}" title="${escapeHtml(raw)}">${escapeHtml(raw)}</span>`;
  }

  function fillRoleSelects() {
    const options = rolesList
      .map(
        (role) =>
          `<option value="${escapeHtml(role.code)}">${escapeHtml(role.name)} (${escapeHtml(
            role.code
          )})</option>`
      )
      .join("");
    roleFilterEl.innerHTML = `<option value="">All Roles</option>${options}`;
    $("field-role").innerHTML = options || `<option value="Member">Member</option>`;
  }

  function renderStats(stats) {
    const items = [
      ["Total", stats.total || 0],
      ["Active", stats.active || 0],
      ["Inactive", stats.inactive || 0],
      ["Admin", stats.admins || 0],
    ];
    statsEl.innerHTML = items
      .map(
        ([label, value]) => `
      <article class="stat-card">
        <span>${label}</span>
        <strong>${value}</strong>
      </article>`
      )
      .join("");
  }

  const ICONS = {
    edit: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4.5L18.5 10a1.5 1.5 0 0 0 0-2.1L16.1 5.5a1.5 1.5 0 0 0-2.1 0L4 15.5V20z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M13.5 6.5l4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    reset: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V7a5 5 0 0 1 10 0v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><rect x="5" y="10" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="15" r="1.4" fill="currentColor"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 7l1 12a2 2 0 0 0 2 1.8h2a2 2 0 0 0 2-1.8L16 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`,
  };

  function iconBtn(action, label, icon, extraClass = "") {
    return `<button type="button" class="icon-action ${extraClass}" data-action="${action}" title="${label}" aria-label="${label}">${icon}<span class="sr-only">${label}</span></button>`;
  }

  function renderRows(items) {
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">Belum ada user.</td></tr>`;
      return;
    }
    tbody.innerHTML = items
      .map((user) => {
        const activeBadge = user.is_active
          ? `<span class="badge badge-active">Active</span>`
          : `<span class="badge badge-inactive">Inactive</span>`;
        return `
        <tr data-id="${user.id}">
          <td>
            <div class="user-cell">
              <img src="${user.avatar_url}" alt="" />
              <div>
                <strong>${escapeHtml(user.name)}</strong>
                <span>${escapeHtml(user.email)}</span>
              </div>
            </div>
          </td>
          <td>${roleBadge(user.role)}</td>
          <td>${activeBadge}</td>
          <td>${fmtDate(user.last_login_at)}</td>
          <td class="col-actions">
            <div class="row-actions">
              ${iconBtn("edit", "Edit", ICONS.edit)}
              ${iconBtn("reset", "Reset Password", ICONS.reset)}
              ${iconBtn("delete", "Delete", ICONS.trash, "danger")}
            </div>
          </td>
        </tr>`;
      })
      .join("");
  }

  async function loadUsers() {
    const params = new URLSearchParams();
    if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
    if (roleFilterEl.value) params.set("role", roleFilterEl.value);
    if (activeFilterEl.value) params.set("active", activeFilterEl.value);

    const res = await fetch(`/api/users?${params.toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (res.status === 403) {
      tbody.innerHTML = `<tr><td colspan="5" style="color:#dc2626">Hanya Admin yang dapat mengelola user.</td></tr>`;
      return;
    }
    if (!res.ok) throw new Error("Gagal memuat users");
    const data = await res.json();
    const previousRoleFilter = roleFilterEl.value;
    const previousFormRole = $("field-role").value;
    rolesList = data.roles || [];
    fillRoleSelects();
    if (previousRoleFilter) roleFilterEl.value = previousRoleFilter;
    if (previousFormRole) $("field-role").value = previousFormRole;
    renderStats(data.stats || {});
    renderRows(data.items || []);
  }

  function openModal(mode, user) {
    form.reset();
    $("user-id").value = user?.id || "";
    $("field-name").value = user?.name || "";
    $("field-email").value = user?.email || "";
    $("field-role").value = user?.role || "Member";
    $("field-active").checked = user ? Boolean(user.is_active) : true;
    $("field-send-email").checked = true;
    sendEmailWrap.hidden = mode === "edit";
    titleEl.textContent = mode === "edit" ? "Edit User" : "New User";
    subtitleEl.textContent =
      mode === "edit" ? "Perbarui data akun pengguna." : "Buat akun baru dan kirim undangan email.";
    setStatus(formStatus, "");
    modal.hidden = false;
  }

  function closeModal() {
    modal.hidden = true;
  }

  $("btn-new-user").addEventListener("click", () => openModal("create"));
  $("btn-close-user-modal").addEventListener("click", closeModal);
  $("btn-cancel-user").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    saveBtn.disabled = true;
    setStatus(formStatus, "Menyimpan…");

    const id = $("user-id").value;
    const payload = {
      name: $("field-name").value.trim(),
      email: $("field-email").value.trim(),
      role: $("field-role").value,
      is_active: $("field-active").checked,
    };

    try {
      let res;
      if (id) {
        res = await fetch(`/api/users/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        payload.send_email = $("field-send-email").checked;
        res = await fetch("/api/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menyimpan user");

      if (!id && data.temporary_password) {
        const mailNote = data.email_sent
          ? "Email welcome terkirim."
          : data.email_error
            ? `Email gagal: ${data.email_error}`
            : "Email tidak dikirim.";
        setStatus(
          formStatus,
          `User dibuat. Password sementara: ${data.temporary_password}. ${mailNote}`,
          data.email_sent || !payload.send_email ? "ok" : "err"
        );
      } else {
        setStatus(formStatus, "User tersimpan.", "ok");
        closeModal();
      }
      await loadUsers();
    } catch (err) {
      setStatus(formStatus, err.message || "Gagal menyimpan", "err");
    } finally {
      saveBtn.disabled = false;
    }
  });

  tbody.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const row = btn.closest("tr[data-id]");
    if (!row) return;
    const id = row.dataset.id;
    const action = btn.dataset.action;

    if (action === "edit") {
      const res = await fetch(`/api/users/${id}`);
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || "Gagal memuat user");
        return;
      }
      openModal("edit", data);
      return;
    }

    if (action === "reset") {
      if (!confirm("Reset password user ini dan kirim email?")) return;
      const res = await fetch(`/api/users/${id}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ send_email: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        alert(data.detail || "Gagal reset password");
        return;
      }
      alert(
        `Password baru: ${data.temporary_password}\n${
          data.email_sent ? "Email terkirim." : data.email_error || "Email tidak terkirim."
        }`
      );
      await loadUsers();
      return;
    }

    if (action === "delete") {
      if (!confirm("Nonaktifkan / hapus akses user ini?")) return;
      const res = await fetch(`/api/users/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        alert(data.detail || "Gagal menghapus user");
        return;
      }
      await loadUsers();
    }
  });

  function scheduleReload() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      loadUsers().catch((err) => {
        tbody.innerHTML = `<tr><td colspan="5" style="color:#dc2626">${escapeHtml(err.message)}</td></tr>`;
      });
    }, 250);
  }

  searchEl.addEventListener("input", scheduleReload);
  roleFilterEl.addEventListener("change", scheduleReload);
  activeFilterEl.addEventListener("change", scheduleReload);

  // —— Roles ——
  const rolesTbody = $("roles-tbody");
  const rolesStatus = $("roles-status");
  const roleModal = $("role-modal");
  const roleForm = $("role-form");
  const roleFormStatus = $("role-form-status");
  const rolePermBox = $("role-permissions");
  const roleSaveBtn = $("btn-save-role");
  let permissionCatalog = [];
  let rolesCache = [];

  function renderPermissionChecks(selected) {
    const selectedSet = new Set(selected || []);
    rolePermBox.innerHTML = permissionCatalog
      .map(
        (item) => `
      <label class="perm-item">
        <input type="checkbox" name="perm" value="${escapeHtml(item.key)}" ${
          selectedSet.has(item.key) ? "checked" : ""
        } />
        <span>${escapeHtml(item.label)}</span>
      </label>`
      )
      .join("");
  }

  function selectedPermissions() {
    return Array.from(roleForm.querySelectorAll('input[name="perm"]:checked')).map((el) => el.value);
  }

  function renderRoles(items) {
    if (!items.length) {
      rolesTbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">Belum ada role.</td></tr>`;
      return;
    }
    rolesTbody.innerHTML = items
      .map((role) => {
        const chips = (role.permissions || [])
          .slice(0, 6)
          .map((p) => `<span class="perm-chip">${escapeHtml(p)}</span>`)
          .join("");
        const more =
          (role.permissions || []).length > 6
            ? `<span class="perm-chip">+${role.permissions.length - 6}</span>`
            : "";
        return `
        <tr data-id="${role.id}">
          <td>
            <strong class="role-code">${escapeHtml(role.code)}</strong>
            <div class="role-desc">${escapeHtml(role.name)}${
          role.description ? " · " + escapeHtml(role.description) : ""
        }</div>
            ${role.is_system ? '<div style="margin-top:4px"><span class="badge badge-admin">System</span></div>' : ""}
          </td>
          <td><div class="perm-chips">${chips}${more}</div></td>
          <td>${role.user_count ?? 0}</td>
          <td>${
            role.is_active
              ? '<span class="badge badge-active">Active</span>'
              : '<span class="badge badge-inactive">Inactive</span>'
          }</td>
          <td class="col-actions">
            <div class="row-actions">
              ${iconBtn("edit-role", "Edit Role", ICONS.edit)}
              ${
                role.is_system
                  ? ""
                  : iconBtn("delete-role", "Hapus Role", ICONS.trash, "danger")
              }
            </div>
          </td>
        </tr>`;
      })
      .join("");
  }

  function openRoleModal(role) {
    $("role-id").value = role?.id || "";
    $("role-code").value = role?.code || "";
    $("role-code").disabled = Boolean(role);
    $("role-name").value = role?.name || "";
    $("role-description").value = role?.description || "";
    $("role-sort").value = role?.sort_order ?? 100;
    $("role-active").checked = role ? Boolean(role.is_active) : true;
    $("role-modal-title").textContent = role ? "Edit Role" : "New Role";
    $("role-modal-subtitle").textContent = role
      ? "Perbarui parameter role dan permission."
      : "Buat role baru dengan permission yang sesuai.";
    renderPermissionChecks(role?.permissions || []);
    setStatus(roleFormStatus, "");
    roleModal.hidden = false;
  }

  function closeRoleModal() {
    roleModal.hidden = true;
  }

  async function loadRoles() {
    setStatus(rolesStatus, "Memuat roles…");
    try {
      const res = await fetch("/api/roles");
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal memuat roles");
      permissionCatalog = data.permissions || [];
      rolesCache = data.items || [];
      renderRoles(rolesCache);
      setStatus(rolesStatus, "");
    } catch (err) {
      setStatus(rolesStatus, err.message || "Gagal memuat roles", "err");
      rolesTbody.innerHTML = `<tr><td colspan="5" style="color:#dc2626">${escapeHtml(
        err.message || "Error"
      )}</td></tr>`;
    }
  }

  $("btn-new-role").addEventListener("click", () => openRoleModal(null));
  $("btn-close-role-modal").addEventListener("click", closeRoleModal);
  $("btn-cancel-role").addEventListener("click", closeRoleModal);
  roleModal.addEventListener("click", (event) => {
    if (event.target === roleModal) closeRoleModal();
  });

  roleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    roleSaveBtn.disabled = true;
    setStatus(roleFormStatus, "Menyimpan…");

    const id = $("role-id").value;
    const payload = {
      name: $("role-name").value.trim(),
      description: $("role-description").value.trim(),
      permissions: selectedPermissions(),
      is_active: $("role-active").checked,
      sort_order: Number($("role-sort").value) || 100,
    };

    try {
      let res;
      if (id) {
        res = await fetch(`/api/roles/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        payload.code = $("role-code").value.trim();
        res = await fetch("/api/roles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menyimpan role");
      closeRoleModal();
      await loadRoles();
      await loadUsers();
      setStatus(rolesStatus, "Role tersimpan.", "ok");
    } catch (err) {
      setStatus(roleFormStatus, err.message || "Gagal menyimpan", "err");
    } finally {
      roleSaveBtn.disabled = false;
    }
  });

  rolesTbody.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const row = btn.closest("tr[data-id]");
    if (!row) return;
    const id = Number(row.dataset.id);
    const role = rolesCache.find((item) => item.id === id);
    if (!role) return;

    if (btn.dataset.action === "edit-role") {
      openRoleModal(role);
      return;
    }

    if (btn.dataset.action === "delete-role") {
      if (!confirm(`Hapus role ${role.code}?`)) return;
      const res = await fetch(`/api/roles/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus(rolesStatus, data.detail || "Gagal menghapus role", "err");
        return;
      }
      await loadRoles();
      await loadUsers();
      setStatus(rolesStatus, "Role dihapus.", "ok");
    }
  });

  loadUsers().catch((err) => {
    tbody.innerHTML = `<tr><td colspan="5" style="color:#dc2626">${escapeHtml(err.message)}</td></tr>`;
  });
  loadRoles();
})();
