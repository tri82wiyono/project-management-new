(() => {
  const $ = (id) => document.getElementById(id);

  const state = {
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    projectId: "",
    data: null,
  };

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function parseDate(value) {
    const [y, m, d] = String(value).split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function fmtShort(dateValue) {
    const d = parseDate(dateValue);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function fmtLong(dateValue) {
    const d = parseDate(dateValue);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function fmtMonth(dateObj) {
    return dateObj.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  }

  function daysBetween(a, b) {
    return Math.round((b - a) / 86400000);
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function buildMonthSegments(rangeStart, rangeEnd) {
    const segments = [];
    let cursor = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), 1);
    while (cursor <= rangeEnd) {
      const nextMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
      const segStart = cursor < rangeStart ? rangeStart : cursor;
      const segEndExclusive = nextMonth > rangeEnd ? new Date(rangeEnd.getTime() + 86400000) : nextMonth;
      const days = Math.max(daysBetween(segStart, segEndExclusive), 1);
      segments.push({
        key: `${cursor.getFullYear()}-${cursor.getMonth()}`,
        label: fmtMonth(cursor),
        days,
      });
      cursor = nextMonth;
      if (segments.length > 36) break;
    }
    return segments.length ? segments : [{ key: "m0", label: fmtMonth(rangeStart), days: 1 }];
  }

  function renderStats(summary) {
    $("tl-stats").innerHTML = `
      <article class="tl-stat">
        <div class="tl-stat-copy">
          <span>Active Projects</span>
          <strong>${summary.active_projects || 0}</strong>
        </div>
        <div class="tl-stat-ico blue" aria-hidden="true">▦</div>
      </article>
      <article class="tl-stat">
        <div class="tl-stat-copy">
          <span>Upcoming Deadlines</span>
          <strong>${summary.upcoming_deadlines || 0}</strong>
        </div>
        <div class="tl-stat-ico sky" aria-hidden="true">◔</div>
      </article>
      <article class="tl-stat">
        <div class="tl-stat-copy">
          <span>Overdue Tasks</span>
          <strong>${summary.overdue_tasks || 0}</strong>
        </div>
        <div class="tl-stat-ico red" aria-hidden="true">⚠</div>
      </article>
    `;
  }

  function renderFilter(options) {
    const select = $("tl-project-filter");
    const current = state.projectId;
    select.innerHTML =
      `<option value="">All Projects</option>` +
      (options || [])
        .map(
          (item) =>
            `<option value="${item.id}" ${String(item.id) === String(current) ? "selected" : ""}>${escapeHtml(
              item.name
            )}</option>`
        )
        .join("");
  }

  function renderGantt(data) {
    const wrap = $("tl-gantt");
    const weeks = data.week_starts || [];
    const rangeStart = parseDate(data.range_start || (weeks[0] || data.today));
    const rangeEnd = parseDate(
      data.range_end || (weeks.length ? weeks[weeks.length - 1] : data.today)
    );
    if (!(rangeStart instanceof Date) || Number.isNaN(rangeStart.getTime())) {
      wrap.innerHTML = `<div class="tl-empty">Tidak ada rentang tanggal untuk ditampilkan.</div>`;
      return;
    }

    const totalDays = Math.max(daysBetween(rangeStart, rangeEnd), 1);
    const months = buildMonthSegments(rangeStart, rangeEnd);
    const monthCols = months.map((m) => `${m.days}fr`).join(" ");

    const pct = (value) => {
      const d = parseDate(value);
      return clamp((daysBetween(rangeStart, d) / totalDays) * 100, 0, 100);
    };

    const today = parseDate(data.today);
    const showToday = today >= rangeStart && today <= rangeEnd;
    const todayLeft = showToday ? pct(data.today) : null;

    const head = `
      <div class="tl-gantt-head">
        <div>Project / Modul</div>
        <div class="tl-months" style="grid-template-columns:${monthCols}">
          ${months
            .map((m) => `<div class="tl-month" title="${escapeHtml(m.label)}">${escapeHtml(m.label)}</div>`)
            .join("")}
        </div>
      </div>
    `;

    if (!(data.projects || []).length) {
      wrap.innerHTML = `${head}<div class="tl-empty">Belum ada project. Atur Start & Target Date (mis. 3 bulan) di menu Projects.</div>`;
      return;
    }

    const rows = data.projects
      .map((project, index) => {
        const start = parseDate(project.start_date);
        const end = parseDate(project.end_date);
        const left = clamp((daysBetween(rangeStart, start) / totalDays) * 100, 0, 100);
        const right = clamp((daysBetween(rangeStart, end) / totalDays) * 100, 0, 100);
        const width = Math.max(right - left, 2.5);
        const progress = clamp(Number(project.progress || 0), 0, 100);
        const barColor = project.color || project.status_color || "#4f7cff";

        const modules = (project.modules || project.milestones || [])
          .map((m) => {
            const mDate = parseDate(m.date);
            if (mDate < rangeStart || mDate > rangeEnd) return "";
            const mLeft = pct(m.date);
            const tone = String(m.status || "todo");
            return `<span
              class="tl-milestone ${tone}"
              style="left:${mLeft}%"
              title="${escapeHtml(m.title)}${m.status_label ? ` · ${m.status_label}` : ""}"
            ></span>`;
          })
          .join("");

        const todayMarker = showToday
          ? `<div class="tl-today-line ${index === 0 ? "with-label" : ""}" style="left:${todayLeft}%">${
              index === 0
                ? `<span class="tl-today-label">Today, ${fmtShort(data.today)}</span>`
                : ""
            }</div>`
          : "";

        return `
          <div class="tl-gantt-row">
            <div class="tl-project-label">
              <strong title="${escapeHtml(project.name)}">${escapeHtml(project.name)}</strong>
              <span>${escapeHtml(project.code)} · ${escapeHtml(project.status_label)} · ${Math.round(progress)}%</span>
            </div>
            <div class="tl-track">
              ${todayMarker}
              <div class="tl-bar" style="left:${left}%;width:${width}%;--bar-color:${barColor}">
                <div class="tl-bar-fill" style="width:${progress}%;background:${barColor}"></div>
                <span class="tl-bar-label">${Math.round(progress)}%</span>
              </div>
              ${modules}
            </div>
          </div>
        `;
      })
      .join("");

    wrap.innerHTML = `
      <div class="tl-gantt">
        ${head}
        ${rows}
        <p class="tl-hint">Skala bulan · bar = jadwal project (Start → Target) · isi = progress · titik = deadline modul.</p>
      </div>
    `;
  }

  function renderDeadlines(items) {
    const box = $("tl-deadlines");
    if (!(items || []).length) {
      box.innerHTML = `<div class="tl-empty">Tidak ada deadline mendatang.</div>`;
      return;
    }
    box.innerHTML = items
      .map((item) => {
        const statusClass = String(item.status || "").toLowerCase();
        return `
        <article class="tl-deadline">
          <time datetime="${escapeHtml(item.due_date)}">${fmtLong(item.due_date)}</time>
          <strong>${escapeHtml(item.title)}</strong>
          <span class="tl-badge ${statusClass}">${escapeHtml(item.status_label || item.status)}</span>
        </article>`;
      })
      .join("");
  }

  function renderLegend(items) {
    $("tl-legend").innerHTML = (items || [])
      .map(
        (item) => `
      <div class="tl-legend-item">
        <span class="tl-legend-dot" style="background:${item.color}"></span>
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.description)}</span>
        </div>
      </div>`
      )
      .join("");
  }

  async function loadTimeline() {
    const params = new URLSearchParams({
      year: String(state.year),
      month: String(state.month),
    });
    if (state.projectId) params.set("project_id", state.projectId);

    const res = await fetch(`/api/timeline?${params.toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!res.ok) throw new Error("Gagal memuat timeline");
    const data = await res.json();
    state.data = data;
    state.year = data.year;
    state.month = data.month;
    $("tl-month-label").textContent = data.month_label;
    renderFilter(data.project_options || []);
    renderStats(data.summary || {});
    renderGantt(data);
    renderDeadlines(data.upcoming || []);
    renderLegend(data.legend || []);
  }

  function shiftMonth(delta) {
    let y = state.year;
    let m = state.month + delta;
    if (m < 1) {
      m = 12;
      y -= 1;
    } else if (m > 12) {
      m = 1;
      y += 1;
    }
    state.year = y;
    state.month = m;
    loadTimeline().catch((err) => {
      $("tl-gantt").innerHTML = `<div class="tl-empty">${escapeHtml(err.message)}</div>`;
    });
  }

  $("btn-prev-month").addEventListener("click", () => shiftMonth(-1));
  $("btn-next-month").addEventListener("click", () => shiftMonth(1));
  $("tl-project-filter").addEventListener("change", (event) => {
    state.projectId = event.target.value;
    loadTimeline().catch((err) => {
      $("tl-gantt").innerHTML = `<div class="tl-empty">${escapeHtml(err.message)}</div>`;
    });
  });

  loadTimeline().catch((err) => {
    $("tl-gantt").innerHTML = `<div class="tl-empty">${escapeHtml(err.message)}</div>`;
  });
})();
