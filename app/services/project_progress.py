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


def calculate_progress_from_tasks(tasks: list[Task]) -> float:
    if not tasks:
        return 0.0
    total = sum(STATUS_WEIGHT.get(task.status, 0.0) for task in tasks)
    return round(total / len(tasks), 1)


def sync_project_status_from_tasks(project: Project, tasks: list[Task]) -> None:
    """Promote Backlog → Dev once any module/task leaves To Do."""
    if project.status != ProjectStatus.backlog:
        return
    if any(task.status != TaskStatus.todo for task in tasks):
        project.status = ProjectStatus.dev


def recalculate_project_progress(db: Session, project_id: int | None) -> float | None:
    if not project_id:
        return None

    project = db.get(Project, project_id)
    if not project:
        return None

    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    project.progress = calculate_progress_from_tasks(tasks)
    sync_project_status_from_tasks(project, tasks)
    return project.progress
