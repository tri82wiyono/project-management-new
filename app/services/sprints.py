from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.models import Sprint, SprintStatus, Task, TaskAssignee, TaskStatus
from app.schemas.schemas import SprintOut, TaskOut
from app.services.dashboard import _task_out


def sprint_query():
    return select(Sprint).options(
        joinedload(Sprint.project),
        joinedload(Sprint.tasks).joinedload(Task.assignee),
        joinedload(Sprint.tasks).joinedload(Task.assignees).joinedload(TaskAssignee.user),
        joinedload(Sprint.tasks).joinedload(Task.notes),
        joinedload(Sprint.tasks).joinedload(Task.project),
        joinedload(Sprint.tasks).joinedload(Task.sprint),
    )


def compute_sla(sprint: Sprint, today: date | None = None) -> tuple[int | None, bool]:
    """Return (days_left, overdue). days_left can be negative when overdue."""
    today = today or date.today()
    if sprint.status == SprintStatus.done:
        return None, False
    delta = (sprint.end_date - today).days
    return delta, delta < 0


def sync_sprint_status_from_tasks(sprint: Sprint) -> None:
    """Mark sprint done when every assigned task is done; reopen if work resumes."""
    tasks = list(sprint.tasks or [])
    if not tasks:
        if sprint.status == SprintStatus.done:
            sprint.status = SprintStatus.active
        return
    if all(t.status == TaskStatus.done for t in tasks):
        sprint.status = SprintStatus.done
    elif sprint.status == SprintStatus.done:
        sprint.status = SprintStatus.active


def sprint_out(sprint: Sprint, *, include_tasks: bool = False) -> SprintOut:
    tasks = list(sprint.tasks or [])
    done_count = sum(1 for t in tasks if t.status == TaskStatus.done)
    task_count = len(tasks)
    progress = round((done_count / task_count) * 100.0, 1) if task_count else 0.0
    days_left, overdue = compute_sla(sprint)
    task_payload: list[TaskOut] = []
    if include_tasks:
        task_payload = [_task_out(t) for t in sorted(tasks, key=lambda x: x.id)]
    return SprintOut(
        id=sprint.id,
        project_id=sprint.project_id,
        project_name=sprint.project.name if sprint.project else None,
        name=sprint.name,
        goal=sprint.goal,
        status=sprint.status,
        start_date=sprint.start_date,
        end_date=sprint.end_date,
        created_at=sprint.created_at,
        task_count=task_count,
        done_count=done_count,
        progress=progress,
        sla_days_left=days_left,
        sla_overdue=overdue,
        tasks=task_payload,
    )
