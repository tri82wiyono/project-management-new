(() => {
  const $ = (id) => document.getElementById(id);

  const statsEl = $("audit-stats");
  const tbody = $("audit-tbody");
  const searchEl = $("audit-search");
  const categoryEl = $("audit-category");
  const successEl = $("audit-success");
  const actionEl = $("audit-action");
  const statusEl = $("audit-status");
  const pagerEl = $("audit-pager");
  const pageLabel = $("audit-page-label");
  const btnPrev = $("btn-audit-prev");
  const btnNext = $("btn-audit-next");
  const btnRefresh = $("btn-audit-refresh");

  let page = 1;
  let pages = 1;
  let debounceTimer = null;

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function setStatus(message, kind) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("err", kind === "err");
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
        second: "2-digit",
      });
    } catch {
      return "—";
    }
  }

  function renderStats(data) {
    if (!statsEl) return;
    const cards = [
      { label: "Login berhasil", value: data.login_success || 0, cls: "is-ok" },
      { label: "Login gagal", value: data.login_failed || 0, cls: "is-err" },
      { label: "Email password terkirim", value: data.password_email_sent || 0, cls: "is-ok" },
      { label: "Email password gagal", value: data.password_email_failed || 0, cls: "is-err" },
    ];
    statsEl.innerHTML = cards
      .map(
        (c) => `
      <div class="audit-stat ${c.cls}">
        <span>${escapeHtml(c.label)}</span>
        <strong>${escapeHtml(c.value)}</strong>
      </div>`
      )
      .join("");
  }

  function targetCell(item) {
    const name = item.target_name || "—";
    const email = item.target_email || "";
    return `<strong>${escapeHtml(name)}</strong>${
      email ? `<small>${escapeHtml(email)}</small>` : ""
    }`;
  }

  function actorCell(item) {
    if (!item.actor_email && !item.actor_name) return "<small>—</small>";
    return `<strong>${escapeHtml(item.actor_name || "—")}</strong>${
      item.actor_email ? `<small>${escapeHtml(item.actor_email)}</small>` : ""
    }`;
  }

  function renderRows(items) {
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="audit-empty">Belum ada log untuk filter ini.</td></tr>`;
      return;
    }
    tbody.innerHTML = items
      .map((item) => {
        const ok = Boolean(item.success);
        return `
        <tr>
          <td>${escapeHtml(fmtDate(item.created_at))}</td>
          <td><span class="audit-badge action">${escapeHtml(item.action_label || item.action)}</span></td>
          <td><span class="audit-badge ${ok ? "ok" : "err"}">${ok ? "Berhasil" : "Gagal"}</span></td>
          <td>${targetCell(item)}</td>
          <td>${actorCell(item)}</td>
          <td><small>${escapeHtml(item.ip_address || "—")}</small></td>
          <td><small>${escapeHtml(item.message || "—")}</small></td>
        </tr>`;
      })
      .join("");
  }

  function queryParams() {
    const params = new URLSearchParams();
    const q = (searchEl.value || "").trim();
    const category = categoryEl.value;
    const success = successEl.value;
    const action = actionEl.value;
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (success !== "") params.set("success", success);
    if (action) params.set("action", action);
    params.set("page", String(page));
    params.set("page_size", "50");
    return params;
  }

  async function loadSummary() {
    const res = await fetch("/api/audit/summary");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (res.status === 403) {
      setStatus("Anda tidak punya izin melihat Log Audit (audit.view).", "err");
      return;
    }
    if (!res.ok) throw new Error(await res.text());
    renderStats(await res.json());
  }

  async function loadLogs() {
    setStatus("Memuat log…");
    tbody.innerHTML = `<tr><td colspan="7" class="audit-empty">Memuat log…</td></tr>`;
    const res = await fetch(`/api/audit/logs?${queryParams().toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (res.status === 403) {
      tbody.innerHTML = `<tr><td colspan="7" class="audit-empty">Akses ditolak. Butuh permission audit.view.</td></tr>`;
      setStatus("Anda tidak punya izin melihat Log Audit.", "err");
      pagerEl.hidden = true;
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Gagal memuat log");

    renderRows(data.items || []);
    page = data.page || 1;
    pages = data.pages || 1;
    pageLabel.textContent = `Halaman ${page} / ${pages} · ${data.total || 0} entri`;
    pagerEl.hidden = (data.total || 0) <= 0;
    btnPrev.disabled = page <= 1;
    btnNext.disabled = page >= pages;
    setStatus("");
  }

  async function refreshAll() {
    try {
      await Promise.all([loadSummary(), loadLogs()]);
    } catch (err) {
      setStatus(err.message || "Gagal memuat audit", "err");
    }
  }

  function scheduleReload() {
    page = 1;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      refreshAll();
    }, 250);
  }

  searchEl.addEventListener("input", scheduleReload);
  categoryEl.addEventListener("change", scheduleReload);
  successEl.addEventListener("change", scheduleReload);
  actionEl.addEventListener("change", scheduleReload);
  btnRefresh.addEventListener("click", () => refreshAll());
  btnPrev.addEventListener("click", () => {
    if (page > 1) {
      page -= 1;
      loadLogs().catch((err) => setStatus(err.message || "Gagal memuat", "err"));
    }
  });
  btnNext.addEventListener("click", () => {
    if (page < pages) {
      page += 1;
      loadLogs().catch((err) => setStatus(err.message || "Gagal memuat", "err"));
    }
  });

  refreshAll();
})();
