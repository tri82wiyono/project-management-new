from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.models import Project, ProjectStatus, Task, TaskNote, TeamMember, User
from app.schemas.schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectStats,
    ProjectTaskNoteOut,
    ProjectUpdate,
)
from app.services.project_progress import recalculate_project_progress

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _task_count_map(db: Session, project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(Task.project_id, func.count())
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    ).all()
    return {int(pid): int(count) for pid, count in rows}


def _to_out(project: Project, task_count: int = 0) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        pic=project.pic or "",
        status=project.status,
        progress=project.progress,
        color=project.color,
        start_date=project.start_date,
        end_date=project.end_date,
        created_at=project.created_at,
        members=project.members or [],
        task_count=task_count,
    )


def _load_project(db: Session, project_id: int) -> Project:
    project = db.scalar(
        select(Project)
        .options(joinedload(Project.members).joinedload(TeamMember.user))
        .where(Project.id == project_id)
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/stats", response_model=ProjectStats)
def project_stats(db: Session = Depends(get_db)) -> ProjectStats:
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    planning = (
        db.scalar(select(func.count()).select_from(Project).where(Project.status == ProjectStatus.backlog))
        or 0
    )
    in_progress = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.status.in_(
                    [
                        ProjectStatus.dev,
                        ProjectStatus.sit,
                        ProjectStatus.uat,
                        ProjectStatus.to,
                        ProjectStatus.izin,
                    ]
                )
            )
        )
        or 0
    )
    completed = (
        db.scalar(select(func.count()).select_from(Project).where(Project.status == ProjectStatus.release))
        or 0
    )
    return ProjectStats(
        total=total,
        planning=planning,
        in_progress=in_progress,
        completed=completed,
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(
    q: str | None = Query(default=None),
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    filters = []
    if status_filter:
        filters.append(Project.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Project.name.ilike(like),
                Project.description.ilike(like),
                Project.pic.ilike(like),
            )
        )

    count_stmt = select(func.count()).select_from(Project)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.scalar(count_stmt) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    offset = (page - 1) * page_size

    stmt = select(Project).options(joinedload(Project.members).joinedload(TeamMember.user))
    if filters:
        stmt = stmt.where(*filters)
    projects = list(
        db.scalars(
            stmt.order_by(Project.name.asc(), Project.id.asc()).offset(offset).limit(page_size)
        )
        .unique()
        .all()
    )
    counts = _task_count_map(db, [p.id for p in projects])
    return ProjectListResponse(
        items=[_to_out(p, counts.get(p.id, 0)) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    project = _load_project(db, project_id)
    counts = _task_count_map(db, [project.id])
    return _to_out(project, counts.get(project.id, 0))


@router.get("/{project_id}/notes", response_model=list[ProjectTaskNoteOut])
def list_project_notes(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ProjectTaskNoteOut]:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    notes = (
        db.scalars(
            select(TaskNote)
            .join(Task, Task.id == TaskNote.task_id)
            .options(joinedload(TaskNote.author), joinedload(TaskNote.task))
            .where(Task.project_id == project_id)
            .order_by(TaskNote.created_at.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )
    return [
        ProjectTaskNoteOut(
            id=note.id,
            task_id=note.task_id,
            body=note.body,
            kind=note.kind or "problem",
            author_id=note.author_id,
            author_name=note.author.name if note.author else None,
            created_at=note.created_at,
            task_title=note.task.title if note.task else f"Task #{note.task_id}",
            task_status=note.task.status if note.task else None,
        )
        for note in notes
    ]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    project = Project(
        name=payload.name,
        description=payload.description,
        pic=payload.pic or "",
        status=payload.status,
        progress=0,
        color=payload.color,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(project)
    db.flush()

    if payload.member_ids:
        users = db.scalars(select(User).where(User.id.in_(payload.member_ids))).all()
        for user in users:
            db.add(TeamMember(project_id=project.id, user_id=user.id, role=user.role))

    recalculate_project_progress(db, project.id)
    db.commit()
    return get_project(project.id, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectOut:
    project = _load_project(db, project_id)
    data = payload.model_dump(exclude_unset=True)
    member_ids = data.pop("member_ids", None)
    data.pop("progress", None)  # progress is derived from task statuses

    for key, value in data.items():
        setattr(project, key, value)

    if member_ids is not None:
        project.members.clear()
        db.flush()
        users = db.scalars(select(User).where(User.id.in_(member_ids))).all()
        for user in users:
            db.add(TeamMember(project_id=project.id, user_id=user.id, role=user.role))

    recalculate_project_progress(db, project.id)
    db.commit()
    return get_project(project.id, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = _load_project(db, project_id)
    db.delete(project)
    db.commit()
