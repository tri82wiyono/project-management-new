from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Project, ProjectStatus, Task, TaskStatus, User
from app.services import org_scope

STATUS_BAR_COLOR = {
    ProjectStatus.backlog: "#94a3b8",
    ProjectStatus.dev: "#4f7cff",
    ProjectStatus.sit: "#8b5cf6",
    ProjectStatus.uat: "#f59e0b",
    ProjectStatus.to: "#06b6d4",
    ProjectStatus.izin: "#f97316",
    ProjectStatus.release: "#22c55e",
}

STATUS_LABEL = {
    ProjectStatus.backlog: "Backlog",
    ProjectStatus.dev: "Dev",
    ProjectStatus.sit: "SIT",
    ProjectStatus.uat: "UAT",
    ProjectStatus.to: "TO",
    ProjectStatus.izin: "Izin",
    ProjectStatus.release: "Release",
}

PIPELINE_STATUSES = {
    ProjectStatus.dev,
    ProjectStatus.sit,
    ProjectStatus.uat,
    ProjectStatus.to,
    ProjectStatus.izin,
}

TASK_STATUS_LABEL = {
    TaskStatus.todo: "To Do",
    TaskStatus.in_progress: "In Progress",
    TaskStatus.review: "Review",
    TaskStatus.done: "Done",
}


def _initials(name: str) -> str:
    parts = [p for p in name.replace("-", " ").split() if p]
    if not parts:
        return "PR"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _week_starts_covering(range_start: date, range_end: date) -> list[date]:
    cursor = range_start - timedelta(days=range_start.weekday())
    weeks: list[date] = []
    while cursor <= range_end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks or [range_start]


def get_timeline_page(
    db: Session,
    *,
    year: int,
    month: int,
    project_id: int | None = None,
    user: User | None = None,
) -> dict:
    """
    Timeline shows the overall project schedule (all modules/tasks inside),
    not only a single-day marker. Month navigation focuses the viewport,
    but bars still use each project's start → target date.
    """
    today = date.today()
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    projects_q = select(Project).order_by(Project.start_date.asc(), Project.id.asc())
    p_scope = org_scope.project_visibility_filter(db, user) if user is not None else None
    if p_scope is not None:
        projects_q = projects_q.where(p_scope)
    if project_id:
        if user is not None:
            project = db.get(Project, project_id)
            if project is not None:
                org_scope.require_project_view(db, user, project)
        projects_q = projects_q.where(Project.id == project_id)
    projects = list(db.scalars(projects_q).all())

    # Prefer projects overlapping the focused month; fall back to all.
    visible = [
        p
        for p in projects
        if p.end_date >= month_start and p.start_date <= month_end
    ]
    if not visible:
        visible = list(projects)

    active_count = sum(1 for p in projects if p.status in PIPELINE_STATUSES)

    t_scope = org_scope.task_visibility_filter(db, user) if user is not None else None
    upcoming_q = (
        select(Task)
        .where(Task.due_date.is_not(None))
        .where(Task.due_date >= today)
        .where(Task.status != TaskStatus.done)
    )
    if t_scope is not None:
        upcoming_q = upcoming_q.where(t_scope)
    upcoming_tasks = db.scalars(
        upcoming_q.order_by(Task.due_date.asc(), Task.id.asc()).limit(8)
    ).all()

    overdue_q = (
        select(func.count())
        .select_from(Task)
        .where(Task.due_date.is_not(None))
        .where(Task.due_date < today)
        .where(Task.status != TaskStatus.done)
    )
    if t_scope is not None:
        overdue_q = overdue_q.where(t_scope)
    overdue_count = db.scalar(overdue_q) or 0

    upcoming_deadlines = []
    for task in upcoming_tasks:
        project = next((p for p in projects if p.id == task.project_id), None)
        if project_id and task.project_id != project_id:
            continue
        upcoming_deadlines.append(
            {
                "id": task.id,
                "title": task.title,
                "due_date": task.due_date.isoformat(),
                "status": task.status.value,
                "status_label": TASK_STATUS_LABEL.get(task.status, task.status.value),
                "project_id": task.project_id,
                "project_name": project.name if project else "",
            }
        )

    if not upcoming_deadlines:
        for p in sorted(visible, key=lambda x: x.end_date):
            if p.end_date >= today and p.status != ProjectStatus.release:
                upcoming_deadlines.append(
                    {
                        "id": p.id,
                        "title": f"{p.name} target end",
                        "due_date": p.end_date.isoformat(),
                        "status": "in_progress" if p.status in PIPELINE_STATUSES else "todo",
                        "status_label": STATUS_LABEL.get(p.status, p.status.value),
                        "project_id": p.id,
                        "project_name": p.name,
                    }
                )
            if len(upcoming_deadlines) >= 6:
                break

    upcoming_count = len(upcoming_deadlines)

    # Overall schedule window: cover focused month AND full project spans (~3 months typical).
    range_start = month_start
    range_end = month_end
    if visible:
        range_start = min(range_start, min(p.start_date for p in visible))
        range_end = max(range_end, max(p.end_date for p in visible))
    # Ensure at least ~12 weeks so a 3-month delivery plan is readable.
    min_span_end = range_start + timedelta(days=84)
    if range_end < min_span_end:
        range_end = min_span_end

    week_starts = _week_starts_covering(range_start, range_end)

    tasks_by_project: dict[int, list[Task]] = {}
    if visible:
        task_rows = db.scalars(
            select(Task)
            .where(Task.project_id.in_([p.id for p in visible]))
            .order_by(Task.due_date.asc().nulls_last(), Task.id.asc())
        ).all()
        for t in task_rows:
            tasks_by_project.setdefault(t.project_id, []).append(t)

    schedule = []
    for p in visible:
        modules = []
        for t in tasks_by_project.get(p.id, []):
            marker_date = t.due_date or p.end_date
            if marker_date < range_start or marker_date > range_end:
                continue
            modules.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "date": marker_date.isoformat(),
                    "status": t.status.value,
                    "status_label": TASK_STATUS_LABEL.get(t.status, t.status.value),
                }
            )

        schedule.append(
            {
                "id": p.id,
                "name": p.name,
                "code": _initials(p.name),
                "status": p.status.value,
                "status_label": STATUS_LABEL.get(p.status, p.status.value),
                "color": p.color or STATUS_BAR_COLOR.get(p.status, "#4f7cff"),
                "status_color": STATUS_BAR_COLOR.get(p.status, "#94a3b8"),
                "progress": float(p.progress or 0),
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat(),
                "modules": modules,
                "milestones": [
                    {"date": m["date"], "title": m["title"]} for m in modules[:8]
                ],
            }
        )

    options_q = select(Project).order_by(Project.name.asc())
    if p_scope is not None:
        options_q = options_q.where(p_scope)
    project_options = [
        {"id": p.id, "name": p.name}
        for p in db.scalars(options_q).all()
    ]

    return {
        "year": year,
        "month": month,
        "month_label": month_start.strftime("%B %Y"),
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "today": today.isoformat(),
        "week_starts": [d.isoformat() for d in week_starts],
        "summary": {
            "active_projects": active_count,
            "upcoming_deadlines": upcoming_count,
            "overdue_tasks": int(overdue_count),
        },
        "projects": schedule,
        "upcoming": upcoming_deadlines[:6],
        "project_options": project_options,
        "legend": [
            {
                "color": STATUS_BAR_COLOR[status],
                "label": STATUS_LABEL[status],
                "description": f"Status project: {STATUS_LABEL[status]}",
            }
            for status in ProjectStatus
        ],
    }
