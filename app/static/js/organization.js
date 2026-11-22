(() => {
  const $ = (id) => document.getElementById(id);

  const tabs = Array.from(document.querySelectorAll(".users-tab"));
  const panels = {
    divisions: $("panel-divisions"),
    bidang: $("panel-bidang"),
    structure: $("panel-structure"),
  };
  const btnNewDivision = $("btn-new-division");
  const btnNewBidang = $("btn-new-bidang");

  function activateTab(key) {
    const valid = panels[key] ? key : "divisions";
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
    btnNewDivision.hidden = valid !== "divisions";
    btnNewBidang.hidden = valid !== "bidang";
    history.replaceState(null, "", `#${valid}`);
    if (valid === "structure") loadStructure();
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));

  const escapeHtml = (value) =>
    String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const askConfirm = (options) =>
    window.pmConfirm
      ? window.pmConfirm(options)
      : Promise.resolve(window.confirm(options?.message || "Lanjutkan?"));
  const showNotice = (options) =>
    window.pmNotice
      ? window.pmNotice(options)
      : Promise.resolve(window.alert(options?.message || "") || true);

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
            : `Request failed (${res.status})`;
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function statusBadge(active) {
    return active
      ? `<span class="org-badge active">Aktif</span>`
      : `<span class="org-badge inactive">Nonaktif</span>`;
  }

  function leaderLabel(leader) {
    if (!leader) return "—";
    const inactive = leader.is_active ? "" : " (nonaktif)";
    return `${escapeHtml(leader.name)}${inactive}`;
  }

  let users = [];
  let divisionsCache = [];

  async function loadUsers() {
    try {
      users = await api("/api/team?active_only=true");
    } catch {
      users = [];
    }
  }

  function fillLeaderSelect(selectEl, selectedId) {
    if (!selectEl) return;
    const current = selectedId == null ? "" : String(selectedId);
    selectEl.innerHTML =
      `<option value="">— Belum ditetapkan —</option>` +
      users
        .map(
          (u) =>
            `<option value="${u.id}" ${String(u.id) === current ? "selected" : ""}>${escapeHtml(
              u.name
            )} (${escapeHtml(u.email)})</option>`
        )
        .join("");
  }

  function fillDivisionSelect(selectEl, selectedId, { includeEmpty = false } = {}) {
    if (!selectEl) return;
    const current = selectedId == null ? "" : String(selectedId);
    const options = divisionsCache
      .map(
        (d) =>
          `<option value="${d.id}" ${String(d.id) === current ? "selected" : ""}>${escapeHtml(
            d.code
          )} — ${escapeHtml(d.name)}</option>`
      )
      .join("");
    selectEl.innerHTML = (includeEmpty ? `<option value="">Semua Divisi</option>` : "") + options;
  }

  // —— Divisions ——
  const divisionsTbody = $("divisions-tbody");
  const divisionSearch = $("division-search");
  const divisionActiveFilter = $("division-active-filter");
  const divisionModal = $("division-modal");
  const divisionForm = $("division-form");
  const divisionFormStatus = $("division-form-status");

  async function loadDivisions() {
    const params = new URLSearchParams();
    const q = (divisionSearch?.value || "").trim();
    const active = divisionActiveFilter?.value;
    if (q) params.set("q", q);
    if (active === "true" || active === "false") params.set("active", active);
    try {
      const data = await api(`/api/divisions?${params.toString()}`);
      divisionsCache = data.items || [];
      renderDivisions(divisionsCache);
      fillDivisionSelect($("bidang-division-filter"), $("bidang-division-filter")?.value || "", {
        includeEmpty: true,
      });
      fillDivisionSelect($("bidang-division"), $("bidang-division")?.value || "");
    } catch (err) {
      divisionsTbody.innerHTML = `<tr><td colspan="6" style="color:#dc2626">${escapeHtml(
        err.message
      )}</td></tr>`;
    }
  }

  function renderDivisions(items) {
    if (!items.length) {
      divisionsTbody.innerHTML = `<tr><td colspan="6" class="org-empty">Belum ada Divisi. Buat Divisi terlebih dahulu.</td></tr>`;
      return;
    }
    divisionsTbody.innerHTML = items
      .map(
        (d) => `<tr>
        <td><strong>${escapeHtml(d.code)}</strong></td>
        <td>${escapeHtml(d.name)}</td>
        <td>${leaderLabel(d.leader)}</td>
        <td>${d.bidang_count ?? 0}</td>
        <td>${statusBadge(d.is_active)}</td>
        <td class="col-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-edit-division="${d.id}">Edit</button>
          <button type="button" class="btn btn-ghost btn-sm" data-toggle-division="${d.id}" data-active="${
          d.is_active ? "1" : "0"
        }">${d.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
        </td>
      </tr>`
      )
      .join("");
  }

  function openDivisionModal(row = null) {
    $("division-id").value = row ? row.id : "";
    $("division-modal-title").textContent = row ? "Edit Divisi" : "Divisi Baru";
    $("division-code").value = row?.code || "";
    $("division-name").value = row?.name || "";
    $("division-description").value = row?.description || "";
    $("division-active").checked = row ? Boolean(row.is_active) : true;
    fillLeaderSelect($("division-leader"), row?.leader_user_id ?? "");
    setStatus(divisionFormStatus, "");
    divisionModal.hidden = false;
  }

  function closeDivisionModal() {
    divisionModal.hidden = true;
  }

  divisionForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $("division-id").value;
    const leaderVal = $("division-leader").value;
    const payload = {
      code: $("division-code").value.trim(),
      name: $("division-name").value.trim(),
      description: $("division-description").value.trim(),
      is_active: $("division-active").checked,
      leader_user_id: leaderVal ? Number(leaderVal) : null,
      clear_leader: !leaderVal,
    };
    try {
      if (id) {
        await api(`/api/divisions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        delete payload.clear_leader;
        await api("/api/divisions", { method: "POST", body: JSON.stringify(payload) });
      }
      closeDivisionModal();
      await loadDivisions();
      await showNotice({ title: "Berhasil", message: "Divisi disimpan." });
    } catch (err) {
      setStatus(divisionFormStatus, err.message, "err");
    }
  });

  // —— Bidang ——
  const bidangTbody = $("bidang-tbody");
  const bidangSearch = $("bidang-search");
  const bidangDivisionFilter = $("bidang-division-filter");
  const bidangActiveFilter = $("bidang-active-filter");
  const bidangModal = $("bidang-modal");
  const bidangForm = $("bidang-form");
  const bidangFormStatus = $("bidang-form-status");

  async function loadBidang() {
    const params = new URLSearchParams();
    const q = (bidangSearch?.value || "").trim();
    const divisionId = bidangDivisionFilter?.value;
    const active = bidangActiveFilter?.value;
    if (q) params.set("q", q);
    if (divisionId) params.set("division_id", divisionId);
    if (active === "true" || active === "false") params.set("active", active);
    try {
      const data = await api(`/api/bidang?${params.toString()}`);
      renderBidang(data.items || []);
    } catch (err) {
      bidangTbody.innerHTML = `<tr><td colspan="6" style="color:#dc2626">${escapeHtml(
        err.message
      )}</td></tr>`;
    }
  }

  function renderBidang(items) {
    if (!items.length) {
      bidangTbody.innerHTML = `<tr><td colspan="6" class="org-empty">Belum ada Bidang.</td></tr>`;
      return;
    }
    bidangTbody.innerHTML = items
      .map(
        (b) => `<tr>
        <td><strong>${escapeHtml(b.code)}</strong></td>
        <td>${escapeHtml(b.name)}</td>
        <td>${escapeHtml(b.division_code)} — ${escapeHtml(b.division_name)}</td>
        <td>${leaderLabel(b.leader)}</td>
        <td>${statusBadge(b.is_active)}</td>
        <td class="col-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-edit-bidang="${b.id}">Edit</button>
          <button type="button" class="btn btn-ghost btn-sm" data-toggle-bidang="${b.id}" data-active="${
          b.is_active ? "1" : "0"
        }">${b.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
        </td>
      </tr>`
      )
      .join("");
  }

  function openBidangModal(row = null) {
    $("bidang-id").value = row ? row.id : "";
    $("bidang-modal-title").textContent = row ? "Edit Bidang" : "Bidang Baru";
    fillDivisionSelect($("bidang-division"), row?.division_id || divisionsCache[0]?.id || "");
    $("bidang-code").value = row?.code || "";
    $("bidang-name").value = row?.name || "";
    $("bidang-description").value = row?.description || "";
    $("bidang-active").checked = row ? Boolean(row.is_active) : true;
    fillLeaderSelect($("bidang-leader"), row?.leader_user_id ?? "");
    setStatus(bidangFormStatus, "");
    bidangModal.hidden = false;
  }

  function closeBidangModal() {
    bidangModal.hidden = true;
  }

  bidangForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $("bidang-id").value;
    const leaderVal = $("bidang-leader").value;
    const payload = {
      division_id: Number($("bidang-division").value),
      code: $("bidang-code").value.trim(),
      name: $("bidang-name").value.trim(),
      description: $("bidang-description").value.trim(),
      is_active: $("bidang-active").checked,
      leader_user_id: leaderVal ? Number(leaderVal) : null,
      clear_leader: !leaderVal,
    };
    try {
      if (id) {
        await api(`/api/bidang/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        delete payload.clear_leader;
        await api("/api/bidang", { method: "POST", body: JSON.stringify(payload) });
      }
      closeBidangModal();
      await loadBidang();
      await loadDivisions();
      await showNotice({ title: "Berhasil", message: "Bidang disimpan." });
    } catch (err) {
      setStatus(bidangFormStatus, err.message, "err");
    }
  });

  // —— Structure ——
  async function loadStructure() {
    const el = $("org-tree");
    if (!el) return;
    try {
      const tree = await api("/api/organization/tree");
      const divisions = tree.divisions || [];
      el.innerHTML =
        `<div class="org-tree-root">
          <h2>${escapeHtml(tree.organization_name || "Organisasi")}</h2>
          <p>${tree.stats?.divisions || 0} Divisi · ${tree.stats?.bidangs || 0} Bidang</p>
        </div>` +
        (divisions.length
          ? divisions
              .map((d) => {
                const bidangs = d.bidangs || [];
                return `<article class="org-division-card">
                  <header>
                    <div>
                      <h3>${escapeHtml(d.code)} — ${escapeHtml(d.name)} ${statusBadge(d.is_active)}</h3>
                      <p class="meta">Pemimpin: ${leaderLabel(d.leader)}</p>
                    </div>
                  </header>
                  ${
                    bidangs.length
                      ? `<ul class="org-bidang-list">${bidangs
                          .map(
                            (b) => `<li>
                              <strong>${escapeHtml(b.code)} — ${escapeHtml(b.name)}</strong>
                              <span class="meta">Pemimpin: ${leaderLabel(b.leader)} · ${
                              b.is_active ? "Aktif" : "Nonaktif"
                            }</span>
                            </li>`
                          )
                          .join("")}</ul>`
                      : `<p class="org-empty">Belum ada Bidang pada Divisi ini.</p>`
                  }
                </article>`;
              })
              .join("")
          : `<p class="org-empty">Struktur organisasi masih kosong.</p>`);
    } catch (err) {
      el.innerHTML = `<p class="org-empty" style="color:#dc2626">${escapeHtml(err.message)}</p>`;
    }
  }

  // Events
  btnNewDivision?.addEventListener("click", () => openDivisionModal());
  btnNewBidang?.addEventListener("click", async () => {
    if (!divisionsCache.length) await loadDivisions();
    if (!divisionsCache.length) {
      await showNotice({
        title: "Belum ada Divisi",
        message: "Buat Divisi terlebih dahulu sebelum menambah Bidang.",
      });
      return;
    }
    openBidangModal();
  });
  $("btn-close-division-modal")?.addEventListener("click", closeDivisionModal);
  $("btn-cancel-division")?.addEventListener("click", closeDivisionModal);
  $("btn-close-bidang-modal")?.addEventListener("click", closeBidangModal);
  $("btn-cancel-bidang")?.addEventListener("click", closeBidangModal);

  let debounce;
  const refreshDivisionsSoon = () => {
    clearTimeout(debounce);
    debounce = setTimeout(loadDivisions, 250);
  };
  divisionSearch?.addEventListener("input", refreshDivisionsSoon);
  divisionActiveFilter?.addEventListener("change", loadDivisions);

  const refreshBidangSoon = () => {
    clearTimeout(debounce);
    debounce = setTimeout(loadBidang, 250);
  };
  bidangSearch?.addEventListener("input", refreshBidangSoon);
  bidangDivisionFilter?.addEventListener("change", loadBidang);
  bidangActiveFilter?.addEventListener("change", loadBidang);

  document.addEventListener("click", async (e) => {
    const editDiv = e.target.closest("[data-edit-division]");
    if (editDiv) {
      const id = Number(editDiv.getAttribute("data-edit-division"));
      const row = divisionsCache.find((d) => d.id === id);
      if (row) openDivisionModal(row);
      return;
    }
    const toggleDiv = e.target.closest("[data-toggle-division]");
    if (toggleDiv) {
      const id = Number(toggleDiv.getAttribute("data-toggle-division"));
      const active = toggleDiv.getAttribute("data-active") === "1";
      const ok = await askConfirm({
        title: active ? "Nonaktifkan Divisi?" : "Aktifkan Divisi?",
        message: active
          ? "Bidang di dalamnya tidak dihapus. Bidang aktif tidak dapat ditambahkan ke Divisi nonaktif."
          : "Divisi akan ditandai aktif kembali.",
      });
      if (!ok) return;
      try {
        await api(`/api/divisions/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: !active }),
        });
        await loadDivisions();
        await loadBidang();
      } catch (err) {
        await showNotice({ title: "Gagal", message: err.message });
      }
      return;
    }
    const editBidang = e.target.closest("[data-edit-bidang]");
    if (editBidang) {
      const id = Number(editBidang.getAttribute("data-edit-bidang"));
      try {
        const row = await api(`/api/bidang/${id}`);
        openBidangModal(row);
      } catch (err) {
        await showNotice({ title: "Gagal", message: err.message });
      }
      return;
    }
    const toggleBidang = e.target.closest("[data-toggle-bidang]");
    if (toggleBidang) {
      const id = Number(toggleBidang.getAttribute("data-toggle-bidang"));
      const active = toggleBidang.getAttribute("data-active") === "1";
      const ok = await askConfirm({
        title: active ? "Nonaktifkan Bidang?" : "Aktifkan Bidang?",
        message: "Data pengguna dan project tidak dihapus.",
      });
      if (!ok) return;
      try {
        await api(`/api/bidang/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: !active }),
        });
        await loadBidang();
        await loadDivisions();
      } catch (err) {
        await showNotice({ title: "Gagal", message: err.message });
      }
    }
  });

  async function init() {
    await loadUsers();
    await loadDivisions();
    await loadBidang();
    activateTab((location.hash || "").replace("#", "") || "divisions");
  }

  init();
})();
