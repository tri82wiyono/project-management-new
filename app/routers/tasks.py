from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.models import Project, Task, TaskAssignee, TaskStatus, User
from app.schemas.schemas import TaskCreate, TaskOut, TaskUpdate
from app.services.dashboard import _task_out
from app.services.project_progress import recalculate_project_progress

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_query():
    return select(Task).options(
        joinedload(Task.assignee),
        joinedload(Task.assignees).joinedload(TaskAssignee.user),
        joinedload(Task.project),
    )


def _load_task(db: Session, task_id: int) -> Task:
    task = db.scalar(_task_query().where(Task.id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _normalize_assignee_ids(assignee_ids: list[int] | None, assignee_id: int | None) -> list[int]:
    ids: list[int] = []
    for value in assignee_ids or []:
        if value and value not in ids:
            ids.append(value)
    if assignee_id and assignee_id not in ids:
        ids.insert(0, assignee_id)
    return ids


def _set_task_assignees(db: Session, task: Task, assignee_ids: list[int]) -> None:
    """Replace task assignees via the relationship (avoids delete-orphan races)."""
    ids = _normalize_assignee_ids(assignee_ids, None)
    valid_ids: list[int] = []
    if ids:
        found = {
            u.id: u
            for u in db.scalars(select(User).where(User.id.in_(ids))).all()
        }
        valid_ids = [i for i in ids if i in found]

    # Explicit delete keeps FK rows in sync even if collection wasn't loaded.
    db.execute(delete(TaskAssignee).where(TaskAssignee.task_id == task.id))
    db.expire(task, ["assignees"])
    db.flush()

    for user_id in valid_ids:
        db.add(TaskAssignee(task_id=task.id, user_id=user_id))

    task.assignee_id = valid_ids[0] if valid_ids else None
    db.flush()


@router.get("", response_model=list[TaskOut])
def list_tasks(
    project_id: int | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[TaskOut]:
    stmt = _task_query()
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    tasks = db.scalars(stmt.order_by(Task.created_at.desc())).unique().all()
    return [_task_out(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)) -> TaskOut:
    return _task_out(_load_task(db, task_id))


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    if not db.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    data = payload.model_dump()
    assignee_ids = _normalize_assignee_ids(data.pop("assignee_ids", []), data.get("assignee_id"))
    data["assignee_id"] = assignee_ids[0] if assignee_ids else None

    task = Task(**data)
    if task.status == TaskStatus.done:
        task.completed_at = datetime.now(timezone.utc)
    db.add(task)
    db.flush()
    _set_task_assignees(db, task, assignee_ids)
    recalculate_project_progress(db, task.project_id)
    db.commit()
    return _task_out(_load_task(db, task.id))


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskOut:
    task = _load_task(db, task_id)
    data = payload.model_dump(exclude_unset=True)
    previous_status = task.status
    previous_project_id = task.project_id

    if "project_id" in data and data["project_id"] is not None:
        if not db.get(Project, data["project_id"]):
            raise HTTPException(status_code=404, detail="Project not found")

    assignee_ids = None
    if "assignee_ids" in data:
        assignee_ids = _normalize_assignee_ids(data.pop("assignee_ids"), data.pop("assignee_id", None))
    elif "assignee_id" in data:
        assignee_ids = _normalize_assignee_ids(None, data.pop("assignee_id"))

    for key, value in data.items():
        setattr(task, key, value)

    if "status" in data:
        if task.status == TaskStatus.done and previous_status != TaskStatus.done:
            task.completed_at = datetime.now(timezone.utc)
        elif task.status != TaskStatus.done:
            task.completed_at = None

    db.flush()
    if assignee_ids is not None:
        _set_task_assignees(db, task, assignee_ids)

    recalculate_project_progress(db, task.project_id)
    if previous_project_id != task.project_id:
        recalculate_project_progress(db, previous_project_id)

    db.commit()
    return _task_out(_load_task(db, task.id))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = _load_task(db, task_id)
    project_id = task.project_id
    db.delete(task)
    db.flush()
    recalculate_project_progress(db, project_id)
    db.commit()
