from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Project, Sprint, SprintStatus, Task, User
from app.schemas.schemas import SprintCreate, SprintOut, SprintTaskIds, SprintUpdate
from app.services.auth import require_any_permission
from app.services import org_scope
from app.services.sprints import sprint_out, sprint_query, sync_sprint_status_from_tasks

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


def _load_sprint(db: Session, sprint_id: int) -> Sprint:
    sprint = db.scalar(sprint_query().where(Sprint.id == sprint_id))
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


@router.get("", response_model=list[SprintOut])
def list_sprints(
    project_id: int | None = None,
    status_filter: SprintStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.view", "tasks.view")),
) -> list[SprintOut]:
    stmt = sprint_query()
    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        org_scope.require_project_view(db, user, project)
        stmt = stmt.where(Sprint.project_id == project_id)
    else:
        visible = org_scope.project_visibility_filter(db, user)
        if visible is not None:
            stmt = stmt.join(Project, Project.id == Sprint.project_id).where(visible)
    if status_filter:
        stmt = stmt.where(Sprint.status == status_filter)
    sprints = db.scalars(stmt.order_by(Sprint.start_date.desc(), Sprint.id.desc())).unique().all()
    return [sprint_out(s, include_tasks=False) for s in sprints]


@router.get("/{sprint_id}", response_model=SprintOut)
def get_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.view", "tasks.view")),
) -> SprintOut:
    sprint = _load_sprint(db, sprint_id)
    org_scope.require_project_view(db, user, sprint.project)
    return sprint_out(sprint, include_tasks=True)


@router.post("", response_model=SprintOut, status_code=status.HTTP_201_CREATED)
def create_sprint(
    payload: SprintCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.manage", "tasks.manage")),
) -> SprintOut:
    project = db.get(Project, payload.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_view(db, user, project)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="Tanggal akhir sprint harus setelah tanggal mulai")

    sprint = Sprint(
        project_id=payload.project_id,
        name=payload.name.strip(),
        goal=(payload.goal or "").strip() or None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status or SprintStatus.planned,
    )
    db.add(sprint)
    db.flush()

    if payload.task_ids:
        tasks = list(
            db.scalars(
                select(Task).where(
                    Task.id.in_(payload.task_ids),
                    Task.project_id == payload.project_id,
                )
            ).all()
        )
        for task in tasks:
            task.sprint_id = sprint.id
        db.flush()
        sync_sprint_status_from_tasks(sprint)

    db.commit()
    return sprint_out(_load_sprint(db, sprint.id), include_tasks=True)


@router.patch("/{sprint_id}", response_model=SprintOut)
def update_sprint(
    sprint_id: int,
    payload: SprintUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.manage", "tasks.manage")),
) -> SprintOut:
    sprint = _load_sprint(db, sprint_id)
    org_scope.require_project_view(db, user, sprint.project)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "goal" in data and data["goal"] is not None:
        data["goal"] = data["goal"].strip() or None
    start = data.get("start_date", sprint.start_date)
    end = data.get("end_date", sprint.end_date)
    if end < start:
        raise HTTPException(status_code=400, detail="Tanggal akhir sprint harus setelah tanggal mulai")
    for key, value in data.items():
        setattr(sprint, key, value)
    sync_sprint_status_from_tasks(sprint)
    db.commit()
    return sprint_out(_load_sprint(db, sprint.id), include_tasks=True)


@router.post("/{sprint_id}/tasks", response_model=SprintOut)
def add_tasks_to_sprint(
    sprint_id: int,
    payload: SprintTaskIds,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.manage", "tasks.manage")),
) -> SprintOut:
    sprint = _load_sprint(db, sprint_id)
    org_scope.require_project_view(db, user, sprint.project)
    tasks = list(
        db.scalars(
            select(Task).where(
                Task.id.in_(payload.task_ids),
                Task.project_id == sprint.project_id,
            )
        ).all()
    )
    if not tasks:
        raise HTTPException(status_code=400, detail="Tidak ada task valid untuk project ini")
    for task in tasks:
        task.sprint_id = sprint.id
    db.flush()
    sprint = _load_sprint(db, sprint_id)
    sync_sprint_status_from_tasks(sprint)
    db.commit()
    return sprint_out(_load_sprint(db, sprint_id), include_tasks=True)


@router.delete("/{sprint_id}/tasks/{task_id}", response_model=SprintOut)
def remove_task_from_sprint(
    sprint_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.manage", "tasks.manage")),
) -> SprintOut:
    sprint = _load_sprint(db, sprint_id)
    org_scope.require_project_view(db, user, sprint.project)
    task = db.get(Task, task_id)
    if not task or task.sprint_id != sprint.id:
        raise HTTPException(status_code=404, detail="Task tidak ada di sprint ini")
    task.sprint_id = None
    db.flush()
    sprint = _load_sprint(db, sprint_id)
    sync_sprint_status_from_tasks(sprint)
    db.commit()
    return sprint_out(_load_sprint(db, sprint_id), include_tasks=True)


@router.delete("/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("sprints.manage", "tasks.manage")),
) -> Response:
    sprint = _load_sprint(db, sprint_id)
    org_scope.require_project_view(db, user, sprint.project)
    for task in list(sprint.tasks or []):
        task.sprint_id = None
    db.delete(sprint)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
