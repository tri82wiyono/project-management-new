(() => {
  const POLL_MS = 30000;
  const POLL_HIDDEN_MS = 120000;

  const menu = document.querySelector("[data-notif-menu]");
  if (!menu) return;

  const toggle = menu.querySelector("[data-notif-toggle]");
  const panel = menu.querySelector("[data-notif-panel]");
  const badge = menu.querySelector("[data-notif-badge]");
  const list = menu.querySelector("[data-notif-list]");
  const markAllBtn = menu.querySelector("[data-notif-mark-all]");

  let items = [];
  let unreadCount = 0;
  let loading = false;

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function hasRealPhoto(url) {
    const value = String(url || "").trim().toLowerCase();
    if (!value) return false;
    if (value.includes("dicebear.com")) return false;
    if (value.startsWith("data:image/svg")) return false;
    return true;
  }

  function initials(name) {
    return String(name || "?")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() || "")
      .join("");
  }

  function formatTime(value) {
    if (!value) return "";
    try {
      const d = new Date(value);
      const now = new Date();
      const sameDay = d.toDateString() === now.toDateString();
      if (sameDay) {
        return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
    } catch {
      return "";
    }
  }

  function setBadge(count) {
    unreadCount = Number(count) || 0;
    if (!badge) return;
    if (unreadCount <= 0) {
      badge.hidden = true;
      badge.textContent = "0";
      return;
    }
    badge.hidden = false;
    badge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
  }

  function renderList() {
    if (!list) return;
    if (!items.length) {
      list.innerHTML = `<div class="notif-empty">Belum ada mention untuk Anda.</div>`;
      return;
    }
    list.innerHTML = items
      .map((item) => {
        const avatar = hasRealPhoto(item.actor_avatar_url)
          ? `<img src="${escapeHtml(item.actor_avatar_url)}" alt="" />`
          : `<span class="notif-avatar-fallback">${escapeHtml(initials(item.actor_name))}</span>`;
        return `
          <a
            class="notif-item${!item.is_read ? " is-unread" : ""}"
            href="${escapeHtml(item.open_url)}"
            data-notif-id="${item.id}"
            data-notif-link
            role="menuitem"
          >
            ${avatar}
            <div class="notif-item-body">
              <div class="notif-item-title">
                <strong>${escapeHtml(item.actor_name)}</strong>
                <time>${escapeHtml(formatTime(item.created_at))}</time>
              </div>
              <div class="notif-item-meta">Mention di ${escapeHtml(item.project_name)}</div>
              <p class="notif-item-preview">${escapeHtml(item.body_preview || "(tanpa teks)")}</p>
            </div>
          </a>`;
      })
      .join("");
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      throw new Error(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
            : `Request failed (${res.status})`
      );
    }
    return data;
  }

  async function refresh({ silent = false } = {}) {
    if (loading) return;
    loading = true;
    try {
      const data = await api("/api/notifications/mentions?limit=30");
      items = Array.isArray(data.items) ? data.items : [];
      setBadge(data.unread_count || 0);
      if (!silent || !panel?.hidden) renderList();
    } catch (_) {
      if (!silent && list) {
        list.innerHTML = `<div class="notif-empty">Gagal memuat notifikasi.</div>`;
      }
    } finally {
      loading = false;
    }
  }

  async function markRead({ notificationId = null, markAll = false } = {}) {
    const payload = markAll
      ? { mark_all: true }
      : { notification_id: Number(notificationId) };
    const data = await api("/api/notifications/mentions/read", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    items = Array.isArray(data.items) ? data.items : items;
    setBadge(data.unread_count || 0);
    renderList();
  }

  function closePanel() {
    if (!panel || !toggle) return;
    panel.hidden = true;
    menu.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  }

  function openPanel() {
    document.querySelectorAll("[data-user-menu].open").forEach((other) => {
      other.classList.remove("open");
      const otherPanel = other.querySelector("[data-user-menu-panel]");
      const otherToggle = other.querySelector("[data-user-menu-toggle]");
      if (otherPanel) otherPanel.hidden = true;
      if (otherToggle) otherToggle.setAttribute("aria-expanded", "false");
    });
    panel.hidden = false;
    menu.classList.add("open");
    toggle.setAttribute("aria-expanded", "true");
    renderList();
    refresh({ silent: false });
  }

  toggle?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (panel.hidden) openPanel();
    else closePanel();
  });

  markAllBtn?.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await markRead({ markAll: true });
    } catch (_) {
      /* ignore */
    }
  });

  list?.addEventListener("click", async (e) => {
    const link = e.target.closest("[data-notif-link]");
    if (!link) return;
    const id = Number(link.dataset.notifId);
    if (!id) return;
    try {
      await markRead({ notificationId: id });
    } catch (_) {
      /* navigation still proceeds */
    }
  });

  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target)) closePanel();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanel();
  });

  let pollTimer = null;

  function schedulePoll() {
    if (pollTimer) window.clearInterval(pollTimer);
    const ms = document.visibilityState === "hidden" ? POLL_HIDDEN_MS : POLL_MS;
    pollTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      refresh({ silent: true });
    }, ms);
  }

  document.addEventListener("visibilitychange", () => {
    schedulePoll();
    if (document.visibilityState === "visible") refresh({ silent: true });
  });

  refresh({ silent: true });
  schedulePoll();
})();
