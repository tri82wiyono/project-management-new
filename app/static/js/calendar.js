const api = async (path) => {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Request failed: ${path}`);
  return res.json();
};

const monthNames = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const shortMonths = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const weekdays = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const DEADLINE_TONES = ["tone-amber", "tone-green", "tone-violet", "tone-blue"];

const STATUS_LABEL = {
  todo: "To Do",
  in_progress: "In Progress",
  review: "Review",
  done: "Done",
};

const state = {
  year: new Date().getFullYear(),
  month: new Date().getMonth() + 1,
  selectedDate: null,
  data: null,
};

const els = {
  monthLabel: document.getElementById("cal-month-label"),
  title: document.getElementById("calendar-title"),
  meta: document.getElementById("cal-month-meta"),
  grid: document.getElementById("calendar-grid"),
  stats: document.getElementById("cal-stats"),
  dayTitle: document.getElementById("cal-day-title"),
  dayCount: document.getElementById("cal-day-count"),
  dayList: document.getElementById("cal-day-list"),
  upcoming: document.getElementById("upcoming-list"),
  prev: document.getElementById("btn-prev-month"),
  next: document.getElementById("btn-next-month"),
  today: document.getElementById("btn-today"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toneFor(key = "") {
  let hash = 0;
  for (let i = 0; i < String(key).length; i += 1) {
    hash = (hash + key.charCodeAt(i) * (i + 1)) % DEADLINE_TONES.length;
  }
  return DEADLINE_TONES[hash];
}

function formatDate(value) {
  const d = new Date(value);
  return `${shortMonths[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

function formatDayTitle(key) {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function todayKey() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function deadlineMap(data) {
  return new Map((data.days || []).map((d) => [d.date, d]));
}

function selectedEntry() {
  if (!state.data || !state.selectedDate) return null;
  return deadlineMap(state.data).get(state.selectedDate) || null;
}

function renderStats(data) {
  const totalDeadlines = (data.days || []).reduce((sum, d) => sum + Number(d.count || 0), 0);
  const busyDays = (data.days || []).length;
  const upcoming = (data.upcoming || []).length;

  els.stats.innerHTML = `
    <article class="cal-stat">
      <span>Deadlines bulan ini</span>
      <strong>${totalDeadlines}</strong>
    </article>
    <article class="cal-stat">
      <span>Hari dengan deadline</span>
      <strong>${busyDays}</strong>
    </article>
    <article class="cal-stat">
      <span>Upcoming</span>
      <strong>${upcoming}</strong>
    </article>
  `;
}

function renderDeadlineItem(item) {
  const tone = toneFor(item.category || item.title);
  const status = STATUS_LABEL[item.status] || item.status;
  return `
    <a class="cal-deadline-item" href="/tasks" data-task-id="${item.id}">
      <div class="cal-deadline-main">
        <span class="upcoming-dot ${tone}"></span>
        <div class="cal-deadline-copy">
          <strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.project_name || "—")} · ${escapeHtml(status)}</span>
        </div>
      </div>
      <span class="due-chip">${formatDate(item.due_date)}</span>
    </a>`;
}

function renderDayPanel() {
  const entry = selectedEntry();
  const items = entry?.deadlines || [];
  els.dayTitle.textContent = state.selectedDate ? formatDayTitle(state.selectedDate) : "Selected day";
  els.dayCount.textContent = `${items.length} deadline`;
  els.dayList.innerHTML = items.length
    ? items.map(renderDeadlineItem).join("")
    : `<div class="cal-empty">Tidak ada deadline di tanggal ini.</div>`;
}

function renderUpcoming(data) {
  const items = data.upcoming || [];
  els.upcoming.innerHTML = items.length
    ? items.map(renderDeadlineItem).join("")
    : `<div class="cal-empty">Tidak ada deadline mendatang.</div>`;
}

function renderCalendar(data) {
  els.monthLabel.textContent = `${monthNames[data.month - 1]} ${data.year}`;
  els.title.textContent = `${monthNames[data.month - 1]} ${data.year}`;
  const total = (data.days || []).reduce((sum, d) => sum + Number(d.count || 0), 0);
  els.meta.textContent = `${total} deadline`;

  const map = deadlineMap(data);
  const first = new Date(Date.UTC(data.year, data.month - 1, 1));
  const daysInMonth = new Date(Date.UTC(data.year, data.month, 0)).getUTCDate();
  const startWeekday = first.getUTCDay();
  const today = todayKey();

  let html = weekdays.map((d) => `<div class="cal-cell head">${d}</div>`).join("");
  for (let i = 0; i < startWeekday; i += 1) html += `<div class="cal-cell muted-cell"></div>`;

  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = `${data.year}-${String(data.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const entry = map.get(key);
    const classes = ["cal-cell", "cal-day"];
    if (entry) classes.push("has-deadline", toneFor(entry.deadlines?.[0]?.category || key));
    if (key === today) classes.push("today");
    if (key === state.selectedDate) classes.push("selected");
    const countLabel = entry ? `${entry.count} deadline` : "0 deadline";
    html += `
      <button type="button" class="${classes.join(" ")}" data-date="${key}" title="${countLabel}">
        <span class="cal-day-num">${day}</span>
        ${entry ? `<span class="cal-day-count">${entry.count}</span>` : ""}
      </button>`;
  }

  els.grid.innerHTML = html;
}

function shiftMonth(delta) {
  let month = state.month + delta;
  let year = state.year;
  if (month < 1) {
    month = 12;
    year -= 1;
  } else if (month > 12) {
    month = 1;
    year += 1;
  }
  state.year = year;
  state.month = month;
  state.selectedDate = null;
  return loadCalendar();
}

async function loadCalendar() {
  const data = await api(`/api/dashboard/calendar?year=${state.year}&month=${state.month}`);
  state.data = data;
  state.year = data.year;
  state.month = data.month;

  if (!state.selectedDate) {
    const today = todayKey();
    const inMonth =
      today.startsWith(`${data.year}-${String(data.month).padStart(2, "0")}`);
    state.selectedDate = inMonth ? today : `${data.year}-${String(data.month).padStart(2, "0")}-01`;
  }

  renderStats(data);
  renderCalendar(data);
  renderDayPanel();
  renderUpcoming(data);
}

function wireEvents() {
  els.prev?.addEventListener("click", () => shiftMonth(-1));
  els.next?.addEventListener("click", () => shiftMonth(1));
  els.today?.addEventListener("click", async () => {
    const now = new Date();
    state.year = now.getFullYear();
    state.month = now.getMonth() + 1;
    state.selectedDate = todayKey();
    await loadCalendar();
  });

  els.grid?.addEventListener("click", (e) => {
    const cell = e.target.closest("[data-date]");
    if (!cell) return;
    state.selectedDate = cell.dataset.date;
    renderCalendar(state.data);
    renderDayPanel();
  });

}

async function init() {
  wireEvents();
  try {
    await loadCalendar();
  } catch (err) {
    els.grid.innerHTML = `<div class="cal-empty">Gagal memuat calendar: ${escapeHtml(err.message)}</div>`;
  }
}

init();
