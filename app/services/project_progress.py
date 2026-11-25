from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Project, ProjectStatus, Task, TaskStatus

STATUS_WEIGHT = {
    TaskStatus.todo: 0.0,
    TaskStatus.in_progress: 40.0,
    TaskStatus.review: 70.0,
    TaskStatus.done: 100.0,
}

RELEASE_MIN_PROGRESS = 100.0


def calculate_progress_from_tasks(tasks: list[Task]) -> float:
    if not tasks:
        return 0.0
    total = sum(STATUS_WEIGHT.get(task.status, 0.0) for task in tasks)
    return round(total / len(tasks), 1)


def status_from_progress(progress: float) -> ProjectStatus:
    """Map task-derived progress to a pipeline stage (used when demoting invalid Release)."""
    pct = float(progress or 0.0)
    if pct <= 0:
        return ProjectStatus.backlog
    if pct < 40:
        return ProjectStatus.dev
    if pct < 60:
        return ProjectStatus.sit
    if pct < 75:
        return ProjectStatus.uat
    if pct < 90:
        return ProjectStatus.to
    if pct < RELEASE_MIN_PROGRESS:
        return ProjectStatus.izin
    return ProjectStatus.release


def release_allowed(progress: float) -> bool:
    return float(progress or 0.0) >= RELEASE_MIN_PROGRESS


def sync_project_status_from_tasks(project: Project, tasks: list[Task], progress: float) -> None:
    """Derive project pipeline stage entirely from task progress.

    Create/edit forms no longer set status; task updates drive backlog → … → release.
    """
    if not tasks:
        project.status = ProjectStatus.backlog
        return
    project.status = status_from_progress(progress)


def recalculate_project_progress(db: Session, project_id: int | None) -> float | None:
    if not project_id:
        return None

    project = db.get(Project, project_id)
    if not project:
        return None

    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    progress = calculate_progress_from_tasks(tasks)
    project.progress = progress
    sync_project_status_from_tasks(project, tasks, progress)
    return project.progress


def reconcile_all_project_progress(db: Session) -> int:
    """Recalc progress + demote invalid Release for every project. Returns count touched."""
    ids = list(db.scalars(select(Project.id)).all())
    for project_id in ids:
        recalculate_project_progress(db, project_id)
    if ids:
        db.commit()
    return len(ids)
