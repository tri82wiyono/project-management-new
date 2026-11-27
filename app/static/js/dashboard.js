const api = (path) => fetch(path).then((r) => {
  if (!r.ok) throw new Error(`Request failed: ${path}`);
  return r.json();
});

const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const shortMonths = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const weekdays = ["Su","Mo","Tu","We","Th","Fr","Sa"];
const DEADLINE_TONES = ["tone-amber", "tone-green", "tone-violet", "tone-blue"];

let analyticsChart;

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^(https?:|data:image\/|\/)/i.test(raw) && !/^(javascript:|vbscript:)/i.test(raw)) {
    return raw;
  }
  return "";
}

function greetingText() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning!";
  if (hour < 18) return "Good afternoon!";
  return "Good evening!";
}

function formatDate(value) {
  const d = new Date(value);
  return `${shortMonths[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

function tagClass(category = "") {
  return category.toLowerCase().replace(/[^a-z]/g, "");
}

function toneFor(key = "") {
  let hash = 0;
  for (let i = 0; i < String(key).length; i += 1) hash = (hash + key.charCodeAt(i) * (i + 1)) % DEADLINE_TONES.length;
  return DEADLINE_TONES[hash];
}

function setGreeting() {
  const el = document.getElementById("greeting-title");
  if (el) el.textContent = greetingText();
}

function formatGrowth(value, suffix = "%") {
  const n = Number(value || 0);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n}${suffix} vs. last period`;
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

function animateCount(el, target, { suffix = "", duration = 700 } = {}) {
  if (!el) return;
  const end = Number(target);
  if (!Number.isFinite(end) || prefersReducedMotion()) {
    el.textContent = `${target}${suffix}`;
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3;
    el.textContent = `${Math.round(end * eased)}${suffix}`;
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

const CLASSIFICATION_META = {
  business_support: {
    icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3.5" y="8" width="17" height="12" rx="2"/><path d="M9 8V6.5A2.5 2.5 0 0 1 11.5 4h1A2.5 2.5 0 0 1 15 6.5V8" stroke-linecap="round"/><path d="M3.5 13h17" stroke-linecap="round"/></svg>`,
  },
  supporting: {
    icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6" stroke-linecap="round"/></svg>`,
  },
  security: {
    icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3.5l7 3v5.2c0 4.2-2.8 7.4-7 8.8-4.2-1.4-7-4.6-7-8.8V6.5l7-3Z"/><path d="M9.2 12.1l1.8 1.8 3.8-3.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  },
  compliance: {
    icon: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 4.5h8a2 2 0 0 1 2 2v13l-2.2-1.4L13.6 19 11.4 18.1 9.2 19 7 17.6V6.5a2 2 0 0 1 1-2Z"/><path d="M9.5 9.5h5M9.5 12.5h5M9.5 15.5h3" stroke-linecap="round"/></svg>`,
  },
};

function renderClassificationOverview(data) {
  const grid = document.getElementById("classification-overview-grid");
  if (!grid) return;
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    grid.innerHTML = `<div class="muted">Belum ada data klasifikasi.</div>`;
    return;
  }
  grid.innerHTML = items
    .map((item, index) => {
      const key = item.key || "";
      const meta = CLASSIFICATION_META[key] || CLASSIFICATION_META.business_support;
      const tasks = item.tasks || {};
      const todo = Number(tasks.todo || 0);
      const inProgress = Number(tasks.in_progress || 0);
      const review = Number(tasks.review || 0);
      const done = Number(tasks.done || 0);
      const totalTasks = Number(tasks.total || todo + inProgress + review + done);
      const projectCount = Number(item.project_count || 0);
      const pct = (n) => (totalTasks ? Math.round((n / totalTasks) * 100) : 0);
      const donePct = pct(done);
      const empty = projectCount === 0 && totalTasks === 0;
      const statuses = [
        { key: "todo", label: "To Do", value: todo },
        { key: "progress", label: "In Progress", value: inProgress },
        { key: "review", label: "Review", value: review },
        { key: "done", label: "Done", value: done },
      ];
      return `
        <article class="classification-card${empty ? " is-empty" : ""}" data-class="${escapeHtml(key)}" style="--reveal-delay:${index * 55}ms">
          <div class="classification-card-top">
            <span class="classification-icon" aria-hidden="true">${meta.icon}</span>
            <div class="classification-card-copy">
              <div class="classification-title-row">
                <h3>${escapeHtml(item.label || key)}</h3>
                <span class="classification-project-pill">${projectCount} project</span>
              </div>
              <p>${escapeHtml(item.description || "")}</p>
            </div>
          </div>

          <div class="classification-hero">
            <div class="classification-hero-main">
              <strong>${totalTasks}</strong>
              <span>total task</span>
            </div>
            <div class="classification-hero-side">
              <strong>${donePct}%</strong>
              <span>selesai</span>
            </div>
          </div>

          <div class="classification-stack" aria-hidden="true" title="Komposisi status task">
            <span class="is-todo" style="flex:${Math.max(todo, 0)}"></span>
            <span class="is-progress" style="flex:${Math.max(inProgress, 0)}"></span>
            <span class="is-review" style="flex:${Math.max(review, 0)}"></span>
            <span class="is-done" style="flex:${Math.max(done, 0)}"></span>
          </div>

          <div class="classification-status-chips">
            ${statuses
              .map(
                (s) => `
              <div class="classification-chip" data-status="${s.key}">
                <span>${s.label}</span>
                <strong>${s.value}</strong>
              </div>`
              )
              .join("")}
          </div>
        </article>`;
    })
    .join("");
}

function renderKPI(data) {
  const cards = [
    { label: "Total Projects", value: data.total_projects, growth: formatGrowth(data.total_projects_growth), icon: "▣", tone: "violet", down: data.total_projects_growth < 0, numeric: data.total_projects, suffix: "" },
    { label: "Completed Tasks", value: data.completed_tasks, growth: formatGrowth(data.completed_tasks_growth), icon: "✓", tone: "green", down: data.completed_tasks_growth < 0, numeric: data.completed_tasks, suffix: "" },
    { label: "In Progress", value: data.in_progress, growth: formatGrowth(data.in_progress_growth), icon: "⏱", tone: "amber", down: data.in_progress_growth < 0, numeric: data.in_progress, suffix: "" },
    { label: "On-Time Delivery", value: `${data.on_time_delivery}%`, growth: formatGrowth(data.on_time_delivery_growth, " pp"), icon: "◎", tone: "blue", down: data.on_time_delivery_growth < 0, numeric: data.on_time_delivery, suffix: "%" },
  ];
  document.getElementById("kpi-grid").innerHTML = cards.map((c) => `
    <article class="kpi-card">
      <div class="kpi-top">
        <div>
          <p class="kpi-label">${c.label}</p>
          <p class="kpi-value" data-kpi-num="${Number(c.numeric)}" data-kpi-suffix="${c.suffix}">0${c.suffix}</p>
        </div>
        <div class="kpi-icon ${c.tone}">${c.icon}</div>
      </div>
      <span class="kpi-growth${c.down ? " down" : ""}">${c.growth}</span>
    </article>
  `).join("");
  requestAnimationFrame(() => {
    document.querySelectorAll("#kpi-grid .kpi-value[data-kpi-num]").forEach((el, i) => {
      setTimeout(() => {
        animateCount(el, el.dataset.kpiNum, { suffix: el.dataset.kpiSuffix || "", duration: 720 });
      }, 60 + i * 50);
    });
  });
}

function formatSprintDate(value) {
  if (!value) return "—";
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return `${d.getDate()} ${shortMonths[d.getMonth()]} ${d.getFullYear()}`;
}

function sprintDueLabel(item) {
  const days = Number(item.days_left);
  if (item.overdue || days < 0) return `Terlambat ${Math.abs(days)} hari`;
  if (days === 0) return "Jatuh tempo hari ini";
  return `${days} hari lagi`;
}

function renderSprintOverview(data) {
  const projects = Array.isArray(data?.projects_with_sprints) ? data.projects_with_sprints : [];
  const dueSoon = Array.isArray(data?.due_soon) ? data.due_soon : [];
  const completed = Array.isArray(data?.completed) ? data.completed : [];
  const total = Number(data?.total_sprints || 0);
  const windowDays = Number(data?.due_soon_window_days || 14);

  const sub = document.getElementById("sprint-overview-sub");
  const projectCount = document.getElementById("sprint-project-count");
  const dueCount = document.getElementById("sprint-due-count");
  const doneCount = document.getElementById("sprint-done-count");
  const projectList = document.getElementById("sprint-project-list");
  const dueList = document.getElementById("sprint-due-list");
  const doneList = document.getElementById("sprint-done-list");
  if (!projectList || !dueList || !doneList) return;

  if (sub) {
    sub.textContent = total
      ? `${total} sprint di ${projects.length} project · selesai ${completed.length} · SLA ≤ ${windowDays} hari`
      : "Belum ada sprint pada project yang terlihat";
  }
  if (projectCount) projectCount.textContent = String(projects.length);
  if (dueCount) dueCount.textContent = String(dueSoon.length);
  if (doneCount) doneCount.textContent = String(completed.length);

  projectList.innerHTML = projects.length
    ? projects
        .map((p) => `
        <a class="sprint-overview-item" href="/sprints?project_id=${p.project_id}">
          <div class="sprint-overview-item-main">
            <strong>${escapeHtml(p.project_name)}</strong>
            <span>${p.active_sprint_name ? `Aktif: ${escapeHtml(p.active_sprint_name)}` : "Belum ada sprint aktif"}</span>
          </div>
          <span class="sprint-overview-pill">${Number(p.sprint_count || 0)} sprint</span>
        </a>`)
        .join("")
    : `<div class="sprint-overview-empty">Belum ada project dengan sprint.</div>`;

  dueList.innerHTML = dueSoon.length
    ? dueSoon
        .map((item) => {
          const modules = Array.isArray(item.modules) ? item.modules : [];
          const moduleHtml = modules.length
            ? `<ul class="sprint-overview-modules">${modules
                .map((m) => `<li>${escapeHtml(m.title)}</li>`)
                .join("")}</ul>`
            : `<p class="sprint-overview-modules-empty">Semua modul selesai / belum ada modul</p>`;
          return `
          <a class="sprint-overview-item ${item.overdue ? "is-overdue" : "is-soon"}" href="/sprints?project_id=${item.project_id}">
            <div class="sprint-overview-item-main">
              <strong>${escapeHtml(item.project_name)} · ${escapeHtml(item.sprint_name)}</strong>
              <span>SLA ${formatSprintDate(item.end_date)} · ${sprintDueLabel(item)}</span>
              ${moduleHtml}
            </div>
            <span class="sprint-overview-pill">${item.overdue ? "Overdue" : "Due soon"}</span>
          </a>`;
        })
        .join("")
    : `<div class="sprint-overview-empty">Tidak ada sprint jatuh tempo dalam ${windowDays} hari.</div>`;

  doneList.innerHTML = completed.length
    ? completed
        .map((item) => `
        <a class="sprint-overview-item is-done" href="/sprints?project_id=${item.project_id}">
          <div class="sprint-overview-item-main">
            <strong>${escapeHtml(item.project_name)} · ${escapeHtml(item.sprint_name)}</strong>
            <span>Selesai ${formatSprintDate(item.end_date)} · ${Number(item.done_count || 0)}/${Number(item.task_count || 0)} modul</span>
          </div>
          <span class="sprint-overview-pill">Selesai</span>
        </a>`)
        .join("")
    : `<div class="sprint-overview-empty">Belum ada sprint yang diselesaikan.</div>`;
}

function renderOverdueAlert(data) {
  const root = document.getElementById("overdue-alert");
  const countEl = document.getElementById("overdue-alert-count");
  const heading = document.getElementById("overdue-alert-heading");
  const sub = document.getElementById("overdue-alert-sub");
  const preview = document.getElementById("overdue-alert-preview");
  if (!root) return;

  const count = Number(data?.count || 0);
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!count) {
    root.hidden = true;
    if (preview) {
      preview.hidden = true;
      preview.textContent = "";
    }
    return;
  }

  root.hidden = false;
  if (countEl) countEl.textContent = String(count);
  if (heading) {
    heading.textContent = count === 1
      ? "1 pekerjaan terlambat"
      : `${count} pekerjaan terlambat`;
  }
  if (sub) {
    sub.textContent = "Sudah melewati due date dan belum selesai.";
  }

  if (preview) {
    const names = items.slice(0, 3).map((item) => item.title).filter(Boolean);
    if (names.length) {
      const more = count > names.length ? ` · +${count - names.length} lainnya` : "";
      preview.hidden = false;
      preview.textContent = `Teratas: ${names.join(" · ")}${more}`;
      preview.title = items.map((i) => i.title).filter(Boolean).join(", ");
    } else {
      preview.hidden = true;
      preview.textContent = "";
    }
  }
}

function renderProgress(items) {
  const root = document.getElementById("progress-list");
  if (!items.length) {
    root.innerHTML = `<div class="muted">No active projects yet</div>`;
    return;
  }
  root.innerHTML = items.map((p) => `
    <div class="progress-item">
      <div class="progress-meta">
        <strong>${escapeHtml(p.name)}</strong>
        <span>${Math.round(p.progress)}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" data-width="${p.progress}" style="background:${escapeHtml(p.color || "#1F5FD6")}"></div>
      </div>
    </div>
  `).join("");
  requestAnimationFrame(() => {
    root.querySelectorAll(".progress-fill").forEach((el) => {
      el.style.width = `${el.dataset.width}%`;
    });
  });
}

const KANBAN_STATUS_COLORS = {
  todo: {
    accent: "#7b8ea3",
    bg: "#f7f9fc",
    border: "#e6ebf2",
    head: "#5b6b7c",
    headBg: "#eef2f7",
    chip: "rgba(123,142,163,.14)",
  },
  in_progress: {
    accent: "#5b86e5",
    bg: "#f6f9ff",
    border: "#e0eaff",
    head: "#3d63b8",
    headBg: "#ebf2ff",
    chip: "rgba(91,134,229,.14)",
  },
  review: {
    accent: "#d4a017",
    bg: "#fffdf6",
    border: "#f3e6c0",
    head: "#9a6b00",
    headBg: "#fff6de",
    chip: "rgba(212,160,23,.14)",
  },
  done: {
    accent: "#4caf7a",
    bg: "#f5fbf7",
    border: "#d9eee3",
    head: "#2f7a52",
    headBg: "#e8f6ee",
    chip: "rgba(76,175,122,.14)",
  },
};

function renderKanban(board) {
  const root = document.getElementById("kanban-board");
  root.innerHTML = board.columns.map((col) => {
    const palette = KANBAN_STATUS_COLORS[col.status] || KANBAN_STATUS_COLORS.todo;
    const colStyle = [
      `background:${palette.bg}`,
      `border:1px solid ${palette.border}`,
      `border-top:2px solid ${palette.accent}`,
    ].join(";");
    const headStyle = [
      `background:${palette.headBg}`,
      `border:1px solid ${palette.border}`,
      `color:${palette.head}`,
      `border-radius:8px`,
      `padding:5px 7px`,
      `margin:0 0 6px`,
    ].join(";");
    return `
    <div class="kanban-col status-${col.status || "todo"}" data-status="${col.status || "todo"}" style="${colStyle}">
      <h3 style="${headStyle}">
        <span style="display:inline-flex;align-items:center;gap:6px;color:${palette.head}">
          <i class="kanban-dot" aria-hidden="true" style="width:7px;height:7px;border-radius:50%;background:${palette.accent};box-shadow:0 0 0 3px ${palette.chip}"></i>
          ${escapeHtml(col.label)}
        </span>
        <span class="kanban-count" style="color:${palette.head};background:${palette.chip};min-width:18px;height:16px;padding:0 5px;border-radius:999px;display:inline-grid;place-items:center;font-size:0.58rem;font-weight:700">${col.count}</span>
      </h3>
      ${col.tasks.slice(0, 3).map((task) => {
        const pct = Math.round(Number(task.project_progress || 0));
        const showBar = col.status === "in_progress" && task.project_progress != null;
        return `
        <article class="task-card status-${col.status || "todo"}${task.notes_count > 0 ? " has-notes" : ""}${task.has_problem ? " has-problem" : ""}" style="border-left:3px solid ${palette.accent};border-color:${palette.border}">
          <h4>${escapeHtml(task.title)}</h4>
          ${showBar ? `<div class="task-progress" title="Project ${pct}%"><span style="width:${Math.min(100, Math.max(0, pct))}%"></span></div>` : ""}
          <div class="task-card-foot">
            <span class="tag ${tagClass(task.category)}">${escapeHtml(task.category || "General")}</span>
            ${task.notes_count > 0
              ? `<span class="task-note-badge${task.has_problem ? " is-problem" : ""}" title="${task.notes_count} catatan">${task.notes_count}</span>`
              : ""}
            ${(() => {
              const people = (task.assignees && task.assignees.length)
                ? task.assignees
                : (task.assignee ? [task.assignee] : []);
              if (!people.length) return "<span></span>";
              return `<div class="mini-avatar-stack" title="${escapeHtml(people.map((u) => u.name).join(", "))}">${
                people.slice(0, 3).map((u) => {
                  const name = u.name || "?";
                  if (hasRealPhoto(u.avatar_url)) {
                    return `<img class="mini-avatar" src="${escapeHtml(safeUrl(u.avatar_url))}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" />`;
                  }
                  return `<span class="mini-avatar mini-avatar-initials" title="${escapeHtml(name)}">${escapeHtml(nameInitials(name))}</span>`;
                }).join("")
              }</div>`;
            })()}
          </div>
        </article>`;
      }).join("") || `<div class="muted" style="padding:4px 0">No tasks</div>`}
    </div>`;
  }).join("");
}

function nameInitials(name) {
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

function hasRealPhoto(url) {
  const value = String(url || "").trim();
  if (!value) return false;
  // Account profile photo: uploaded file or generated avatar URL
  return true;
}

function renderTeamAvatar(user) {
  const name = user?.name || "User";
  const online = Boolean(user?.is_online);
  const title = `${name}${online ? " · Online" : ""}`;
  const photo = hasRealPhoto(user?.avatar_url)
    ? `<img src="${escapeHtml(safeUrl(user.avatar_url))}" alt="${escapeHtml(name)}" />`
    : `<span class="team-avatar-initials" aria-hidden="true">${escapeHtml(nameInitials(name))}</span>`;
  return `
    <div class="team-avatar${online ? " is-online" : ""}" title="${escapeHtml(title)}" role="img" aria-label="${escapeHtml(title)}">
      ${photo}
      <span class="team-online-dot" aria-hidden="true"></span>
    </div>`;
}

function renderTeam(team) {
  document.getElementById("team-count").textContent = `${team.total} members`;
  document.getElementById("team-avatars").innerHTML = `
    ${(team.visible || []).map(renderTeamAvatar).join("")}
    ${team.extra > 0 ? `<div class="team-extra">+${team.extra}</div>` : ""}
  `;
}

function renderCalendar(data) {
  const title = document.getElementById("calendar-title");
  title.textContent = `${monthNames[data.month - 1]} ${data.year}`;

  const deadlineMap = new Map(data.days.map((d) => [d.date, d]));
  const first = new Date(Date.UTC(data.year, data.month - 1, 1));
  const daysInMonth = new Date(Date.UTC(data.year, data.month, 0)).getUTCDate();
  const startWeekday = first.getUTCDay();
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  let html = weekdays.map((d) => `<div class="cal-cell head">${d}</div>`).join("");
  for (let i = 0; i < startWeekday; i += 1) html += `<div class="cal-cell"></div>`;
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = `${data.year}-${String(data.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const classes = ["cal-cell"];
    const entry = deadlineMap.get(key);
    if (entry) {
      classes.push("has-deadline", toneFor(entry.deadlines?.[0]?.category || key));
    }
    if (key === todayKey) classes.push("today");
    html += `<div class="${classes.join(" ")}" title="${entry?.count || 0} deadline(s)">${day}</div>`;
  }
  document.getElementById("calendar-grid").innerHTML = html;

  document.getElementById("upcoming-list").innerHTML = data.upcoming.slice(0, 5).map((item) => {
    const tone = toneFor(item.category || item.title);
    return `
    <div class="upcoming-item">
      <div class="upcoming-item-main">
        <span class="upcoming-dot ${tone}"></span>
        <strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong>
      </div>
      <span class="due-chip">${formatDate(item.due_date)}</span>
    </div>`;
  }).join("") || `<div class="muted">No upcoming deadlines</div>`;
}

function renderAnalytics(data) {
  const completedSign = data.completed_growth >= 0 ? "+" : "";
  const createdSign = data.created_growth >= 0 ? "+" : "";
  document.getElementById("analytics-stats").innerHTML = `
    <div>
      <strong>${data.tasks_completed}</strong>
      <span>Tasks Completed (${completedSign}${data.completed_growth}%)</span>
    </div>
    <div>
      <strong>${data.tasks_created}</strong>
      <span>Tasks Created (${createdSign}${data.created_growth}%)</span>
    </div>
  `;

  const labels = data.series.map((p) => formatDate(p.date));
  const completed = data.series.map((p) => p.completed);
  const created = data.series.map((p) => p.created);
  const ctx = document.getElementById("analytics-chart");

  if (analyticsChart) analyticsChart.destroy();

  const buildChart = () => {
    if (typeof Chart === "undefined" || !ctx) return;
    analyticsChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Completed",
            data: completed,
            borderColor: "#1F5FD6",
            backgroundColor: "rgba(79,124,255,0.12)",
            fill: true,
            tension: 0.35,
            pointRadius: 0,
            borderWidth: 2.5,
          },
          {
            label: "Created",
            data: created,
            borderColor: "#94A3B8",
            backgroundColor: "transparent",
            tension: 0.35,
            pointRadius: 0,
            borderWidth: 2,
            borderDash: [5, 5],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: prefersReducedMotion() ? false : { duration: 420, easing: "easeOutQuart" },
        devicePixelRatio: Math.min(window.devicePixelRatio || 1, 1.75),
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              maxTicksLimit: 5,
              color: "#7a8699",
              font: { size: 10 },
            },
          },
          y: {
            beginAtZero: true,
            grid: { color: "#eef2f7" },
            ticks: { precision: 0, color: "#7a8699", font: { size: 10 } },
          },
        },
      },
    });
  };

  // Defer chart work until the canvas is near the viewport.
  if ("IntersectionObserver" in window && ctx) {
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        buildChart();
      },
      { rootMargin: "120px 0px" }
    );
    io.observe(ctx);
  } else {
    buildChart();
  }
}

function buildMonthLabels(minTs, maxTs) {
  const labels = [];
  const cursor = new Date(minTs);
  cursor.setUTCDate(1);
  cursor.setUTCHours(0, 0, 0, 0);
  const end = new Date(maxTs);
  while (cursor <= end && labels.length < 12) {
    labels.push(shortMonths[cursor.getUTCMonth()]);
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return labels.length ? labels : shortMonths.slice(0, 6);
}

function renderTimeline(items) {
  if (!items.length) {
    document.getElementById("gantt").innerHTML = `<div class="muted">No projects yet</div>`;
    return;
  }

  const starts = items.map((i) => new Date(i.start_date).getTime());
  const ends = items.map((i) => new Date(i.end_date).getTime());
  const min = Math.min(...starts);
  const max = Math.max(...ends);
  const span = Math.max(max - min, 1);
  const today = Date.now();
  const todayPct = Math.min(100, Math.max(0, ((today - min) / span) * 100));
  const months = buildMonthLabels(min, max);

  document.getElementById("gantt").innerHTML = `
    <div class="gantt-header">
      <div></div>
      <div class="gantt-months" style="grid-template-columns:repeat(${months.length}, minmax(0, 1fr))">
        ${months.map((m) => `<span>${m}</span>`).join("")}
      </div>
    </div>
    ${items.map((item) => {
      const start = new Date(item.start_date).getTime();
      const end = new Date(item.end_date).getTime();
      const left = ((start - min) / span) * 100;
      const width = Math.max(((end - start) / span) * 100, 8);
      return `
        <div class="gantt-row">
          <div class="gantt-label" title="${item.name}">${item.name}</div>
          <div class="gantt-track">
            <div class="gantt-today" style="left:${todayPct}%"></div>
            <div class="gantt-bar" style="left:${left}%;width:${width}%;background:${item.color}">
              ${Math.round(item.progress)}%
            </div>
          </div>
        </div>
      `;
    }).join("")}
  `;
}

function runWhenIdle(fn) {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => fn(), { timeout: 600 });
  } else {
    setTimeout(fn, 40);
  }
}

async function boot() {
  setGreeting();
  try {
    // Satu request bootstrap — jauh lebih cepat daripada 7 parallel round-trip
    const data = await api("/api/dashboard/summary");
    // Above-the-fold first for perceived speed
    renderOverdueAlert(data.overdue || { count: 0, items: [] });
    renderClassificationOverview(data.classifications || { items: [] });
    renderSprintOverview(
      data.sprints || {
        total_sprints: 0,
        projects_with_sprints: [],
        due_soon: [],
        completed: [],
        due_soon_window_days: 14,
      }
    );
    renderProgress(data.progress);
    renderKanban(data.kanban);
    renderTeam(data.team);

    runWhenIdle(() => {
      renderCalendar(data.calendar);
      renderTimeline(data.timeline);
      renderAnalytics(data.analytics);
      document.getElementById("dashboard")?.classList.add("dash-ready");
    });
  } catch (err) {
    console.error(err);
    const host = document.getElementById("classification-overview-grid");
    if (host) {
      host.innerHTML = `<div class="panel">Gagal memuat dashboard. Pastikan API berjalan.</div>`;
    }
  }
}

document.addEventListener("DOMContentLoaded", boot);
