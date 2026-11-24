(() => {
  const page = document.getElementById("chat-page");
  if (!page) return;

  const REACTION_EMOJIS = ["👍", "❤️", "😄", "🎉", "✅", "👀", "🔥", "🙏"];
  const COMPOSER_EMOJIS = [...REACTION_EMOJIS, "😊", "👏", "💡", "⚠️", "📌", "🚀"];
  const POLL_MS = 12000;

  const state = {
    currentUserId: Number(page.dataset.userId || 0),
    canManage: page.dataset.canManage === "1",
    threads: [],
    users: [],
    query: "",
    activeProjectId: null,
    messages: [],
    replyTo: null,
    pendingFiles: [],
    mentionIds: new Set(),
    mentionQuery: "",
    mentionOpen: false,
    mentionIndex: 0,
    emojiOpen: false,
    reactionPickerFor: null,
    sending: false,
    pollTimer: null,
  };

  const els = {
    list: document.getElementById("chat-list"),
    summary: document.getElementById("chat-summary"),
    search: document.getElementById("chat-search"),
    refresh: document.getElementById("chat-refresh"),
    roomEmpty: document.getElementById("chat-room-empty"),
    roomActive: document.getElementById("chat-room-active"),
    roomHead: document.getElementById("chat-room-head"),
    feed: document.getElementById("chat-feed"),
    composer: document.getElementById("chat-composer"),
  };

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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

  function hasPhoto(url) {
    const value = String(url || "").trim().toLowerCase();
    if (!value) return false;
    if (value.includes("dicebear.com")) return false;
    if (value.startsWith("data:image/svg")) return false;
    return true;
  }

  function avatarHtml(user) {
    const name = user?.name || "User";
    if (hasPhoto(user?.avatar_url)) {
      return `<img class="pw-msg-avatar" src="${escapeHtml(user.avatar_url)}" alt="${escapeHtml(name)}" />`;
    }
    return `<span class="pw-msg-avatar-fallback" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
  }

  function formatTime(value) {
    if (!value) return "";
    try {
      const d = new Date(value);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
    } catch {
      return "";
    }
  }

  function formatMsgTime(value) {
    if (!value) return "";
    try {
      const d = new Date(value);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleString("id-ID", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function formatBytes(n) {
    const size = Number(n) || 0;
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function linkifyAndMentions(text, mentions = []) {
    let html = escapeHtml(text || "");
    html = html.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>'
    );
    const names = [...mentions]
      .map((m) => m.name)
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
    for (const name of names) {
      const pattern = new RegExp(`@${escapeRegExp(name)}\\b`, "gi");
      html = html.replace(pattern, `<span class="pw-mention">@${escapeHtml(name)}</span>`);
    }
    return html;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (res.status === 204) return null;
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

  function activeThread() {
    return state.threads.find((t) => t.project_id === state.activeProjectId) || null;
  }

  function renderThreadList() {
    if (!els.list) return;
    const unreadThreads = state.threads.filter((t) => t.unread_mentions > 0).length;
    if (els.summary) {
      els.summary.textContent = unreadThreads
        ? `${state.threads.length} chat · ${unreadThreads} belum dibaca`
        : `${state.threads.length} riwayat chat`;
    }

    if (!state.threads.length) {
      els.list.innerHTML = `<div class="chat-empty">${
        state.query
          ? "Tidak ada chat yang cocok."
          : "Belum ada project chat yang dapat diakses."
      }</div>`;
      return;
    }

    els.list.innerHTML = state.threads
      .map((item) => {
        const preview = item.last_author_name
          ? `<em>${escapeHtml(item.last_author_name)}:</em> ${escapeHtml(item.last_message_preview)}`
          : escapeHtml(item.last_message_preview || "Belum ada pesan.");
        const active = item.project_id === state.activeProjectId ? " is-active" : "";
        const unread = item.unread_mentions > 0 ? " is-unread" : "";
        return `
          <button type="button" class="chat-item${active}${unread}" data-open-thread="${item.project_id}">
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
                  : ""
              }
            </div>
          </button>`;
      })
      .join("");
  }

  function renderMessage(msg) {
    const canDelete =
      !msg.is_deleted &&
      (msg.author?.id === state.currentUserId || state.canManage);
    const files = (msg.attachments || [])
      .map((att) => {
        if (att.kind === "image") {
          return `<a href="${escapeHtml(att.url)}" target="_blank" rel="noopener"><img class="pw-msg-image" src="${escapeHtml(att.url)}" alt="${escapeHtml(att.original_name)}" /></a>`;
        }
        return `<a class="pw-msg-file" href="${escapeHtml(att.url)}" target="_blank" rel="noopener">📎 ${escapeHtml(att.original_name)} · ${escapeHtml(formatBytes(att.size_bytes))}</a>`;
      })
      .join("");
    const reactions = (msg.reactions || [])
      .map(
        (r) => `
      <button type="button" class="pw-reaction${r.reacted_by_me ? " is-mine" : ""}" data-react="${msg.id}:${escapeHtml(r.emoji)}">
        ${escapeHtml(r.emoji)} ${r.count}
      </button>`
      )
      .join("");

    return `
      <article class="pw-msg" data-msg-id="${msg.id}">
        ${avatarHtml(msg.author)}
        <div class="pw-msg-bubble">
          <div class="pw-msg-top">
            <span class="pw-msg-name">${escapeHtml(msg.author?.name || "Pengguna")}</span>
            <span class="pw-msg-role">${escapeHtml(msg.author?.role || "")}</span>
            <span class="pw-msg-time">${escapeHtml(formatMsgTime(msg.created_at))}</span>
          </div>
          ${
            msg.parent
              ? `<div class="pw-msg-reply"><strong>${escapeHtml(msg.parent.author_name)}</strong>${escapeHtml(msg.parent.body_preview || "")}</div>`
              : ""
          }
          ${
            msg.is_deleted
              ? `<p class="pw-msg-deleted">Pesan dihapus</p>`
              : `<p class="pw-msg-body">${linkifyAndMentions(msg.body, msg.mentions)}</p>`
          }
          ${files ? `<div class="pw-msg-files">${files}</div>` : ""}
          ${
            msg.is_deleted
              ? ""
              : `<div class="pw-msg-actions">
                  <div class="pw-reactions">${reactions}</div>
                  <button type="button" data-reply="${msg.id}">Balas</button>
                  <button type="button" data-open-react="${msg.id}">Reaksi</button>
                  ${canDelete ? `<button type="button" data-delete-msg="${msg.id}">Hapus</button>` : ""}
                </div>`
          }
        </div>
      </article>`;
  }

  function availableMentions(query = "") {
    const q = query.trim().toLowerCase();
    return state.users
      .filter((u) => u.id !== state.currentUserId)
      .filter((u) => {
        if (!q) return true;
        return (
          String(u.name || "").toLowerCase().includes(q) ||
          String(u.role || "").toLowerCase().includes(q)
        );
      })
      .slice(0, 8);
  }

  function renderComposer() {
    if (!els.composer) return;
    const reply = state.replyTo;
    const mentionUsers = availableMentions(state.mentionQuery);
    els.composer.innerHTML = `
      <p class="pw-error" id="chat-error" hidden></p>
      ${
        reply
          ? `<div class="pw-reply-bar">
              <div>Membalas <strong>${escapeHtml(reply.author?.name || "")}</strong></div>
              <button type="button" id="chat-cancel-reply" aria-label="Batalkan balasan">×</button>
            </div>`
          : ""
      }
      <div class="pw-composer-wrap">
        <div class="pw-composer-box">
          <textarea
            id="chat-composer-input"
            class="pw-composer-input"
            placeholder="Tulis pesan, @mention, atau lampirkan file…"
            maxlength="8000"
          ></textarea>
          ${
            state.pendingFiles.length
              ? `<div class="pw-pending-files">${state.pendingFiles
                  .map(
                    (f, idx) => `
                <span class="pw-pending-file">
                  ${escapeHtml(f.name)}
                  <button type="button" data-remove-pending="${idx}">×</button>
                </span>`
                  )
                  .join("")}</div>`
              : ""
          }
          <div class="pw-composer-toolbar">
            <div class="pw-composer-tools">
              <button type="button" class="pw-tool-btn" id="chat-btn-emoji" title="Emoji">😊</button>
              <button type="button" class="pw-tool-btn" id="chat-btn-mention" title="Mention">@</button>
              <button type="button" class="pw-tool-btn" id="chat-btn-attach" title="Lampirkan">📎</button>
              <input type="file" id="chat-file-input" multiple hidden accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.zip" />
            </div>
            <button type="button" class="pw-send-btn" id="chat-btn-send">Kirim</button>
          </div>
        </div>
        ${
          state.emojiOpen
            ? `<div class="pw-popover" id="chat-emoji-popover" style="bottom:74px;left:8px">
                <div class="pw-emoji-grid">
                  ${COMPOSER_EMOJIS.map((e) => `<button type="button" data-insert-emoji="${e}">${e}</button>`).join("")}
                </div>
              </div>`
            : ""
        }
        ${
          state.mentionOpen
            ? `<div class="pw-popover" id="chat-mention-popover" style="bottom:74px;left:40px">
                <div class="pw-mention-list">
                  ${
                    mentionUsers.length
                      ? mentionUsers
                          .map(
                            (u, idx) => `
                        <button type="button" class="pw-mention-item${idx === state.mentionIndex ? " active" : ""}" data-mention-id="${u.id}">
                          ${avatarHtml(u)}
                          <span><strong>${escapeHtml(u.name)}</strong><small>${escapeHtml(u.role || "")}</small></span>
                        </button>`
                          )
                          .join("")
                      : `<div class="pw-empty" style="padding:10px">Tidak ada user</div>`
                  }
                </div>
              </div>`
            : ""
        }
        ${
          state.reactionPickerFor
            ? `<div class="pw-popover" id="chat-react-popover" style="bottom:auto;top:30%;right:16px">
                <div class="pw-emoji-grid">
                  ${REACTION_EMOJIS.map(
                    (e) =>
                      `<button type="button" data-pick-react="${state.reactionPickerFor}:${e}">${e}</button>`
                  ).join("")}
                </div>
              </div>`
            : ""
        }
      </div>
    `;
    wireComposerEvents();
  }

  function renderRoom() {
    const thread = activeThread();
    if (!thread) {
      els.roomEmpty.hidden = false;
      els.roomActive.hidden = true;
      return;
    }
    els.roomEmpty.hidden = true;
    els.roomActive.hidden = false;
    els.roomHead.innerHTML = `
      <div class="chat-room-head-main">
        <div class="chat-avatar" style="background:${escapeHtml(thread.project_color || "#4F7CFF")}">
          ${escapeHtml(initials(thread.project_name))}
        </div>
        <div class="chat-room-head-text">
          <h3>${escapeHtml(thread.project_name)}</h3>
          <p>${thread.message_count || state.messages.length} pesan · ${escapeHtml(thread.project_status || "")}</p>
        </div>
      </div>
      <a class="btn btn-ghost btn-sm" href="/projects/${thread.project_id}">Buka Project</a>
    `;
    els.feed.innerHTML = state.messages.length
      ? state.messages.map(renderMessage).join("")
      : `<div class="pw-empty">Belum ada pesan. Mulai percakapan di sini.</div>`;
    renderComposer();
    wireFeedEvents();
    scrollFeedBottom(false);
  }

  function showError(message) {
    const el = document.getElementById("chat-error");
    if (!el) return;
    el.hidden = !message;
    el.textContent = message || "";
  }

  function scrollFeedBottom(smooth = true) {
    if (!els.feed) return;
    els.feed.scrollTo({
      top: els.feed.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }

  function preserveComposerValue() {
    return document.getElementById("chat-composer-input")?.value || "";
  }

  function restoreComposerValue(value) {
    const input = document.getElementById("chat-composer-input");
    if (!input) return;
    input.value = value || "";
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  }

  function refreshRoomUi(keepText = true) {
    const draft = keepText ? preserveComposerValue() : "";
    renderRoom();
    if (keepText) restoreComposerValue(draft);
  }

  function insertAtCursor(text) {
    const input = document.getElementById("chat-composer-input");
    if (!input) return;
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const value = input.value || "";
    input.value = `${value.slice(0, start)}${text}${value.slice(end)}`;
    const pos = start + text.length;
    input.focus();
    input.setSelectionRange(pos, pos);
  }

  function insertMention(user) {
    const input = document.getElementById("chat-composer-input");
    if (!input || !user) return;
    const value = input.value || "";
    const caret = input.selectionStart || value.length;
    const before = value.slice(0, caret);
    const after = value.slice(caret);
    const atMatch = before.match(/@([^\s@]*)$/);
    const nextBefore = atMatch ? before.slice(0, atMatch.index) : before;
    const mentionText = `@${user.name} `;
    input.value = `${nextBefore}${mentionText}${after}`;
    state.mentionIds.add(user.id);
    state.mentionOpen = false;
    state.mentionQuery = "";
    refreshRoomUi(true);
    restoreComposerValue(input.value);
  }

  async function loadThreads({ silent = false } = {}) {
    const params = new URLSearchParams({ limit: "100" });
    if (state.query) params.set("q", state.query);
    const data = await api(`/api/chat/threads?${params.toString()}`);
    state.threads = Array.isArray(data.items) ? data.items : [];
    renderThreadList();
    if (!silent && state.activeProjectId && !activeThread() && state.threads.length) {
      // keep selection if still present
    }
  }

  async function loadMessages(projectId, { silent = false } = {}) {
    const data = await api(`/api/projects/${projectId}/discussion?limit=120`);
    const items = Array.isArray(data.items) ? data.items : [];
    const prevLast = state.messages[state.messages.length - 1]?.id;
    const nextLast = items[items.length - 1]?.id;
    const changed =
      nextLast !== prevLast || items.length !== (state.messages || []).length;
    state.messages = items;
    if (!silent || changed) {
      refreshRoomUi(true);
      if (changed) scrollFeedBottom(false);
    }
  }

  async function markThreadRead(projectId) {
    const thread = state.threads.find((t) => t.project_id === projectId);
    if (!thread?.unread_mentions) return;
    try {
      // Mark any unread mentions for messages currently loaded
      for (const msg of state.messages) {
        const mentioned = (msg.mentions || []).some((m) => m.id === state.currentUserId);
        if (mentioned) {
          await api("/api/notifications/mentions/read", {
            method: "POST",
            body: JSON.stringify({ message_id: msg.id }),
          });
        }
      }
      thread.unread_mentions = 0;
      renderThreadList();
    } catch (_) {
      /* ignore */
    }
  }

  async function openThread(projectId, { updateUrl = true } = {}) {
    state.activeProjectId = Number(projectId) || null;
    state.replyTo = null;
    state.pendingFiles = [];
    state.mentionIds = new Set();
    state.emojiOpen = false;
    state.mentionOpen = false;
    state.reactionPickerFor = null;
    renderThreadList();
    if (!state.activeProjectId) {
      renderRoom();
      return;
    }
    try {
      await loadMessages(state.activeProjectId);
      await markThreadRead(state.activeProjectId);
      if (updateUrl) {
        const url = new URL(window.location.href);
        url.searchParams.set("project_id", String(state.activeProjectId));
        window.history.replaceState({}, "", url.toString());
      }
    } catch (err) {
      if (els.feed) {
        els.feed.innerHTML = `<div class="pw-empty">${escapeHtml(err.message || "Gagal memuat chat.")}</div>`;
      }
    }
  }

  async function sendMessage() {
    if (!state.activeProjectId || state.sending) return;
    const input = document.getElementById("chat-composer-input");
    const body = (input?.value || "").trim();
    if (!body && !state.pendingFiles.length) {
      showError("Tulis pesan atau lampirkan file terlebih dahulu.");
      return;
    }
    showError("");
    state.sending = true;
    const sendBtn = document.getElementById("chat-btn-send");
    if (sendBtn) sendBtn.disabled = true;
    try {
      const form = new FormData();
      form.append("body", body);
      if (state.replyTo?.id) form.append("parent_id", String(state.replyTo.id));
      form.append("mention_ids", JSON.stringify([...state.mentionIds]));
      for (const file of state.pendingFiles) form.append("files", file, file.name);
      const res = await fetch(`/api/projects/${state.activeProjectId}/discussion`, {
        method: "POST",
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : `Gagal mengirim (${res.status})`
        );
      }
      state.messages.push(data);
      state.replyTo = null;
      state.pendingFiles = [];
      state.mentionIds = new Set();
      state.emojiOpen = false;
      state.mentionOpen = false;
      state.reactionPickerFor = null;
      refreshRoomUi(false);
      scrollFeedBottom(true);
      await loadThreads({ silent: true });
      renderThreadList();
    } catch (err) {
      showError(err.message || "Gagal mengirim pesan.");
    } finally {
      state.sending = false;
      const btn = document.getElementById("chat-btn-send");
      if (btn) btn.disabled = false;
    }
  }

  async function toggleReaction(messageId, emoji) {
    try {
      const updated = await api(
        `/api/projects/${state.activeProjectId}/discussion/${messageId}/reactions`,
        { method: "POST", body: JSON.stringify({ emoji }) }
      );
      const idx = state.messages.findIndex((m) => m.id === messageId);
      if (idx >= 0) state.messages[idx] = updated;
      state.reactionPickerFor = null;
      refreshRoomUi(true);
    } catch (err) {
      showError(err.message || "Gagal menambah reaksi.");
    }
  }

  async function deleteMessage(messageId) {
    if (!window.confirm("Hapus pesan ini?")) return;
    try {
      const updated = await api(
        `/api/projects/${state.activeProjectId}/discussion/${messageId}`,
        { method: "DELETE" }
      );
      const idx = state.messages.findIndex((m) => m.id === messageId);
      if (idx >= 0) state.messages[idx] = updated;
      refreshRoomUi(true);
    } catch (err) {
      showError(err.message || "Gagal menghapus pesan.");
    }
  }

  function wireFeedEvents() {
    els.feed?.querySelectorAll("[data-reply]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.reply);
        state.replyTo = state.messages.find((m) => m.id === id) || null;
        state.reactionPickerFor = null;
        refreshRoomUi(true);
      });
    });
    els.feed?.querySelectorAll("[data-open-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.openReact);
        state.reactionPickerFor = state.reactionPickerFor === id ? null : id;
        state.emojiOpen = false;
        state.mentionOpen = false;
        refreshRoomUi(true);
      });
    });
    els.feed?.querySelectorAll("[data-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [id, emoji] = String(btn.dataset.react || "").split(":");
        if (id && emoji) toggleReaction(Number(id), emoji);
      });
    });
    els.feed?.querySelectorAll("[data-delete-msg]").forEach((btn) => {
      btn.addEventListener("click", () => deleteMessage(Number(btn.dataset.deleteMsg)));
    });
  }

  function updateMentionPopover() {
    const pop = document.getElementById("chat-mention-popover");
    if (!pop) {
      refreshRoomUi(true);
      return;
    }
    const mentionUsers = availableMentions(state.mentionQuery);
    pop.innerHTML = `<div class="pw-mention-list">${
      mentionUsers.length
        ? mentionUsers
            .map(
              (u, idx) => `
          <button type="button" class="pw-mention-item${idx === state.mentionIndex ? " active" : ""}" data-mention-id="${u.id}">
            ${avatarHtml(u)}
            <span><strong>${escapeHtml(u.name)}</strong><small>${escapeHtml(u.role || "")}</small></span>
          </button>`
            )
            .join("")
        : `<div class="pw-empty" style="padding:10px">Tidak ada user</div>`
    }</div>`;
    pop.querySelectorAll("[data-mention-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const user = state.users.find((u) => u.id === Number(btn.dataset.mentionId));
        if (user) insertMention(user);
      });
    });
  }

  function wireComposerEvents() {
    document.getElementById("chat-btn-send")?.addEventListener("click", () => sendMessage());
    document.getElementById("chat-cancel-reply")?.addEventListener("click", () => {
      state.replyTo = null;
      refreshRoomUi(true);
    });
    document.getElementById("chat-btn-emoji")?.addEventListener("click", () => {
      state.emojiOpen = !state.emojiOpen;
      state.mentionOpen = false;
      state.reactionPickerFor = null;
      refreshRoomUi(true);
    });
    document.getElementById("chat-btn-mention")?.addEventListener("click", () => {
      state.mentionOpen = !state.mentionOpen;
      state.emojiOpen = false;
      state.reactionPickerFor = null;
      state.mentionQuery = "";
      state.mentionIndex = 0;
      refreshRoomUi(true);
      insertAtCursor("@");
    });
    document.getElementById("chat-btn-attach")?.addEventListener("click", () => {
      document.getElementById("chat-file-input")?.click();
    });
    document.getElementById("chat-file-input")?.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      const room = 5 - state.pendingFiles.length;
      state.pendingFiles.push(...files.slice(0, Math.max(0, room)));
      e.target.value = "";
      refreshRoomUi(true);
    });
    document.querySelectorAll("[data-remove-pending]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.removePending);
        state.pendingFiles = state.pendingFiles.filter((_, i) => i !== idx);
        refreshRoomUi(true);
      });
    });
    document.querySelectorAll("[data-insert-emoji]").forEach((btn) => {
      btn.addEventListener("click", () => {
        insertAtCursor(btn.dataset.insertEmoji || "");
        state.emojiOpen = false;
        refreshRoomUi(true);
      });
    });
    document.querySelectorAll("[data-mention-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const user = state.users.find((u) => u.id === Number(btn.dataset.mentionId));
        if (user) insertMention(user);
      });
    });
    document.querySelectorAll("[data-pick-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [id, emoji] = String(btn.dataset.pickReact || "").split(":");
        if (id && emoji) toggleReaction(Number(id), emoji);
      });
    });

    const input = document.getElementById("chat-composer-input");
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        if (state.mentionOpen) {
          e.preventDefault();
          const picks = availableMentions(state.mentionQuery);
          const pick = picks[state.mentionIndex] || picks[0];
          if (pick) insertMention(pick);
          return;
        }
        e.preventDefault();
        sendMessage();
      }
      if (state.mentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const picks = availableMentions(state.mentionQuery);
        if (!picks.length) return;
        state.mentionIndex =
          e.key === "ArrowDown"
            ? (state.mentionIndex + 1) % picks.length
            : (state.mentionIndex - 1 + picks.length) % picks.length;
        refreshRoomUi(true);
      }
      if (e.key === "Escape") {
        state.mentionOpen = false;
        state.emojiOpen = false;
        state.reactionPickerFor = null;
        refreshRoomUi(true);
      }
    });
    input?.addEventListener("input", () => {
      const value = input.value || "";
      const caret = input.selectionStart || 0;
      const before = value.slice(0, caret);
      const match = before.match(/@([^\s@]*)$/);
      if (match) {
        const wasOpen = state.mentionOpen;
        state.mentionOpen = true;
        state.mentionQuery = match[1] || "";
        state.mentionIndex = 0;
        state.emojiOpen = false;
        if (!wasOpen) refreshRoomUi(true);
        else updateMentionPopover();
      } else if (state.mentionOpen) {
        state.mentionOpen = false;
        document.getElementById("chat-mention-popover")?.remove();
      }
    });
  }

  function wireListEvents() {
    els.list?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-open-thread]");
      if (!btn) return;
      openThread(Number(btn.dataset.openThread));
    });
  }

  function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(async () => {
      try {
        await loadThreads({ silent: true });
        if (state.activeProjectId) {
          await loadMessages(state.activeProjectId, { silent: true });
        }
      } catch (_) {
        /* ignore */
      }
    }, POLL_MS);
  }

  async function boot() {
    wireListEvents();
    els.refresh?.addEventListener("click", async () => {
      await loadThreads();
      if (state.activeProjectId) await loadMessages(state.activeProjectId);
    });
    let searchTimer = null;
    els.search?.addEventListener("input", () => {
      state.query = (els.search.value || "").trim();
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadThreads(), 250);
    });

    try {
      const [threads, users] = await Promise.all([
        api("/api/chat/threads?limit=100"),
        api("/api/team?active_only=true"),
      ]);
      state.threads = Array.isArray(threads.items) ? threads.items : [];
      state.users = Array.isArray(users) ? users : users.items || [];
      renderThreadList();

      const params = new URLSearchParams(window.location.search);
      const fromQuery = Number(params.get("project_id") || 0);
      const focusMsg = Number(params.get("focus_msg") || 0);
      const notifId = Number(params.get("notif") || 0);
      const initial =
        fromQuery ||
        state.threads.find((t) => t.unread_mentions > 0)?.project_id ||
        state.threads[0]?.project_id ||
        null;
      if (initial) {
        await openThread(initial, { updateUrl: Boolean(fromQuery) });
        if (focusMsg) {
          const node = document.querySelector(`[data-msg-id="${focusMsg}"]`);
          if (node) {
            node.classList.add("is-focused");
            node.scrollIntoView({ behavior: "smooth", block: "center" });
            window.setTimeout(() => node.classList.remove("is-focused"), 4000);
          }
          try {
            if (notifId) {
              await api("/api/notifications/mentions/read", {
                method: "POST",
                body: JSON.stringify({ notification_id: notifId }),
              });
            } else {
              await api("/api/notifications/mentions/read", {
                method: "POST",
                body: JSON.stringify({ message_id: focusMsg }),
              });
            }
          } catch (_) {
            /* ignore */
          }
        }
      } else renderRoom();
      startPolling();
    } catch (err) {
      if (els.list) {
        els.list.innerHTML = `<div class="chat-empty">${escapeHtml(err.message || "Gagal memuat chat.")}</div>`;
      }
    }
  }

  boot();
})();
