(() => {
  const els = {
    list: document.getElementById("chat-list"),
    summary: document.getElementById("chat-summary"),
    search: document.getElementById("chat-search"),
    refresh: document.getElementById("chat-refresh"),
  };

  let timer = null;
  let query = "";

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function initials(name) {
    const parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!parts.length) return "P";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
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

  async function api(path) {
    const res = await fetch(path);
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

  function render(items, meta = {}) {
    if (!els.list) return;
    const unreadThreads = Number(meta.unread_threads || 0);
    const total = Number(meta.total || items.length || 0);
    if (els.summary) {
      els.summary.textContent = unreadThreads
        ? `${total} chat · ${unreadThreads} belum dibaca`
        : `${total} chat project`;
    }

    if (!items.length) {
      els.list.innerHTML = `<div class="chat-empty">${
        query
          ? "Tidak ada chat yang cocok dengan pencarian."
          : "Belum ada project chat yang dapat diakses."
      }</div>`;
      return;
    }

    els.list.innerHTML = items
      .map((item) => {
        const preview = item.last_author_name
          ? `<em>${escapeHtml(item.last_author_name)}:</em> ${escapeHtml(item.last_message_preview)}`
          : escapeHtml(item.last_message_preview || "Belum ada pesan.");
        return `
          <a class="chat-item${item.unread_mentions > 0 ? " is-unread" : ""}" href="${escapeHtml(item.open_url)}">
            <div class="chat-avatar" style="background:${escapeHtml(item.project_color || "#4F7CFF")}">
              ${escapeHtml(initials(item.project_name))}
            </div>
            <div class="chat-item-main">
              <div class="chat-item-top">
                <strong>${escapeHtml(item.project_name)}</strong>
                <span class="chat-item-time">${escapeHtml(formatTime(item.last_message_at))}</span>
              </div>
              <p class="chat-item-preview">${preview}</p>
            </div>
            <div class="chat-item-side">
              ${
                item.unread_mentions > 0
                  ? `<span class="chat-unread">${item.unread_mentions > 99 ? "99+" : item.unread_mentions}</span>`
                  : `<span class="chat-status">${escapeHtml(item.project_status || "")}</span>`
              }
            </div>
          </a>`;
      })
      .join("");
  }

  async function load() {
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (query) params.set("q", query);
      const data = await api(`/api/chat/threads?${params.toString()}`);
      render(Array.isArray(data.items) ? data.items : [], data);
    } catch (err) {
      if (els.list) {
        els.list.innerHTML = `<div class="chat-empty">${escapeHtml(err.message || "Gagal memuat chat.")}</div>`;
      }
      if (els.summary) els.summary.textContent = "Gagal memuat";
    }
  }

  els.search?.addEventListener("input", () => {
    query = (els.search.value || "").trim();
    if (timer) clearTimeout(timer);
    timer = setTimeout(load, 250);
  });
  els.refresh?.addEventListener("click", () => load());

  load();
  window.setInterval(load, 20000);
})();
