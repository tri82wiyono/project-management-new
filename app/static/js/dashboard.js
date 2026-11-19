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

function renderKPI(data) {
  const cards = [
    { label: "Total Projects", value: data.total_projects, growth: formatGrowth(data.total_projects_growth), icon: "▣", tone: "violet", down: data.total_projects_growth < 0 },
    { label: "Completed Tasks", value: data.completed_tasks, growth: formatGrowth(data.completed_tasks_growth), icon: "✓", tone: "green", down: data.completed_tasks_growth < 0 },
    { label: "In Progress", value: data.in_progress, growth: formatGrowth(data.in_progress_growth), icon: "⏱", tone: "amber", down: data.in_progress_growth < 0 },
    { label: "On-Time Delivery", value: `${data.on_time_delivery}%`, growth: formatGrowth(data.on_time_delivery_growth, " pp"), icon: "◎", tone: "blue", down: data.on_time_delivery_growth < 0 },
  ];
  document.getElementById("kpi-grid").innerHTML = cards.map((c) => `
    <article class="kpi-card">
      <div class="kpi-top">
        <div>
          <p class="kpi-label">${c.label}</p>
          <p class="kpi-value">${c.value}</p>
        </div>
        <div class="kpi-icon ${c.tone}">${c.icon}</div>
      </div>
      <span class="kpi-growth${c.down ? " down" : ""}">${c.growth}</span>
    </article>
  `).join("");
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
        <div class="progress-fill" data-width="${p.progress}" style="background:${escapeHtml(p.color || "#4F7CFF")}"></div>
      </div>
    </div>
  `).join("");
  requestAnimationFrame(() => {
    root.querySelectorAll(".progress-fill").forEach((el) => {
      el.style.width = `${el.dataset.width}%`;
    });
  });
}

function renderKanban(board) {
  const root = document.getElementById("kanban-board");
  root.innerHTML = board.columns.map((col) => `
    <div class="kanban-col">
      <h3><span>${col.label}</span><span>${col.count}</span></h3>
      ${col.tasks.slice(0, 3).map((task) => {
        const pct = Math.round(Number(task.project_progress || 0));
        const showBar = col.status === "in_progress" && task.project_progress != null;
        return `
        <article class="task-card${task.notes_count > 0 ? " has-notes" : ""}${task.has_problem ? " has-problem" : ""}">
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
                people.slice(0, 3).map((u) =>
                  `<img class="mini-avatar" src="${escapeHtml(safeUrl(u.avatar_url))}" alt="${escapeHtml(u.name)}" title="${escapeHtml(u.name)}" />`
                ).join("")
              }</div>`;
            })()}
          </div>
        </article>`;
      }).join("") || `<div class="muted" style="padding:4px 0">No tasks</div>`}
    </div>
  `).join("");
}

function renderTeam(team) {
  document.getElementById("team-count").textContent = `${team.total} members`;
  document.getElementById("team-avatars").innerHTML = `
    ${team.visible.map((u) => `<img src="${escapeHtml(safeUrl(u.avatar_url))}" alt="${escapeHtml(u.name)}" title="${escapeHtml(u.name)}" />`).join("")}
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
  analyticsChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Completed",
          data: completed,
          borderColor: "#4F7CFF",
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

async function boot() {
  setGreeting();
  try {
    // Satu request bootstrap — jauh lebih cepat daripada 7 parallel round-trip
    const data = await api("/api/dashboard/summary");
    renderKPI(data.kpi);
    // Fallback bila summary belum memuat overdue (backend lama / cache)
    const overdue = data.overdue && typeof data.overdue.count === "number"
      ? data.overdue
      : await api("/api/dashboard/overdue").catch(() => ({ count: 0, items: [] }));
    renderOverdueAlert(overdue);
    renderProgress(data.progress);
    renderKanban(data.kanban);
    renderTeam(data.team);
    renderCalendar(data.calendar);
    renderAnalytics(data.analytics);
    renderTimeline(data.timeline);
  } catch (err) {
    console.error(err);
    document.getElementById("kpi-grid").innerHTML = `<div class="panel">Gagal memuat dashboard. Pastikan API berjalan.</div>`;
  }
}

document.addEventListener("DOMContentLoaded", boot);
