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
    backlog: "Backlog",
    dev: "Dev",
    sit: "SIT",
    uat: "UAT",
    to: "TO",
    izin: "Izin",
    release: "Release",
  };

  const DEVELOPED_BY_LABEL = {
    internal: "Internal Bank",
    vendor: "Pihak Ketiga (Vendor)",
    blanket_mandays: "Blanket Mandays",
  };

  const TASK_STATUS_LABEL = {
    todo: "To Do",
    in_progress: "In Progress",
    review: "Review",
    done: "Done",
  };

  const REACTION_EMOJIS = ["👍", "❤️", "😄", "🎉", "✅", "👀", "🔥", "🙏"];
  const COMPOSER_EMOJIS = [...REACTION_EMOJIS, "😊", "👏", "💡", "⚠️", "📌", "🚀"];
  const POLL_MS = 12000;

  const page = document.getElementById("project-detail-page");
  const state = {
    projectId: Number(page?.dataset.projectId || 0),
    currentUserId: Number(page?.dataset.userId || 0),
    canManage: page?.dataset.canManage === "1",
    project: null,
    tasks: [],
    notes: [],
    users: [],
    messages: [],
    replyTo: null,
    pendingFiles: [],
    mentionIds: new Set(),
    mentionQuery: "",
    mentionOpen: false,
    mentionIndex: 0,
    emojiOpen: false,
    reactionPickerFor: null,
    pollTimer: null,
    sending: false,
  };

  const els = {
    root: document.getElementById("project-detail-root"),
    pageTitle: document.getElementById("detail-page-title"),
    pageSubtitle: document.getElementById("detail-page-subtitle"),
    btnEdit: document.getElementById("btn-edit-project"),
    btnTasks: document.getElementById("btn-open-tasks"),
  };

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function stripHtml(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = String(html || "");
    return (tmp.textContent || tmp.innerText || "").trim();
  }

  function formatBudgetId(value) {
    if (value == null || value === "") return "—";
    const digits = String(value).replace(/\D/g, "");
    if (!digits) return "—";
    return `Rp ${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const d = new Date(`${value}T00:00:00`);
    return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
  }

  function formatNoteTime(value) {
    if (!value) return "";
    try {
      return new Date(value).toLocaleString("id-ID", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function formatMsgTime(value) {
    if (!value) return "";
    try {
      const d = new Date(value);
      const now = new Date();
      const sameDay = d.toDateString() === now.toDateString();
      if (sameDay) {
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

  function hasPhoto(url) {
    return Boolean(String(url || "").trim());
  }

  function initials(name) {
    return String(name || "?")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() || "")
      .join("");
  }

  function avatarHtml(user, sizeClass = "") {
    const name = user?.name || "User";
    const url = user?.avatar_url;
    if (hasPhoto(url)) {
      return `<img class="pw-msg-avatar ${sizeClass}" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" />`;
    }
    return `<span class="pw-msg-avatar-fallback ${sizeClass}" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
  }

  function picIcon(title = "") {
    return `
      <span class="pic-avatar pic-avatar-icon" title="${escapeHtml(title)}" role="img" aria-label="${escapeHtml(title || "PIC")}">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 12a4.5 4.5 0 1 0-4.5-4.5A4.5 4.5 0 0 0 12 12Zm0 2.25c-3.6 0-6.75 1.8-6.75 4.05V20h13.5v-1.7c0-2.25-3.15-4.05-6.75-4.05Z"/>
        </svg>
      </span>`;
  }

  function picPeople(project) {
    return (project.members || []).map((m) => m.user).filter(Boolean);
  }

  function renderPicStack(project) {
    const people = picPeople(project);
    const label = people.map((u) => u.name).join(", ") || project.pic || "Tidak ada PIC";
    if (!people.length) {
      return `<div class="pic-avatar-stack" title="${escapeHtml(label)}">${picIcon(label)}</div>
        <div class="detail-pic-names">${escapeHtml(label)}</div>`;
    }
    const shown = people.slice(0, 6);
    const extra = people.length - shown.length;
    return `
      <div class="pic-avatar-stack" title="${escapeHtml(label)}">
        ${shown
          .map((u) =>
            hasPhoto(u.avatar_url)
              ? `<img class="pic-avatar" src="${escapeHtml(u.avatar_url)}" alt="${escapeHtml(u.name)}" title="${escapeHtml(u.name)}" />`
              : picIcon(u.name)
          )
          .join("")}
        ${extra > 0 ? `<span class="pic-avatar-extra">+${extra}</span>` : ""}
      </div>
      <div class="detail-pic-names">${escapeHtml(label)}</div>`;
  }

  function ownershipLabel(project) {
    if (project.owner_type === "bidang") {
      return project.owner_bidang_name
        ? `Bidang · ${project.owner_bidang_name}`
        : "Bidang";
    }
    if (project.owner_type === "division") {
      return project.owner_division_name
        ? `Divisi · ${project.owner_division_name}`
        : "Divisi";
    }
    return "Belum diklasifikasi";
  }

  function taskCounts(tasks) {
    const counts = { todo: 0, in_progress: 0, review: 0, done: 0 };
    for (const t of tasks) {
      if (counts[t.status] != null) counts[t.status] += 1;
    }
    return counts;
  }

  function renderDescriptionBlock(description) {
    const raw = String(description || "").trim();
    if (!raw) return `<div class="pw-desc pw-empty" style="padding:8px 0;text-align:left">Belum ada deskripsi.</div>`;
    if (/<[a-z][\s\S]*>/i.test(raw)) {
      return `<div class="pw-desc">${raw}</div>`;
    }
    return `<div class="pw-desc">${escapeHtml(raw)}</div>`;
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
      html = html.replace(
        pattern,
        `<span class="pw-mention">@${escapeHtml(name)}</span>`
      );
    }
    return html;
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function formatBytes(n) {
    const size = Number(n) || 0;
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
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
      <button type="button" class="pw-reaction${r.reacted_by_me ? " is-mine" : ""}" data-react="${msg.id}:${escapeHtml(r.emoji)}" title="${r.count} reaksi">
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

  function renderDiscussionPanel() {
    const reply = state.replyTo;
    const mentionUsers = availableMentions(state.mentionQuery);
    return `
      <aside class="pw-discussion" id="pw-discussion">
        <div class="pw-discussion-head">
          <div>
            <h3>Project Discussion</h3>
            <p>Ruang komunikasi pihak berwenang pada project ini</p>
          </div>
          <span class="pw-discussion-count">${state.messages.length}</span>
        </div>
        <div class="pw-discussion-feed" id="pw-discussion-feed">
          ${
            state.messages.length
              ? state.messages.map(renderMessage).join("")
              : `<div class="pw-empty">Belum ada diskusi. Mulai percakapan pertama untuk project ini.</div>`
          }
        </div>
        <div class="pw-composer" id="pw-composer">
          <p class="pw-error" id="pw-discussion-error" hidden></p>
          ${
            reply
              ? `<div class="pw-reply-bar">
                  <div>Membalas <strong>${escapeHtml(reply.author?.name || "")}</strong></div>
                  <button type="button" id="pw-cancel-reply" aria-label="Batalkan balasan">×</button>
                </div>`
              : ""
          }
          <div class="pw-composer-wrap">
            <div class="pw-composer-box">
              <textarea
                id="pw-composer-input"
                class="pw-composer-input"
                placeholder="Tulis update, pertanyaan, atau @sebutkan rekan…"
                maxlength="8000"
              ></textarea>
              ${
                state.pendingFiles.length
                  ? `<div class="pw-pending-files">${state.pendingFiles
                      .map(
                        (f, idx) => `
                    <span class="pw-pending-file">
                      ${escapeHtml(f.name)}
                      <button type="button" data-remove-pending="${idx}" aria-label="Hapus file">×</button>
                    </span>`
                      )
                      .join("")}</div>`
                  : ""
              }
              <div class="pw-composer-toolbar">
                <div class="pw-composer-tools">
                  <button type="button" class="pw-tool-btn" id="pw-btn-emoji" title="Emoji">😊</button>
                  <button type="button" class="pw-tool-btn" id="pw-btn-mention" title="Mention">@</button>
                  <button type="button" class="pw-tool-btn" id="pw-btn-attach" title="Lampirkan">📎</button>
                  <input type="file" id="pw-file-input" multiple hidden accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.zip" />
                </div>
                <button type="button" class="pw-send-btn" id="pw-btn-send">Kirim</button>
              </div>
            </div>
            ${
              state.emojiOpen
                ? `<div class="pw-popover" id="pw-emoji-popover" style="bottom:74px;left:8px">
                    <div class="pw-emoji-grid">
                      ${COMPOSER_EMOJIS.map((e) => `<button type="button" data-insert-emoji="${e}">${e}</button>`).join("")}
                    </div>
                  </div>`
                : ""
            }
            ${
              state.mentionOpen
                ? `<div class="pw-popover" id="pw-mention-popover" style="bottom:74px;left:40px">
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
                ? `<div class="pw-popover" id="pw-react-popover" style="bottom:auto;top:40%;right:16px">
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
        </div>
      </aside>`;
  }

  function renderWorkspace() {
    const p = state.project;
    if (!p) {
      els.root.innerHTML = `
        <div class="details-empty">
          <div class="details-empty-icon">!</div>
          Project tidak ditemukan.
        </div>`;
      return;
    }

    const pct = Math.round(p.progress || 0);
    const counts = taskCounts(state.tasks);
    const related = state.tasks.slice(0, 10);
    const color = p.color || "#4F7CFF";

    els.pageTitle.textContent = p.name;
    els.pageSubtitle.textContent =
      stripHtml(p.description) || "Collaborative Project Workspace";
    els.btnEdit.hidden = false;
    els.btnTasks.href = `/tasks?project_id=${p.id}`;

    els.root.innerHTML = `
      <div class="pw-workspace">
        <section class="pw-header">
          <div class="pw-header-top">
            <div class="pw-header-main">
              <div class="project-card-icon lg" style="background:${escapeHtml(color)}20;color:${escapeHtml(color)}">▣</div>
              <div class="pw-header-text">
                <h2>${escapeHtml(p.name)}</h2>
                <div class="pw-header-meta">
                  <span class="status-badge ${escapeHtml(p.status)}">${STATUS_LABEL[p.status] || p.status}</span>
                  <span class="pw-meta-chip">PIC <strong>${escapeHtml(p.pic || "—")}</strong></span>
                  <span class="pw-meta-chip">Target <strong>${formatDate(p.end_date)}</strong></span>
                  <span class="pw-meta-chip">Mulai <strong>${formatDate(p.start_date)}</strong></span>
                </div>
              </div>
            </div>
            <div class="pw-header-actions">
              <button type="button" class="btn btn-ghost btn-sm" id="btn-edit-inline">Edit</button>
              <a class="btn btn-primary btn-sm" href="/tasks?project_id=${p.id}">Open Tasks</a>
              <a class="btn btn-ghost btn-sm" href="/timeline">Timeline</a>
            </div>
          </div>
          <div class="pw-progress-row">
            <div class="pw-progress-track"><span style="width:${Math.min(100, Math.max(0, pct))}%;background:${escapeHtml(color)}"></span></div>
            <div class="pw-progress-pct">${pct}%</div>
          </div>
        </section>

        <div class="pw-body">
          <div class="pw-info">
            <section class="pw-panel">
              <div class="pw-panel-head"><h3>Overview</h3></div>
              <div class="pw-overview-grid">
                <div class="pw-overview-item"><span>PIC</span>${renderPicStack(p)}</div>
                <div class="pw-overview-item"><span>Kepemilikan</span><strong>${escapeHtml(ownershipLabel(p))}</strong></div>
                <div class="pw-overview-item"><span>Dikembangkan oleh</span><strong>${escapeHtml(DEVELOPED_BY_LABEL[p.developed_by] || p.developed_by || "—")}</strong></div>
                <div class="pw-overview-item"><span>Anggaran</span><strong>${escapeHtml(formatBudgetId(p.budget))}</strong></div>
                <div class="pw-overview-item"><span>Tasks</span><strong>${Number(p.task_count || state.tasks.length || 0)}</strong></div>
                <div class="pw-overview-item"><span>Status</span><strong>${STATUS_LABEL[p.status] || p.status}</strong></div>
              </div>
              ${renderDescriptionBlock(p.description)}
              ${
                Array.isArray(p.documents) && p.documents.length
                  ? `<div class="pw-docs"><span>Dokumen</span><ul>${p.documents
                      .map(
                        (d) =>
                          `<li><a href="${escapeHtml(d.open_url || d.download_url || d.external_url || "#")}" target="_blank" rel="noopener">${escapeHtml(d.original_name)}${d.kind === "url" ? " ↗" : ""}</a></li>`
                      )
                      .join("")}</ul></div>`
                  : ""
              }
            </section>

            <section class="pw-panel">
              <div class="pw-panel-head"><h3>Task breakdown</h3></div>
              <div class="pw-breakdown">
                ${Object.entries(TASK_STATUS_LABEL)
                  .map(
                    ([key, label]) => `
                  <div class="pw-breakdown-item">
                    <span>${label}</span>
                    <strong>${counts[key] || 0}</strong>
                  </div>`
                  )
                  .join("")}
              </div>
            </section>

            <section class="pw-panel">
              <div class="pw-panel-head">
                <h3>Related tasks</h3>
                <a href="/tasks?project_id=${p.id}">Lihat semua →</a>
              </div>
              ${
                related.length
                  ? `<ul class="pw-task-list">${related
                      .map(
                        (t) => `
                    <li>
                      <div>
                        <strong>${escapeHtml(t.title)}</strong>
                        <small>${escapeHtml(t.category || "General")}${t.due_date ? ` · due ${formatDate(t.due_date)}` : ""}${
                          t.notes_count > 0 ? ` · ${t.notes_count} catatan` : ""
                        }</small>
                      </div>
                      <span class="pw-task-status">${TASK_STATUS_LABEL[t.status] || t.status}</span>
                    </li>`
                      )
                      .join("")}</ul>`
                  : `<div class="pw-empty">Belum ada task untuk project ini.</div>`
              }
            </section>

            <section class="pw-panel">
              <div class="pw-panel-head">
                <h3>Catatan / Problem</h3>
                <span class="project-notes-count">${state.notes.length}</span>
              </div>
              ${
                state.notes.length
                  ? `<div class="pw-notes-list">${state.notes
                      .map(
                        (note) => `
                    <article class="pw-note kind-${escapeHtml(note.kind || "problem")}">
                      <div class="pw-note-meta">
                        <span class="pw-note-kind">${note.kind === "note" ? "Catatan" : "Problem"}</span>
                        <a href="/tasks?project_id=${p.id}">${escapeHtml(note.task_title || `Task #${note.task_id}`)}</a>
                        <span>${escapeHtml(formatNoteTime(note.created_at))}</span>
                      </div>
                      <p>${escapeHtml(note.body)}</p>
                    </article>`
                      )
                      .join("")}</div>`
                  : `<div class="pw-empty">Belum ada catatan pada task di project ini.</div>`
              }
            </section>
          </div>

          ${renderDiscussionPanel()}
        </div>
      </div>
    `;

    document.getElementById("btn-edit-inline")?.addEventListener("click", () => {
      window.location.href = `/projects/${p.id}/edit`;
    });
    wireDiscussionEvents();
    scrollDiscussionToBottom(false);
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

  function showDiscussionError(message) {
    const el = document.getElementById("pw-discussion-error");
    if (!el) return;
    el.hidden = !message;
    el.textContent = message || "";
  }

  function scrollDiscussionToBottom(smooth = true) {
    const feed = document.getElementById("pw-discussion-feed");
    if (!feed) return;
    feed.scrollTo({
      top: feed.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }

  function preserveComposerValue() {
    return document.getElementById("pw-composer-input")?.value || "";
  }

  function restoreComposerValue(value) {
    const input = document.getElementById("pw-composer-input");
    if (!input) return;
    input.value = value || "";
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  }

  function refreshDiscussionUi(keepText = true) {
    const draft = keepText ? preserveComposerValue() : "";
    const feed = document.getElementById("pw-discussion-feed");
    const nearBottom = feed
      ? feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80
      : true;
    renderWorkspace();
    if (keepText) restoreComposerValue(draft);
    if (nearBottom) scrollDiscussionToBottom(false);
  }

  function insertAtCursor(text) {
    const input = document.getElementById("pw-composer-input");
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
    const input = document.getElementById("pw-composer-input");
    if (!input || !user) return;
    const value = input.value || "";
    const caret = input.selectionStart || value.length;
    const before = value.slice(0, caret);
    const after = value.slice(caret);
    const atMatch = before.match(/@([^\s@]*)$/);
    const nextBefore = atMatch ? before.slice(0, atMatch.index) : before;
    const mentionText = `@${user.name} `;
    input.value = `${nextBefore}${mentionText}${after}`;
    const pos = (nextBefore + mentionText).length;
    state.mentionIds.add(user.id);
    state.mentionOpen = false;
    state.mentionQuery = "";
    refreshDiscussionUi(true);
    restoreComposerValue(input.value);
    const restored = document.getElementById("pw-composer-input");
    if (restored) {
      restored.focus();
      restored.setSelectionRange(pos, pos);
    }
  }

  async function loadDiscussion({ silent = false } = {}) {
    const data = await api(`/api/projects/${state.projectId}/discussion?limit=80`);
    const items = Array.isArray(data.items) ? data.items : [];
    const prevLast = state.messages[state.messages.length - 1]?.id;
    const nextLast = items[items.length - 1]?.id;
    state.messages = items;
    if (!silent) {
      refreshDiscussionUi(true);
    } else if (nextLast && nextLast !== prevLast) {
      refreshDiscussionUi(true);
    } else {
      // still update reaction counts without full redraw if lengths match
      const feed = document.getElementById("pw-discussion-feed");
      if (feed && items.length) {
        // light update via full refresh when count changes
        if (items.length !== feed.querySelectorAll(".pw-msg").length) {
          refreshDiscussionUi(true);
        }
      }
    }
  }

  async function sendMessage() {
    if (state.sending) return;
    const input = document.getElementById("pw-composer-input");
    const body = (input?.value || "").trim();
    if (!body && !state.pendingFiles.length) {
      showDiscussionError("Tulis pesan atau lampirkan file terlebih dahulu.");
      return;
    }
    showDiscussionError("");
    state.sending = true;
    const sendBtn = document.getElementById("pw-btn-send");
    if (sendBtn) sendBtn.disabled = true;
    try {
      const form = new FormData();
      form.append("body", body);
      if (state.replyTo?.id) form.append("parent_id", String(state.replyTo.id));
      form.append("mention_ids", JSON.stringify([...state.mentionIds]));
      for (const file of state.pendingFiles) form.append("files", file, file.name);
      const res = await fetch(`/api/projects/${state.projectId}/discussion`, {
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
      refreshDiscussionUi(false);
      scrollDiscussionToBottom(true);
    } catch (err) {
      showDiscussionError(err.message || "Gagal mengirim pesan.");
    } finally {
      state.sending = false;
      const btn = document.getElementById("pw-btn-send");
      if (btn) btn.disabled = false;
    }
  }

  async function toggleReaction(messageId, emoji) {
    try {
      const updated = await api(`/api/projects/${state.projectId}/discussion/${messageId}/reactions`, {
        method: "POST",
        body: JSON.stringify({ emoji }),
      });
      const idx = state.messages.findIndex((m) => m.id === messageId);
      if (idx >= 0) state.messages[idx] = updated;
      state.reactionPickerFor = null;
      refreshDiscussionUi(true);
    } catch (err) {
      showDiscussionError(err.message || "Gagal menambah reaksi.");
    }
  }

  async function deleteMessage(messageId) {
    const ok = window.confirm("Hapus pesan ini dari diskusi project?");
    if (!ok) return;
    try {
      const updated = await api(`/api/projects/${state.projectId}/discussion/${messageId}`, {
        method: "DELETE",
      });
      const idx = state.messages.findIndex((m) => m.id === messageId);
      if (idx >= 0) state.messages[idx] = updated;
      refreshDiscussionUi(true);
    } catch (err) {
      showDiscussionError(err.message || "Gagal menghapus pesan.");
    }
  }

  function wireDiscussionEvents() {
    const input = document.getElementById("pw-composer-input");
    document.getElementById("pw-btn-send")?.addEventListener("click", () => sendMessage());
    document.getElementById("pw-cancel-reply")?.addEventListener("click", () => {
      state.replyTo = null;
      refreshDiscussionUi(true);
    });
    document.getElementById("pw-btn-emoji")?.addEventListener("click", () => {
      state.emojiOpen = !state.emojiOpen;
      state.mentionOpen = false;
      state.reactionPickerFor = null;
      refreshDiscussionUi(true);
    });
    document.getElementById("pw-btn-mention")?.addEventListener("click", () => {
      state.mentionOpen = !state.mentionOpen;
      state.emojiOpen = false;
      state.reactionPickerFor = null;
      state.mentionQuery = "";
      state.mentionIndex = 0;
      refreshDiscussionUi(true);
      insertAtCursor("@");
    });
    document.getElementById("pw-btn-attach")?.addEventListener("click", () => {
      document.getElementById("pw-file-input")?.click();
    });
    document.getElementById("pw-file-input")?.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      const room = 5 - state.pendingFiles.length;
      state.pendingFiles.push(...files.slice(0, Math.max(0, room)));
      e.target.value = "";
      refreshDiscussionUi(true);
    });

    document.querySelectorAll("[data-remove-pending]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.removePending);
        state.pendingFiles = state.pendingFiles.filter((_, i) => i !== idx);
        refreshDiscussionUi(true);
      });
    });

    document.querySelectorAll("[data-insert-emoji]").forEach((btn) => {
      btn.addEventListener("click", () => {
        insertAtCursor(btn.dataset.insertEmoji || "");
        state.emojiOpen = false;
        refreshDiscussionUi(true);
      });
    });

    document.querySelectorAll("[data-mention-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const user = state.users.find((u) => u.id === Number(btn.dataset.mentionId));
        if (user) insertMention(user);
      });
    });

    document.querySelectorAll("[data-reply]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.reply);
        state.replyTo = state.messages.find((m) => m.id === id) || null;
        state.reactionPickerFor = null;
        refreshDiscussionUi(true);
      });
    });

    document.querySelectorAll("[data-open-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.openReact);
        state.reactionPickerFor = state.reactionPickerFor === id ? null : id;
        state.emojiOpen = false;
        state.mentionOpen = false;
        refreshDiscussionUi(true);
      });
    });

    document.querySelectorAll("[data-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [id, emoji] = String(btn.dataset.react || "").split(":");
        if (id && emoji) toggleReaction(Number(id), emoji);
      });
    });

    document.querySelectorAll("[data-pick-react]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [id, emoji] = String(btn.dataset.pickReact || "").split(":");
        if (id && emoji) toggleReaction(Number(id), emoji);
      });
    });

    document.querySelectorAll("[data-delete-msg]").forEach((btn) => {
      btn.addEventListener("click", () => deleteMessage(Number(btn.dataset.deleteMsg)));
    });

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
        return;
      }
      if (state.mentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const picks = availableMentions(state.mentionQuery);
        if (!picks.length) return;
        state.mentionIndex =
          e.key === "ArrowDown"
            ? (state.mentionIndex + 1) % picks.length
            : (state.mentionIndex - 1 + picks.length) % picks.length;
        refreshDiscussionUi(true);
      }
      if (e.key === "Escape") {
        state.mentionOpen = false;
        state.emojiOpen = false;
        state.reactionPickerFor = null;
        refreshDiscussionUi(true);
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
        if (!wasOpen) {
          refreshDiscussionUi(true);
        } else {
          updateMentionPopover();
        }
      } else if (state.mentionOpen) {
        state.mentionOpen = false;
        document.getElementById("pw-mention-popover")?.remove();
      }
    });
  }

  function updateMentionPopover() {
    const pop = document.getElementById("pw-mention-popover");
    if (!pop) {
      refreshDiscussionUi(true);
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

  function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
      loadDiscussion({ silent: true }).catch(() => {});
    }, POLL_MS);
  }

  function wireHeaderEvents() {
    els.btnEdit?.addEventListener("click", () => {
      if (state.projectId) window.location.href = `/projects/${state.projectId}/edit`;
    });
  }

  async function focusMessageFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const focusId = Number(params.get("focus_msg") || 0);
    const notifId = Number(params.get("notif") || 0);
    if (!focusId) return;

    const node = document.querySelector(`[data-msg-id="${focusId}"]`);
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
          body: JSON.stringify({ message_id: focusId }),
        });
      }
    } catch (_) {
      /* ignore mark-read failure */
    }

    params.delete("focus_msg");
    params.delete("notif");
    const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}${window.location.hash || ""}`;
    window.history.replaceState({}, "", next);
  }

  async function boot() {
    wireHeaderEvents();
    if (!state.projectId) {
      els.root.innerHTML = `<div class="details-empty"><div class="details-empty-icon">!</div>Project ID tidak valid.</div>`;
      return;
    }
    try {
      const [project, tasks, notes, users, discussion] = await Promise.all([
        api(`/api/projects/${state.projectId}`),
        api(`/api/tasks?project_id=${state.projectId}`),
        api(`/api/projects/${state.projectId}/notes`),
        api("/api/team?active_only=true"),
        api(`/api/projects/${state.projectId}/discussion?limit=80`),
      ]);
      state.project = project;
      state.tasks = Array.isArray(tasks) ? tasks : [];
      state.notes = Array.isArray(notes) ? notes : [];
      state.users = Array.isArray(users) ? users : users.items || [];
      state.messages = Array.isArray(discussion.items) ? discussion.items : [];
      renderWorkspace();
      startPolling();
      await focusMessageFromQuery();
    } catch (err) {
      els.root.innerHTML = `
        <div class="details-empty">
          <div class="details-empty-icon">!</div>
          Gagal memuat workspace: ${escapeHtml(err.message)}
          <div style="margin-top:12px"><a class="btn btn-ghost btn-sm" href="/projects">Kembali ke Projects</a></div>
        </div>`;
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
