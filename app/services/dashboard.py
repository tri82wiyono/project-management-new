from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.models import Project, ProjectStatus, Task, TaskAssignee, TaskStatus, User
from app.schemas.schemas import (
    AnalyticsPoint,
    AnalyticsResponse,
    CalendarDay,
    CalendarResponse,
    DashboardKPI,
    DeadlineItem,
    KanbanBoard,
    KanbanColumn,
    OverdueAlert,
    OverdueItem,
    ProjectProgress,
    TaskOut,
    TeamOverview,
    TimelineItem,
    UserOut,
)


STATUS_LABELS = {
    TaskStatus.todo: "To Do",
    TaskStatus.in_progress: "In Progress",
    TaskStatus.review: "Review",
    TaskStatus.done: "Done",
}


def _task_assignees(task: Task) -> list[UserOut]:
    people: list[UserOut] = []
    seen: set[int] = set()
    for link in task.assignees or []:
        if not link.user or link.user.id in seen:
            continue
        people.append(UserOut.model_validate(link.user))
        seen.add(link.user.id)
    if task.assignee and task.assignee.id not in seen:
        people.insert(0, UserOut.model_validate(task.assignee))
    return people


def _task_out(task: Task) -> TaskOut:
    assignees = _task_assignees(task)
    primary = assignees[0] if assignees else None
    notes = list(task.notes or [])
    notes_count = len(notes)
    has_problem = any((n.kind or "problem") == "problem" for n in notes)
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        category=task.category,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        project_id=task.project_id,
        assignee_id=primary.id if primary else task.assignee_id,
        assignee_ids=[u.id for u in assignees],
        completed_at=task.completed_at,
        created_at=task.created_at,
        assignee=primary,
        assignees=assignees,
        project_name=task.project.name if task.project else None,
        project_progress=float(task.project.progress) if task.project else None,
        notes_count=notes_count,
        has_problem=has_problem,
    )


def _growth(current: float | int, previous: float | int) -> float:
    current = float(current)
    previous = float(previous)
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100.0, 1)


def _period_bounds(days: int = 30) -> tuple[datetime, datetime, datetime]:
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    return previous_start, current_start, now


def get_kpi(db: Session) -> DashboardKPI:
    prev_start, curr_start, now = _period_bounds(30)

    # Aggregate counts in fewer round-trips
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    status_rows = db.execute(
        select(Task.status, func.count()).group_by(Task.status)
    ).all()
    status_map = {row[0]: int(row[1]) for row in status_rows}
    completed_tasks = status_map.get(TaskStatus.done, 0)
    in_progress = status_map.get(TaskStatus.in_progress, 0) + status_map.get(TaskStatus.review, 0)

    projects_curr = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(and_(Project.created_at >= curr_start, Project.created_at <= now))
        )
        or 0
    )
    projects_prev = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(and_(Project.created_at >= prev_start, Project.created_at < curr_start))
        )
        or 0
    )

    completed_curr = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.completed_at.is_not(None),
                    Task.completed_at >= curr_start,
                    Task.completed_at <= now,
                )
            )
        )
        or 0
    )
    completed_prev = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.completed_at.is_not(None),
                    Task.completed_at >= prev_start,
                    Task.completed_at < curr_start,
                )
            )
        )
        or 0
    )

    in_progress_curr = in_progress
    in_progress_prev = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status.in_([TaskStatus.in_progress, TaskStatus.review]),
                    Task.created_at < curr_start,
                )
            )
        )
        or 0
    )

    # On-time rate via SQL (hindari load semua task done ke Python)
    done_with_due = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.due_date.is_not(None),
                    Task.completed_at.is_not(None),
                )
            )
        )
        or 0
    )
    on_time = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.due_date.is_not(None),
                    Task.completed_at.is_not(None),
                    func.date(Task.completed_at) <= Task.due_date,
                )
            )
        )
        or 0
    )
    on_time_delivery = round((on_time / done_with_due) * 100, 1) if done_with_due else 0.0

    prev_done = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.due_date.is_not(None),
                    Task.completed_at.is_not(None),
                    Task.completed_at >= prev_start,
                    Task.completed_at < curr_start,
                )
            )
        )
        or 0
    )
    prev_on_time = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.status == TaskStatus.done,
                    Task.due_date.is_not(None),
                    Task.completed_at.is_not(None),
                    Task.completed_at >= prev_start,
                    Task.completed_at < curr_start,
                    func.date(Task.completed_at) <= Task.due_date,
                )
            )
        )
        or 0
    )
    prev_on_time_pct = round((prev_on_time / prev_done) * 100, 1) if prev_done else 0.0

    return DashboardKPI(
        total_projects=total_projects,
        total_projects_growth=_growth(projects_curr, projects_prev),
        completed_tasks=completed_tasks,
        completed_tasks_growth=_growth(completed_curr, completed_prev),
        in_progress=in_progress,
        in_progress_growth=_growth(in_progress_curr, in_progress_prev),
        on_time_delivery=on_time_delivery,
        on_time_delivery_growth=round(on_time_delivery - prev_on_time_pct, 1),
    )


def get_project_progress(db: Session, limit: int = 8) -> list[ProjectProgress]:
    """Active projects for the dashboard widget.

    Ordered by name (same as /projects) so the preview matches View All,
    instead of clustering many Review=70% projects at the top.
    """
    projects = db.scalars(
        select(Project)
        .where(Project.status != ProjectStatus.release)
        .order_by(Project.name.asc(), Project.id.asc())
        .limit(limit)
    ).all()
    return [
        ProjectProgress(
            id=p.id,
            name=p.name,
            progress=p.progress,
            status=p.status,
            color=p.color,
        )
        for p in projects
    ]


def get_kanban(
    db: Session,
    project_id: int | None = None,
    *,
    limit_per_column: int | None = None,
) -> KanbanBoard:
    load_opts = (
        joinedload(Task.assignee),
        joinedload(Task.assignees).joinedload(TaskAssignee.user),
        joinedload(Task.project),
        joinedload(Task.notes),
    )

    # Mode ringan (dashboard): hitung per kolom + ambil N terbaru saja
    if limit_per_column:
        count_stmt = select(Task.status, func.count()).group_by(Task.status)
        if project_id:
            count_stmt = count_stmt.where(Task.project_id == project_id)
        counts = {row[0]: int(row[1]) for row in db.execute(count_stmt).all()}

        columns = []
        for status in TaskStatus:
            stmt = (
                select(Task)
                .options(*load_opts)
                .where(Task.status == status)
                .order_by(Task.created_at.desc())
                .limit(limit_per_column)
            )
            if project_id:
                stmt = stmt.where(Task.project_id == project_id)
            tasks = db.scalars(stmt).unique().all()
            columns.append(
                KanbanColumn(
                    status=status,
                    label=STATUS_LABELS[status],
                    count=counts.get(status, 0),
                    tasks=[_task_out(t) for t in tasks],
                )
            )
        return KanbanBoard(columns=columns)

    stmt = select(Task).options(*load_opts)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    tasks = db.scalars(stmt.order_by(Task.created_at.desc())).unique().all()

    grouped: dict[TaskStatus, list[Task]] = {status: [] for status in TaskStatus}
    for task in tasks:
        grouped[task.status].append(task)

    return KanbanBoard(
        columns=[
            KanbanColumn(
                status=status,
                label=STATUS_LABELS[status],
                count=len(grouped[status]),
                tasks=[_task_out(t) for t in grouped[status]],
            )
            for status in TaskStatus
        ]
    )


def get_timeline(db: Session, limit: int | None = 25) -> list[TimelineItem]:
    stmt = select(Project).order_by(Project.start_date.asc(), Project.name.asc())
    if limit:
        stmt = stmt.limit(limit)
    projects = db.scalars(stmt).all()
    return [
        TimelineItem(
            id=p.id,
            name=p.name,
            progress=p.progress,
            color=p.color,
            start_date=p.start_date,
            end_date=p.end_date,
            status=p.status,
        )
        for p in projects
    ]


def get_overdue_alert(db: Session, *, limit: int = 3) -> OverdueAlert:
    """Tugas belum selesai yang due date-nya sudah lewat hari ini."""
    today = date.today()
    count = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                and_(
                    Task.due_date.is_not(None),
                    Task.due_date < today,
                    Task.status != TaskStatus.done,
                )
            )
        )
        or 0
    )
    tasks = db.scalars(
        select(Task)
        .options(
            joinedload(Task.assignee),
            joinedload(Task.project),
        )
        .where(
            and_(
                Task.due_date.is_not(None),
                Task.due_date < today,
                Task.status != TaskStatus.done,
            )
        )
        .order_by(Task.due_date.asc(), Task.id.asc())
        .limit(limit)
    ).unique().all()

    items = [
        OverdueItem(
            id=t.id,
            title=t.title,
            due_date=t.due_date,
            status=t.status,
            category=t.category,
            project_name=t.project.name if t.project else "",
            assignee=UserOut.model_validate(t.assignee) if t.assignee else None,
            days_overdue=max(0, (today - t.due_date).days),
        )
        for t in tasks
        if t.due_date is not None
    ]
    return OverdueAlert(count=int(count), items=items)


def get_dashboard_summary(db: Session) -> dict:
    """Satu payload untuk bootstrap dashboard (hindari 7 round-trip HTTP)."""
    return {
        "kpi": get_kpi(db),
        "progress": get_project_progress(db),
        "kanban": get_kanban(db, limit_per_column=6),
        "timeline": get_timeline(db, limit=25),
        "analytics": get_analytics(db, 30),
        "calendar": get_calendar(db, light=True),
        "team": get_team_overview(db),
        "overdue": get_overdue_alert(db),
    }


def get_analytics(db: Session, days: int = 30) -> AnalyticsResponse:
    today = date.today()
    start = today - timedelta(days=days - 1)
    created_rows = db.execute(
        select(func.date(Task.created_at), func.count())
        .where(Task.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
        .group_by(func.date(Task.created_at))
    ).all()
    completed_rows = db.execute(
        select(func.date(Task.completed_at), func.count())
        .where(
            and_(
                Task.completed_at.is_not(None),
                Task.completed_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
        .group_by(func.date(Task.completed_at))
    ).all()

    created_map = {row[0]: row[1] for row in created_rows}
    completed_map = {row[0]: row[1] for row in completed_rows}

    series: list[AnalyticsPoint] = []
    for i in range(days):
        day = start + timedelta(days=i)
        series.append(
            AnalyticsPoint(
                date=day,
                created=int(created_map.get(day, 0)),
                completed=int(completed_map.get(day, 0)),
            )
        )

    tasks_completed = sum(p.completed for p in series)
    tasks_created = sum(p.created for p in series)

    mid = days // 2
    first_completed = sum(p.completed for p in series[:mid])
    second_completed = sum(p.completed for p in series[mid:])
    first_created = sum(p.created for p in series[:mid])
    second_created = sum(p.created for p in series[mid:])

    return AnalyticsResponse(
        tasks_completed=tasks_completed,
        tasks_created=tasks_created,
        completed_growth=_growth(second_completed, first_completed),
        created_growth=_growth(second_created, first_created),
        series=series,
    )


def get_calendar(
    db: Session,
    year: int | None = None,
    month: int | None = None,
    *,
    light: bool = False,
) -> CalendarResponse:
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    # Dashboard hanya butuh count/category; halaman Calendar butuh detail penuh
    if light:
        load_opts = (joinedload(Task.project),)
    else:
        load_opts = (
            joinedload(Task.assignee),
            joinedload(Task.assignees).joinedload(TaskAssignee.user),
            joinedload(Task.project),
        )

    tasks = db.scalars(
        select(Task)
        .options(*load_opts)
        .where(and_(Task.due_date.is_not(None), Task.due_date >= start, Task.due_date <= end))
        .order_by(Task.due_date.asc())
    ).unique().all()

    by_day: dict[date, list[DeadlineItem]] = defaultdict(list)
    for task in tasks:
        item = DeadlineItem(
            id=task.id,
            title=task.title,
            due_date=task.due_date,
            status=task.status,
            category=task.category,
            project_name=task.project.name if task.project else "",
            assignee=UserOut.model_validate(task.assignee) if (not light and task.assignee) else None,
        )
        by_day[task.due_date].append(item)

    days = [
        CalendarDay(date=day, count=len(items), deadlines=items)
        for day, items in sorted(by_day.items())
    ]

    upcoming_tasks = db.scalars(
        select(Task)
        .options(*load_opts)
        .where(and_(Task.due_date.is_not(None), Task.due_date >= today, Task.status != TaskStatus.done))
        .order_by(Task.due_date.asc())
        .limit(8)
    ).unique().all()

    upcoming = [
        DeadlineItem(
            id=t.id,
            title=t.title,
            due_date=t.due_date,
            status=t.status,
            category=t.category,
            project_name=t.project.name if t.project else "",
            assignee=UserOut.model_validate(t.assignee) if t.assignee else None,
        )
        for t in upcoming_tasks
    ]

    return CalendarResponse(year=year, month=month, days=days, upcoming=upcoming)


def get_team_overview(db: Session, limit: int = 5) -> TeamOverview:
    total = (
        db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    )
    users = db.scalars(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.id.asc())
        .limit(limit)
    ).all()
    visible = [UserOut.model_validate(u) for u in users]
    extra = max(0, int(total) - len(visible))
    return TeamOverview(total=int(total), visible=visible, extra=extra)
