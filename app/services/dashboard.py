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
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    completed_tasks = (
        db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.done)) or 0
    )
    in_progress = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_([TaskStatus.in_progress, TaskStatus.review]))
        )
        or 0
    )

    prev_start, curr_start, now = _period_bounds(30)

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

    done_with_due = db.scalars(
        select(Task).where(and_(Task.status == TaskStatus.done, Task.due_date.is_not(None)))
    ).all()
    on_time = 0
    for task in done_with_due:
        if task.completed_at and task.due_date and task.completed_at.date() <= task.due_date:
            on_time += 1
    on_time_delivery = round((on_time / len(done_with_due)) * 100, 1) if done_with_due else 0.0

    # previous on-time: completed in previous window
    prev_done = [
        t
        for t in done_with_due
        if t.completed_at and prev_start <= t.completed_at < curr_start and t.due_date
    ]
    prev_on_time = sum(
        1 for t in prev_done if t.completed_at and t.completed_at.date() <= t.due_date
    )
    prev_on_time_pct = round((prev_on_time / len(prev_done)) * 100, 1) if prev_done else 0.0

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


def get_kanban(db: Session, project_id: int | None = None) -> KanbanBoard:
    stmt = select(Task).options(
        joinedload(Task.assignee),
        joinedload(Task.assignees).joinedload(TaskAssignee.user),
        joinedload(Task.project),
        joinedload(Task.notes),
    )
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    tasks = db.scalars(stmt.order_by(Task.created_at.desc())).unique().all()

    grouped: dict[TaskStatus, list[Task]] = {status: [] for status in TaskStatus}
    for task in tasks:
        grouped[task.status].append(task)

    columns = [
        KanbanColumn(
            status=status,
            label=STATUS_LABELS[status],
            count=len(grouped[status]),
            tasks=[_task_out(t) for t in grouped[status]],
        )
        for status in TaskStatus
    ]
    return KanbanBoard(columns=columns)


def get_timeline(db: Session) -> list[TimelineItem]:
    projects = db.scalars(
        select(Project).order_by(Project.start_date.asc(), Project.name.asc())
    ).all()
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


def get_calendar(db: Session, year: int | None = None, month: int | None = None) -> CalendarResponse:
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    tasks = db.scalars(
        select(Task)
        .options(
            joinedload(Task.assignee),
            joinedload(Task.assignees).joinedload(TaskAssignee.user),
            joinedload(Task.project),
        )
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
            assignee=UserOut.model_validate(task.assignee) if task.assignee else None,
        )
        by_day[task.due_date].append(item)

    days = [
        CalendarDay(date=day, count=len(items), deadlines=items)
        for day, items in sorted(by_day.items())
    ]

    upcoming_tasks = db.scalars(
        select(Task)
        .options(
            joinedload(Task.assignee),
            joinedload(Task.assignees).joinedload(TaskAssignee.user),
            joinedload(Task.project),
        )
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
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id.asc())).all()
    visible = [UserOut.model_validate(u) for u in users[:limit]]
    extra = max(0, len(users) - limit)
    return TeamOverview(total=len(users), visible=visible, extra=extra)
