(() => {
  const $ = (id) => document.getElementById(id);

  const tabs = Array.from(document.querySelectorAll(".users-tab"));
  const panels = {
    users: $("panel-users"),
    roles: $("panel-roles"),
    matrix: $("panel-matrix"),
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
    if (valid === "matrix") loadPermissionMatrix();
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

  const askConfirm = (options) =>
    window.pmConfirm
      ? window.pmConfirm(options)
      : Promise.resolve(window.confirm(options?.message || "Lanjutkan?"));
  const showNotice = (options) =>
    window.pmNotice
      ? window.pmNotice(options)
      : Promise.resolve(window.alert(options?.message || "") || true);

  // —— Users ——
  const tbody = $("users-tbody");
  const statsEl = $("users-stats");
  const searchEl = $("user-search");
  const roleFilterEl = $("user-role-filter");
  const activeFilterEl = $("user-active-filter");
  const divisionFilterEl = $("user-division-filter");
  const bidangFilterEl = $("user-bidang-filter");
  const placementFilterEl = $("user-placement-filter");
  const modal = $("user-modal");
  const form = $("user-form");
  const formStatus = $("user-form-status");
  const titleEl = $("user-modal-title");
  const subtitleEl = $("user-modal-subtitle");
  const sendEmailWrap = $("send-email-wrap");
  const saveBtn = $("btn-save-user");

  let debounceTimer = null;
  let rolesList = [];
  let divisionsCache = [];
  let bidangCache = [];
  let usersCache = [];

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
      ["Belum ditempatkan", stats.unassigned || 0],
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
    place: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-4.5 7-11a7 7 0 1 0-14 0c0 6.5 7 11 7 11z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="10" r="2.4" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
    history: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v5l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    copy: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 16V6a2 2 0 0 1 2-2h10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    users: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 18a5.5 5.5 0 0 1 11 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="17" cy="9" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15 18a4.2 4.2 0 0 1 5.5-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  };

  function placementLabel(user) {
    const p = user.placement || {};
    if (!p.is_assigned) {
      return {
        division: "—",
        bidang: `<span class="badge badge-inactive">Belum ditempatkan</span>`,
      };
    }
    const leaderNote = user.is_leader ? ` <span class="badge badge-manager" title="Pemimpin unit">Pemimpin</span>` : "";
    return {
      division: escapeHtml(p.division_name || p.division_code || "—"),
      bidang: `${escapeHtml(p.bidang_name || p.bidang_code || "—")}${leaderNote}`,
    };
  }

  async function loadOrgOptions() {
    try {
      const [divRes, bidangRes] = await Promise.all([
        fetch("/api/divisions?active=true"),
        fetch("/api/bidang?active=true"),
      ]);
      if (divRes.ok) {
        const data = await divRes.json();
        divisionsCache = data.items || [];
      }
      if (bidangRes.ok) {
        const data = await bidangRes.json();
        bidangCache = data.items || [];
      }
      // Fallback for admins without organization.view (ownership picker is enough).
      if (!divisionsCache.length || !bidangCache.length) {
        const optRes = await fetch("/api/organization/ownership-options");
        if (optRes.ok) {
          const data = await optRes.json();
          if (!divisionsCache.length) divisionsCache = data.divisions || [];
          if (!bidangCache.length) bidangCache = data.bidangs || [];
        }
      }
    } catch {
      divisionsCache = [];
      bidangCache = [];
    }
    fillOrgFilters();
  }

  function fillUserModalBidang(divisionId, selectedBidangId = "") {
    const select = $("field-bidang");
    if (!select) return;
    const options = bidangCache.filter(
      (b) => !divisionId || String(b.division_id) === String(divisionId)
    );
    select.innerHTML =
      `<option value="">— Pilih Bidang —</option>` +
      options
        .map(
          (b) =>
            `<option value="${b.id}" ${
              String(b.id) === String(selectedBidangId || "") ? "selected" : ""
            }>${escapeHtml(b.code)} — ${escapeHtml(b.name)}</option>`
        )
        .join("");
  }

  function fillUserModalPlacement(user = null) {
    const placement = user?.placement || {};
    const divSelect = $("field-division");
    const versionEl = $("field-placement-version");
    const currentEl = $("field-placement-bidang-current");
    const leadEl = $("user-form-leadership");
    const ackWrap = $("user-ack-leadership-wrap");
    const ackBox = $("field-ack-leadership");
    if (versionEl) versionEl.value = String(placement.placement_version || 0);
    if (currentEl) currentEl.value = placement.bidang_id ? String(placement.bidang_id) : "";
    if (ackBox) ackBox.checked = false;
    const leadership = user?.leadership || [];
    if (leadEl && ackWrap) {
      if (leadership.length) {
        leadEl.hidden = false;
        leadEl.innerHTML =
          "Pemimpin unit: " +
          leadership
            .map((l) => `${escapeHtml(l.unit_type)} ${escapeHtml(l.code)} — ${escapeHtml(l.name)}`)
            .join("; ");
        ackWrap.hidden = false;
      } else {
        leadEl.hidden = true;
        leadEl.textContent = "";
        ackWrap.hidden = true;
      }
    }
    if (divSelect) {
      divSelect.innerHTML =
        `<option value="">— Pilih Divisi —</option>` +
        divisionsCache
          .map(
            (d) =>
              `<option value="${d.id}" ${
                String(d.id) === String(placement.division_id || "") ? "selected" : ""
              }>${escapeHtml(d.code)} — ${escapeHtml(d.name)}</option>`
          )
          .join("");
    }
    fillUserModalBidang(divSelect?.value || placement.division_id || "", placement.bidang_id || "");
  }

  async function syncUserPlacement(userId, { expectedVersion = 0 } = {}) {
    const bidangId = $("field-bidang")?.value || "";
    const currentBidangId = $("field-placement-bidang-current")?.value || "";
    if (String(bidangId) === String(currentBidangId)) return { skipped: true };
    if (!bidangId) {
      // Empty on edit means leave placement unchanged (use dedicated Penempatan modal to clear).
      return { skipped: true };
    }

    const sendPlacement = async (acknowledge) => {
      const res = await fetch(`/api/users/${userId}/placement`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clear: false,
          bidang_id: Number(bidangId),
          reason: "Ditetapkan dari form user",
          expected_version: Number(expectedVersion) || 0,
          acknowledge_leadership_conflict: Boolean(acknowledge),
        }),
      });
      const data = await res.json().catch(() => ({}));
      return { res, data };
    };

    let acknowledge = Boolean($("field-ack-leadership")?.checked);
    let { res, data } = await sendPlacement(acknowledge);

    if (res.status === 409 && data.detail?.code === "leadership_conflict") {
      const ackWrap = $("user-ack-leadership-wrap");
      const leadEl = $("user-form-leadership");
      if (ackWrap) ackWrap.hidden = false;
      const conflicts = (data.detail.conflicts || [])
        .map((c) => `${c.unit_type} ${c.code}`)
        .join(", ");
      if (leadEl) {
        leadEl.hidden = false;
        leadEl.textContent = conflicts
          ? `Pemimpin unit: ${conflicts}`
          : data.detail.message || "Pengguna masih menjadi pemimpin unit.";
      }
      const ok = await askConfirm({
        title: "Konflik kepemimpinan",
        message:
          data.detail.message ||
          "Pengguna masih menjadi pemimpin unit organisasi. Lanjutkan penempatan tanpa mengubah kepemimpinan?",
        meta: conflicts || undefined,
        tone: "warn",
        okText: "Lanjutkan Penempatan",
        cancelText: "Batal",
      });
      if (!ok) {
        throw new Error(
          `${data.detail.message || "Konflik kepemimpinan."}${
            conflicts ? ` (${conflicts})` : ""
          } Centang konfirmasi lalu simpan lagi, atau ubah pemimpin di Organization.`
        );
      }
      if ($("field-ack-leadership")) $("field-ack-leadership").checked = true;
      ({ res, data } = await sendPlacement(true));
    }

    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : data.detail?.message || "Gagal menyimpan penempatan";
      throw new Error(detail);
    }
    return data;
  }

  function fillOrgFilters() {
    const prevDiv = divisionFilterEl?.value || "";
    const prevBidang = bidangFilterEl?.value || "";
    if (divisionFilterEl) {
      divisionFilterEl.innerHTML =
        `<option value="">Semua Divisi</option>` +
        divisionsCache
          .map(
            (d) =>
              `<option value="${d.id}">${escapeHtml(d.code)} — ${escapeHtml(d.name)}</option>`
          )
          .join("");
      if (prevDiv) divisionFilterEl.value = prevDiv;
    }
    fillBidangFilter(prevBidang);
  }

  function fillBidangFilter(selectedId) {
    if (!bidangFilterEl) return;
    const divisionId = divisionFilterEl?.value || "";
    const options = bidangCache.filter((b) => !divisionId || String(b.division_id) === String(divisionId));
    bidangFilterEl.innerHTML =
      `<option value="">Semua Bidang</option>` +
      options
        .map(
          (b) =>
            `<option value="${b.id}">${escapeHtml(b.code)} — ${escapeHtml(b.name)}</option>`
        )
        .join("");
    if (selectedId && options.some((b) => String(b.id) === String(selectedId))) {
      bidangFilterEl.value = String(selectedId);
    }
  }

  function iconBtn(action, label, icon, extraClass = "") {
    return `<button type="button" class="icon-action ${extraClass}" data-action="${action}" title="${label}" aria-label="${label}">${icon}<span class="sr-only">${label}</span></button>`;
  }

  function renderRows(items) {
    usersCache = items || [];
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--muted)">Belum ada user.</td></tr>`;
      return;
    }
    tbody.innerHTML = items
      .map((user) => {
        const activeBadge = user.is_active
          ? `<span class="badge badge-active">Active</span>`
          : `<span class="badge badge-inactive">Inactive</span>`;
        const place = placementLabel(user);
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
          <td>${place.division}</td>
          <td>${place.bidang}</td>
          <td>${activeBadge}</td>
          <td>${fmtDate(user.last_login_at)}</td>
          <td class="col-actions">
            <div class="row-actions">
              ${iconBtn("edit", "Edit", ICONS.edit)}
              ${iconBtn("place", "Penempatan", ICONS.place)}
              ${iconBtn("history", "Riwayat Penempatan", ICONS.history)}
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
    if (divisionFilterEl?.value) params.set("division_id", divisionFilterEl.value);
    if (bidangFilterEl?.value) params.set("bidang_id", bidangFilterEl.value);
    if (placementFilterEl?.value === "unassigned") params.set("unassigned", "true");
    if (placementFilterEl?.value === "assigned") params.set("unassigned", "false");

    const res = await fetch(`/api/users?${params.toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (res.status === 403) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:#dc2626">Hanya Admin yang dapat mengelola user.</td></tr>`;
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
      mode === "edit"
        ? "Perbarui akun dan penempatan Divisi/Bidang."
        : "Buat akun baru, tetapkan penempatan, dan kirim undangan email.";
    fillUserModalPlacement(user || null);
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

  $("field-division")?.addEventListener("change", () => {
    fillUserModalBidang($("field-division").value, "");
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
    const willSendEmail = !id && $("field-send-email")?.checked;
    if (willSendEmail) {
      window.pmBusy?.show({
        title: "Membuat user & mengirim email…",
        message: "Sedang menyimpan akun dan mengirim email welcome. Mohon tunggu.",
      });
    }

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

      const savedUserId = id || data.id;
      const expectedVersion =
        Number($("field-placement-version")?.value) ||
        Number(data.placement?.placement_version) ||
        0;
      if (savedUserId) {
        await syncUserPlacement(savedUserId, { expectedVersion });
      }

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
      window.pmBusy?.hide();
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
        await showNotice({
          title: "Gagal memuat user",
          message: data.detail || "User tidak dapat dimuat.",
          tone: "danger",
          icon: "!",
        });
        return;
      }
      openModal("edit", data);
      return;
    }

    if (action === "place") {
      const cached = usersCache.find((u) => String(u.id) === String(id));
      if (cached) {
        openPlacementModal(cached);
        return;
      }
      const res = await fetch(`/api/users/${id}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        await showNotice({
          title: "Gagal memuat user",
          message: data.detail || "User tidak dapat dimuat.",
          tone: "danger",
          icon: "!",
        });
        return;
      }
      openPlacementModal(data);
      return;
    }

    if (action === "history") {
      await openHistoryModal(id);
      return;
    }

    if (action === "reset") {
      const userName = row.querySelector(".user-cell strong")?.textContent?.trim() || "user ini";
      const userEmail = row.querySelector(".user-cell small")?.textContent?.trim() || "";
      const ok = await askConfirm({
        title: "Reset password?",
        message: "Password sementara baru akan dibuat dan dikirim ke email pengguna.",
        meta: userEmail ? `${userName}\n${userEmail}` : userName,
        tone: "warn",
        icon: "⌨",
        okText: "Reset & Kirim Email",
        cancelText: "Batal",
      });
      if (!ok) return;

      btn.disabled = true;
      window.pmBusy?.show({
        title: "Mengirim email reset…",
        message: userEmail
          ? `Sedang menghubungi SMTP dan mengirim password baru ke ${userEmail}. Mohon tunggu.`
          : "Sedang menghubungi SMTP dan mengirim password baru. Mohon tunggu.",
      });
      try {
        const res = await fetch(`/api/users/${id}/reset-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ send_email: true }),
        });
        const data = await res.json().catch(() => ({}));
        window.pmBusy?.hide();
        if (!res.ok) {
          await showNotice({
            title: "Reset gagal",
            message: data.detail || "Gagal reset password",
            tone: "danger",
            icon: "!",
          });
          return;
        }
        await showNotice({
          title: "Password berhasil direset",
          message: data.email_sent
            ? "Password sementara sudah dibuat dan email berhasil dikirim."
            : "Password sementara sudah dibuat, tetapi email belum terkirim. Salin password di bawah.",
          meta: data.temporary_password
            ? `Password baru: ${data.temporary_password}${
                data.email_error ? `\nCatatan: ${data.email_error}` : ""
              }`
            : data.email_error || "",
          tone: data.email_sent ? "success" : "warn",
          icon: data.email_sent ? "✓" : "!",
        });
        await loadUsers();
      } catch (err) {
        window.pmBusy?.hide();
        await showNotice({
          title: "Reset gagal",
          message: err.message || "Gagal reset password",
          tone: "danger",
          icon: "!",
        });
      } finally {
        btn.disabled = false;
        window.pmBusy?.hide();
      }
      return;
    }

    if (action === "delete") {
      const userName = row.querySelector(".user-cell strong")?.textContent?.trim() || "user ini";
      const ok = await askConfirm({
        title: "Nonaktifkan user?",
        message: "Akses login user ini akan dinonaktifkan. Anda bisa mengaktifkannya lagi nanti.",
        meta: userName,
        tone: "danger",
        icon: "!",
        okText: "Nonaktifkan",
        cancelText: "Batal",
      });
      if (!ok) return;
      const res = await fetch(`/api/users/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        await showNotice({
          title: "Gagal menonaktifkan",
          message: data.detail || "Gagal menghapus user",
          tone: "danger",
          icon: "!",
        });
        return;
      }
      await loadUsers();
    }
  });

  function scheduleReload() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      loadUsers().catch((err) => {
        tbody.innerHTML = `<tr><td colspan="7" style="color:#dc2626">${escapeHtml(err.message)}</td></tr>`;
      });
    }, 250);
  }

  searchEl.addEventListener("input", scheduleReload);
  roleFilterEl.addEventListener("change", scheduleReload);
  activeFilterEl.addEventListener("change", scheduleReload);
  placementFilterEl?.addEventListener("change", scheduleReload);
  divisionFilterEl?.addEventListener("change", () => {
    fillBidangFilter("");
    scheduleReload();
  });
  bidangFilterEl?.addEventListener("change", scheduleReload);

  // —— Placement ——
  const placementModal = $("placement-modal");
  const placementForm = $("placement-form");
  const placementFormStatus = $("placement-form-status");
  const historyModal = $("history-modal");

  function fillPlacementBidangSelect(divisionId, selectedBidangId) {
    const select = $("placement-bidang");
    if (!select) return;
    const options = bidangCache.filter(
      (b) => !divisionId || String(b.division_id) === String(divisionId)
    );
    select.innerHTML =
      `<option value="">— Pilih Bidang —</option>` +
      options
        .map(
          (b) =>
            `<option value="${b.id}" ${
              String(b.id) === String(selectedBidangId || "") ? "selected" : ""
            }>${escapeHtml(b.code)} — ${escapeHtml(b.name)}</option>`
        )
        .join("");
  }

  function openPlacementModal(user) {
    const placement = user.placement || {};
    $("placement-user-id").value = user.id;
    $("placement-version").value = placement.placement_version || 0;
    $("placement-user-meta").textContent = `${user.name} · ${user.email}`;
    $("placement-current").innerHTML = placement.is_assigned
      ? `Saat ini: <strong>${escapeHtml(placement.division_name || "—")}</strong> / <strong>${escapeHtml(
          placement.bidang_name || "—"
        )}</strong>`
      : `Saat ini: <strong>Belum ditempatkan</strong>`;
    const leadership = user.leadership || [];
    const leadEl = $("placement-leadership");
    const ackWrap = $("placement-ack-wrap");
    if (leadership.length) {
      leadEl.hidden = false;
      leadEl.innerHTML =
        "Pemimpin unit: " +
        leadership
          .map((l) => `${escapeHtml(l.unit_type)} ${escapeHtml(l.code)} — ${escapeHtml(l.name)}`)
          .join("; ");
      ackWrap.hidden = false;
    } else {
      leadEl.hidden = true;
      leadEl.textContent = "";
      ackWrap.hidden = true;
    }
    $("placement-ack-leadership").checked = false;
    $("placement-reason").value = "";
    const divSelect = $("placement-division");
    divSelect.innerHTML =
      `<option value="">— Pilih Divisi —</option>` +
      divisionsCache
        .map(
          (d) =>
            `<option value="${d.id}" ${
              String(d.id) === String(placement.division_id || "") ? "selected" : ""
            }>${escapeHtml(d.code)} — ${escapeHtml(d.name)}</option>`
        )
        .join("");
    fillPlacementBidangSelect(divSelect.value || placement.division_id, placement.bidang_id);
    setStatus(placementFormStatus, "");
    placementModal.hidden = false;
  }

  function closePlacementModal() {
    placementModal.hidden = true;
  }

  $("placement-division")?.addEventListener("change", () => {
    fillPlacementBidangSelect($("placement-division").value, "");
  });

  async function submitPlacement({ clear = false } = {}) {
    const userId = $("placement-user-id").value;
    const bidangId = $("placement-bidang").value;
    if (!clear && !bidangId) {
      setStatus(placementFormStatus, "Pilih Bidang tujuan.", "err");
      return;
    }
    const payload = {
      clear: Boolean(clear),
      bidang_id: clear ? null : Number(bidangId),
      reason: $("placement-reason").value.trim(),
      expected_version: Number($("placement-version").value) || 0,
      acknowledge_leadership_conflict: Boolean($("placement-ack-leadership")?.checked),
    };
    setStatus(placementFormStatus, "Menyimpan penempatan…");
    try {
      const res = await fetch(`/api/users/${userId}/placement`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 409 && data.detail?.code === "leadership_conflict") {
        $("placement-ack-wrap").hidden = false;
        const conflicts = (data.detail.conflicts || [])
          .map((c) => `${c.unit_type} ${c.code}`)
          .join(", ");
        setStatus(
          placementFormStatus,
          `${data.detail.message || "Konflik kepemimpinan."}${conflicts ? ` (${conflicts})` : ""} Centang konfirmasi lalu simpan lagi.`,
          "err"
        );
        return;
      }
      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : data.detail?.message || "Gagal menyimpan penempatan";
        throw new Error(detail);
      }
      closePlacementModal();
      await loadUsers();
      await showNotice({
        title: data.unchanged ? "Tidak ada perubahan" : "Penempatan disimpan",
        message: data.unchanged
          ? "Penempatan sudah sama dengan sebelumnya."
          : "Divisi mengikuti Bidang induk. Role dan permission tidak berubah.",
        tone: "success",
        icon: "✓",
      });
    } catch (err) {
      setStatus(placementFormStatus, err.message || "Gagal menyimpan", "err");
    }
  }

  placementForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitPlacement({ clear: false });
  });
  $("btn-clear-placement")?.addEventListener("click", async () => {
    const ok = await askConfirm({
      title: "Hapus penempatan?",
      message: "Pengguna akan menjadi belum ditempatkan. Kepemimpinan unit tidak dihapus otomatis.",
      tone: "warn",
      okText: "Hapus Penempatan",
      cancelText: "Batal",
    });
    if (!ok) return;
    await submitPlacement({ clear: true });
  });
  $("btn-close-placement-modal")?.addEventListener("click", closePlacementModal);
  $("btn-cancel-placement")?.addEventListener("click", closePlacementModal);
  placementModal?.addEventListener("click", (event) => {
    if (event.target === placementModal) closePlacementModal();
  });

  async function openHistoryModal(userId) {
    const list = $("history-list");
    list.innerHTML = `<p class="org-empty">Memuat riwayat…</p>`;
    historyModal.hidden = false;
    try {
      const res = await fetch(`/api/users/${userId}/placement-history`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal memuat riwayat");
      const items = data.items || [];
      if (!items.length) {
        list.innerHTML = `<p class="org-empty">Belum ada riwayat penempatan.</p>`;
        return;
      }
      list.innerHTML = items
        .map((row) => {
          const fromLabel = row.from_bidang_code
            ? `${escapeHtml(row.from_division_code)} / ${escapeHtml(row.from_bidang_code)}`
            : "—";
          const toLabel = row.to_bidang_code
            ? `${escapeHtml(row.to_division_code)} / ${escapeHtml(row.to_bidang_code)}`
            : "Belum ditempatkan";
          return `<article class="history-item">
            <header>
              <strong>${escapeHtml(row.action)}</strong>
              <span>${fmtDate(row.created_at)}</span>
            </header>
            <p>${fromLabel} → ${toLabel}</p>
            <p class="meta">Oleh: ${escapeHtml(row.actor_name || "—")}${
            row.reason ? ` · ${escapeHtml(row.reason)}` : ""
          }</p>
          </article>`;
        })
        .join("");
    } catch (err) {
      list.innerHTML = `<p class="org-empty" style="color:#dc2626">${escapeHtml(err.message)}</p>`;
    }
  }

  function closeHistoryModal() {
    historyModal.hidden = true;
  }
  $("btn-close-history-modal")?.addEventListener("click", closeHistoryModal);
  $("btn-close-history")?.addEventListener("click", closeHistoryModal);
  historyModal?.addEventListener("click", (event) => {
    if (event.target === historyModal) closeHistoryModal();
  });

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
    const assignable = permissionCatalog.filter((item) => (item.status || "active") === "active");
    const groups = {};
    assignable.forEach((item) => {
      const cat = item.category || "Other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    });
    rolePermBox.innerHTML = Object.entries(groups)
      .map(
        ([category, items]) => `
      <fieldset class="perm-group">
        <legend>${escapeHtml(category)}</legend>
        <div class="perm-grid">
          ${items
            .map(
              (item) => `
            <label class="perm-item" title="${escapeHtml(item.description || item.key)}">
              <input type="checkbox" name="perm" value="${escapeHtml(item.key)}" ${
                selectedSet.has(item.key) ? "checked" : ""
              } />
              <span>
                <strong>${escapeHtml(item.label)}</strong>
                <small>${escapeHtml(item.key)}</small>
              </span>
            </label>`
            )
            .join("")}
        </div>
      </fieldset>`
      )
      .join("");
  }

  function selectedPermissions() {
    return Array.from(roleForm.querySelectorAll('input[name="perm"]:checked')).map((el) => el.value);
  }

  function renderRoles(items) {
    if (!items.length) {
      rolesTbody.innerHTML = `<tr><td colspan="6" style="color:var(--muted)">Belum ada role.</td></tr>`;
      return;
    }
    rolesTbody.innerHTML = items
      .map((role) => {
        const chips = (role.permissions || [])
          .slice(0, 5)
          .map((p) => `<span class="perm-chip">${escapeHtml(p)}</span>`)
          .join("");
        const more =
          (role.permissions || []).length > 5
            ? `<span class="perm-chip">+${role.permissions.length - 5}</span>`
            : "";
        return `
        <tr data-id="${role.id}">
          <td>
            <strong>${escapeHtml(role.name)}</strong>
            <div class="role-desc">${
              role.description ? escapeHtml(role.description) : "—"
            }</div>
            ${role.is_system ? '<div style="margin-top:4px"><span class="badge badge-admin">System</span></div>' : ""}
          </td>
          <td><code class="role-code">${escapeHtml(role.code)}</code></td>
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
              ${iconBtn("users-role", "Lihat Users", ICONS.users)}
              ${iconBtn("dup-role", "Duplikasi Role", ICONS.copy)}
              ${
                role.is_system || role.is_protected
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
    if (role?.is_protected) {
      $("role-active").disabled = true;
    } else {
      $("role-active").disabled = false;
    }
    $("role-modal-title").textContent = role ? "Edit Role" : "New Role";
    $("role-modal-subtitle").textContent = role
      ? "Perbarui parameter role dan permission."
      : "Buat role baru dengan permission yang sesuai.";
    renderPermissionChecks(role?.permissions || []);
    const hint = $("role-phase4-hint");
    const pending = role?.phase4_pending_permissions || [];
    if (hint) {
      if (pending.length) {
        hint.hidden = false;
        hint.textContent =
          "Phase 4 (organizational scope) dapat menambahkan: " + pending.join(", ");
      } else {
        hint.hidden = true;
        hint.textContent = "";
      }
    }
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

  async function openRoleUsersModal(role) {
    const modal = $("role-users-modal");
    const list = $("role-users-list");
    if (!modal || !list) return;
    $("role-users-title").textContent = `Pengguna · ${role.name}`;
    $("role-users-subtitle").textContent = `Kode: ${role.code}`;
    list.innerHTML = `<p class="org-empty">Memuat…</p>`;
    modal.hidden = false;
    try {
      const res = await fetch(`/api/roles/${role.id}/users`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal memuat pengguna role");
      const items = data.items || [];
      if (!items.length) {
        list.innerHTML = `<p class="org-empty">Belum ada pengguna pada role ini.</p>`;
        return;
      }
      list.innerHTML = items
        .map(
          (u) => `<div class="member-row">
            <strong>${escapeHtml(u.name)}</strong>
            <span>${escapeHtml(u.email)}</span>
            <span class="meta">${u.is_active ? "Aktif" : "Nonaktif"}</span>
          </div>`
        )
        .join("");
    } catch (err) {
      list.innerHTML = `<p class="org-empty" style="color:#dc2626">${escapeHtml(err.message)}</p>`;
    }
  }

  function closeRoleUsersModal() {
    const modal = $("role-users-modal");
    if (modal) modal.hidden = true;
  }
  $("btn-close-role-users")?.addEventListener("click", closeRoleUsersModal);
  $("btn-close-role-users-footer")?.addEventListener("click", closeRoleUsersModal);
  $("role-users-modal")?.addEventListener("click", (event) => {
    if (event.target === $("role-users-modal")) closeRoleUsersModal();
  });

  function openDupModal(role) {
    $("role-dup-source-id").value = role.id;
    $("role-dup-code").value = `${role.code}-copy`.slice(0, 40);
    $("role-dup-name").value = `${role.name} (Copy)`.slice(0, 80);
    setStatus($("role-dup-status"), "");
    $("role-dup-modal").hidden = false;
  }
  function closeDupModal() {
    $("role-dup-modal").hidden = true;
  }
  $("btn-close-role-dup")?.addEventListener("click", closeDupModal);
  $("btn-cancel-role-dup")?.addEventListener("click", closeDupModal);
  $("role-dup-modal")?.addEventListener("click", (event) => {
    if (event.target === $("role-dup-modal")) closeDupModal();
  });
  $("role-dup-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("role-dup-source-id").value;
    const payload = {
      code: $("role-dup-code").value.trim(),
      name: $("role-dup-name").value.trim(),
    };
    setStatus($("role-dup-status"), "Menduplikasi…");
    try {
      const res = await fetch(`/api/roles/${id}/duplicate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menduplikasi role");
      closeDupModal();
      await loadRoles();
      setStatus(rolesStatus, `Role ${data.code} dibuat dari duplikasi.`, "ok");
    } catch (err) {
      setStatus($("role-dup-status"), err.message || "Gagal", "err");
    }
  });

  async function loadPermissionMatrix() {
    const host = $("permission-matrix");
    const statusEl = $("matrix-status");
    if (!host) return;
    setStatus(statusEl, "Memuat matrix…");
    try {
      const res = await fetch("/api/roles/matrix");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal memuat matrix");
      const roles = data.roles || [];
      const perms = (data.permissions || []).filter((p) => (p.status || "active") === "active");
      if (!roles.length || !perms.length) {
        host.innerHTML = `<p class="org-empty">Belum ada data matrix.</p>`;
        setStatus(statusEl, "");
        return;
      }
      const head = `<tr><th>Permission</th>${roles
        .map((r) => `<th title="${escapeHtml(r.code)}">${escapeHtml(r.name)}</th>`)
        .join("")}</tr>`;
      const body = perms
        .map((p) => {
          const cells = roles
            .map((r) => {
              const has = (r.permissions || []).includes(p.key);
              return `<td class="${has ? "matrix-yes" : "matrix-no"}">${has ? "✓" : "·"}</td>`;
            })
            .join("");
          return `<tr><th scope="row"><span>${escapeHtml(p.label)}</span><small>${escapeHtml(
            p.key
          )}</small></th>${cells}</tr>`;
        })
        .join("");
      host.innerHTML = `<div class="matrix-scroll"><table class="matrix-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
      setStatus(statusEl, "");
    } catch (err) {
      host.innerHTML = "";
      setStatus(statusEl, err.message || "Gagal memuat matrix", "err");
    }
  }

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

    if (btn.dataset.action === "users-role") {
      await openRoleUsersModal(role);
      return;
    }

    if (btn.dataset.action === "dup-role") {
      openDupModal(role);
      return;
    }

    if (btn.dataset.action === "delete-role") {
      const ok = await askConfirm({
        title: "Hapus role?",
        message: "Role yang dihapus tidak bisa dipakai lagi untuk user baru.",
        meta: `${role.name} (${role.code})`,
        tone: "danger",
        icon: "!",
        okText: "Hapus Role",
        cancelText: "Batal",
      });
      if (!ok) return;
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

  loadOrgOptions()
    .then(() => loadUsers())
    .catch((err) => {
      tbody.innerHTML = `<tr><td colspan="7" style="color:#dc2626">${escapeHtml(err.message)}</td></tr>`;
    });
  loadRoles();
})();
