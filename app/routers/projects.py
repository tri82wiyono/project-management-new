from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from urllib.parse import quote

from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.models import (
    Project,
    ProjectDiscussionAttachment,
    ProjectDocument,
    ProjectStatus,
    Task,
    TaskNote,
    TeamMember,
    User,
)
from app.schemas.schemas import (
    DiscussionListResponse,
    DiscussionMessageOut,
    DiscussionReactionCreate,
    ProjectCreate,
    ProjectDocumentOut,
    ProjectDocumentUrlCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectOwnershipUpdate,
    ProjectStats,
    ProjectTaskNoteOut,
    ProjectUpdate,
)
from app.services.auth import require_permission, require_user
from app.services import project_documents as docs_svc
from app.services import project_discussion as discussion_svc
from app.services.audit import write_audit_log
from app.services import org_scope
from app.services.project_progress import (
    calculate_progress_from_tasks,
    recalculate_project_progress,
    release_allowed,
)
from fastapi import Form, Request
import json

router = APIRouter(prefix="/api/projects", tags=["projects"])


def require_admin_role(user: User = Depends(require_user)) -> User:
    role = (user.role or "").strip().lower()
    if role not in {"admin", "administrator"}:
        raise HTTPException(status_code=403, detail="Hanya Admin yang dapat menghapus project")
    return user


def _task_count_map(db: Session, project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(Task.project_id, func.count())
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    ).all()
    return {int(pid): int(count) for pid, count in rows}


def _to_out(project: Project, task_count: int = 0, *, with_documents: bool = False) -> ProjectOut:
    documents = (
        [docs_svc.document_to_out(d) for d in (project.documents or [])]
        if with_documents
        else []
    )
    ownership = org_scope.ownership_summary(project)
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
        developed_by=getattr(project, "developed_by", None),
        budget=getattr(project, "budget", None),
        owner_type=ownership["owner_type"],
        owner_division_id=ownership["owner_division_id"],
        owner_bidang_id=ownership["owner_bidang_id"],
        created_at=project.created_at,
        members=project.members or [],
        task_count=task_count,
        documents=documents,
        owner_division_code=ownership["owner_division_code"],
        owner_division_name=ownership["owner_division_name"],
        owner_bidang_code=ownership["owner_bidang_code"],
        owner_bidang_name=ownership["owner_bidang_name"],
        is_classified=ownership["is_classified"],
        ownership_classified_at=ownership["ownership_classified_at"],
    )


def _load_project(db: Session, project_id: int, *, with_documents: bool = False) -> Project:
    opts = [
        joinedload(Project.members).joinedload(TeamMember.user),
        joinedload(Project.owner_division),
        joinedload(Project.owner_bidang),
    ]
    if with_documents:
        opts.append(joinedload(Project.documents))
    project = db.scalar(
        select(Project)
        .options(*opts)
        .where(Project.id == project_id)
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/scope-status")
def project_scope_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> dict:
    return org_scope.scope_status(db, user)


@router.get("/unassigned", response_model=ProjectListResponse)
def list_unassigned_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ProjectListResponse:
    """Administrator workflow: classify legacy projects without ownership."""
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Hanya Administrator yang dapat mengelola project belum diklasifikasi")
    filters = [
        or_(
            Project.owner_type == "unassigned",
            Project.owner_type.is_(None),
            Project.owner_type == "",
        )
    ]
    total = db.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
    pages = max(1, (int(total) + page_size - 1) // page_size)
    page = min(page, pages)
    projects = list(
        db.scalars(
            select(Project)
            .options(
                joinedload(Project.members).joinedload(TeamMember.user),
                joinedload(Project.owner_division),
                joinedload(Project.owner_bidang),
            )
            .where(*filters)
            .order_by(Project.name.asc(), Project.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )
    counts = _task_count_map(db, [p.id for p in projects])
    return ProjectListResponse(
        items=[_to_out(p, counts.get(p.id, 0)) for p in projects],
        total=int(total),
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/stats", response_model=ProjectStats)
def project_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> ProjectStats:
    stmt = select(Project.status, func.count()).group_by(Project.status)
    scope = org_scope.project_visibility_filter(db, user)
    if scope is not None:
        stmt = stmt.where(scope)
    rows = db.execute(stmt).all()
    by_status = {row[0]: int(row[1]) for row in rows}
    planning = by_status.get(ProjectStatus.backlog, 0)
    in_progress = sum(
        by_status.get(s, 0)
        for s in (
            ProjectStatus.dev,
            ProjectStatus.sit,
            ProjectStatus.uat,
            ProjectStatus.to,
            ProjectStatus.izin,
        )
    )
    completed = by_status.get(ProjectStatus.release, 0)
    total = sum(by_status.values())
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
    owner_type: str | None = Query(default=None),
    owner_division_id: int | None = Query(default=None),
    owner_bidang_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> ProjectListResponse:
    filters = []
    scope = org_scope.project_visibility_filter(db, user)
    if scope is not None:
        filters.append(scope)
    if status_filter:
        filters.append(Project.status == status_filter)
    if owner_type:
        filters.append(Project.owner_type == owner_type.strip())
    if owner_division_id is not None:
        filters.append(Project.owner_division_id == owner_division_id)
    if owner_bidang_id is not None:
        filters.append(Project.owner_bidang_id == owner_bidang_id)
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

    stmt = select(Project).options(
        joinedload(Project.members).joinedload(TeamMember.user),
        joinedload(Project.owner_division),
        joinedload(Project.owner_bidang),
    )
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
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> ProjectOut:
    project = _load_project(db, project_id, with_documents=True)
    org_scope.require_project_view(db, user, project)
    counts = _task_count_map(db, [project.id])
    return _to_out(project, counts.get(project.id, 0), with_documents=True)


@router.get("/{project_id}/notes", response_model=list[ProjectTaskNoteOut])
def list_project_notes(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> list[ProjectTaskNoteOut]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_view(db, user, project)

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


def _reject_premature_release(db: Session, project_id: int | None, status_value) -> None:
    """Release is only valid when task-derived progress is 100%."""
    if status_value != ProjectStatus.release:
        return
    if not project_id:
        # New project has no modules yet → progress 0
        raise HTTPException(
            status_code=400,
            detail="Status Release hanya boleh jika progress modul 100%. Progress saat ini 0%.",
        )
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    progress = calculate_progress_from_tasks(tasks)
    if not release_allowed(progress):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Status Release hanya boleh jika progress modul 100%. "
                f"Progress saat ini {progress:g}% — pilih Dev/SIT/UAT/TO/Izin."
            ),
        )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("projects.manage")),
) -> ProjectOut:
    if not org_scope.can_create_project(db, current):
        raise HTTPException(status_code=403, detail="Tidak berwenang membuat project")
    _reject_premature_release(db, None, payload.status)
    try:
        owner_type, owner_division_id, owner_bidang_id = org_scope.validate_and_normalize_ownership(
            db,
            owner_type=payload.owner_type,
            owner_division_id=payload.owner_division_id,
            owner_bidang_id=payload.owner_bidang_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    developed_by = (payload.developed_by or "").strip() or None
    if developed_by and developed_by not in {"internal", "vendor", "blanket_mandays"}:
        raise HTTPException(status_code=400, detail="Nilai developed_by tidak valid")

    project = Project(
        name=payload.name,
        description=payload.description,
        pic=payload.pic or "",
        status=payload.status,
        progress=0,
        color=payload.color,
        start_date=payload.start_date,
        end_date=payload.end_date,
        developed_by=developed_by,
        budget=payload.budget,
        owner_type=owner_type,
        owner_division_id=owner_division_id,
        owner_bidang_id=owner_bidang_id,
    )
    if owner_type != "unassigned":
        from datetime import datetime, timezone

        project.ownership_classified_at = datetime.now(timezone.utc)
        project.ownership_classified_by_id = current.id
    db.add(project)
    db.flush()

    if payload.member_ids:
        users = db.scalars(select(User).where(User.id.in_(payload.member_ids))).all()
        for member in users:
            if not member.is_active:
                continue
            db.add(TeamMember(project_id=project.id, user_id=member.id, role=member.role))

    recalculate_project_progress(db, project.id)
    db.commit()
    loaded = _load_project(db, project.id)
    counts = _task_count_map(db, [loaded.id])
    write_audit_log(
        db,
        action="project_created",
        success=True,
        actor=current,
        message=f"Project {loaded.name} dibuat",
        request=request,
        meta={
            "project_id": loaded.id,
            "owner_type": loaded.owner_type,
            "owner_division_id": loaded.owner_division_id,
            "owner_bidang_id": loaded.owner_bidang_id,
            "member_ids": payload.member_ids,
        },
    )
    return _to_out(loaded, counts.get(loaded.id, 0))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("projects.manage")),
) -> ProjectOut:
    project = _load_project(db, project_id)
    org_scope.require_project_manage(db, current, project)
    data = payload.model_dump(exclude_unset=True)
    member_ids = data.pop("member_ids", None)
    data.pop("progress", None)  # progress is derived from task statuses
    ownership_keys = {"owner_type", "owner_division_id", "owner_bidang_id"}
    ownership_touch = any(k in data for k in ownership_keys)
    owner_type = data.pop("owner_type", None)
    owner_division_id = data.pop("owner_division_id", None)
    owner_bidang_id = data.pop("owner_bidang_id", None)

    if "status" in data:
        _reject_premature_release(db, project.id, data["status"])

    if "developed_by" in data:
        developed_by = (data.get("developed_by") or "").strip() or None
        if developed_by and developed_by not in {"internal", "vendor", "blanket_mandays"}:
            raise HTTPException(status_code=400, detail="Nilai developed_by tidak valid")
        data["developed_by"] = developed_by

    for key, value in data.items():
        setattr(project, key, value)

    if ownership_touch:
        try:
            org_scope.apply_project_ownership(
                db,
                project,
                owner_type=owner_type if owner_type is not None else (project.owner_type or "unassigned"),
                owner_division_id=owner_division_id if "owner_division_id" in payload.model_fields_set else project.owner_division_id,
                owner_bidang_id=owner_bidang_id if "owner_bidang_id" in payload.model_fields_set else project.owner_bidang_id,
                actor=current,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    previous_member_ids = [m.user_id for m in (project.members or [])]
    if member_ids is not None:
        project.members.clear()
        db.flush()
        users = db.scalars(select(User).where(User.id.in_(member_ids))).all()
        for member in users:
            if not member.is_active:
                continue
            db.add(TeamMember(project_id=project.id, user_id=member.id, role=member.role))

    recalculate_project_progress(db, project.id)
    db.commit()
    loaded = _load_project(db, project.id)
    counts = _task_count_map(db, [loaded.id])
    if member_ids is not None and sorted(previous_member_ids) != sorted(member_ids):
        write_audit_log(
            db,
            action="project_membership_changed",
            success=True,
            actor=current,
            message=f"Keanggotaan project {loaded.name} diubah",
            request=request,
            meta={
                "project_id": loaded.id,
                "from_member_ids": previous_member_ids,
                "to_member_ids": member_ids,
            },
        )
    return _to_out(loaded, counts.get(loaded.id, 0))


@router.put("/{project_id}/ownership", response_model=ProjectOut)
def classify_project_ownership(
    project_id: int,
    payload: ProjectOwnershipUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_user),
) -> ProjectOut:
    """Administrator-only classification of legacy / unassigned projects."""
    if current.role != "Admin":
        raise HTTPException(status_code=403, detail="Hanya Administrator yang dapat mengklasifikasi kepemilikan project")
    project = _load_project(db, project_id)
    before = org_scope.ownership_summary(project)
    try:
        org_scope.apply_project_ownership(
            db,
            project,
            owner_type=payload.owner_type,
            owner_division_id=payload.owner_division_id,
            owner_bidang_id=payload.owner_bidang_id,
            actor=current,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    loaded = _load_project(db, project.id)
    after = org_scope.ownership_summary(loaded)
    write_audit_log(
        db,
        action="project_ownership_classified",
        success=True,
        actor=current,
        message=f"Kepemilikan project {loaded.name} diklasifikasi",
        request=request,
        meta={"project_id": loaded.id, "before": before, "after": after},
    )
    counts = _task_count_map(db, [loaded.id])
    return _to_out(loaded, counts.get(loaded.id, 0))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_role),
) -> None:
    project = _load_project(db, project_id)
    if not org_scope.can_delete_project(db, user, project):
        raise HTTPException(status_code=403, detail="Hanya Admin yang dapat menghapus project")
    db.delete(project)
    db.commit()
    docs_svc.delete_project_files(project_id)


@router.get("/{project_id}/documents", response_model=list[ProjectDocumentOut])
def list_project_documents(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> list[ProjectDocumentOut]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_view(db, user, project)
    return docs_svc.list_documents(db, project_id)


@router.post("/{project_id}/documents", response_model=list[ProjectDocumentOut], status_code=status.HTTP_201_CREATED)
async def upload_project_documents(
    project_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.manage")),
) -> list[ProjectDocumentOut]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_manage(db, user, project)
    return await docs_svc.save_uploads(db, project_id=project_id, files=files, user=user)


@router.post(
    "/{project_id}/documents/url",
    response_model=ProjectDocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_project_document_url(
    project_id: int,
    payload: ProjectDocumentUrlCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.manage")),
) -> ProjectDocumentOut:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_manage(db, user, project)
    return docs_svc.save_url(
        db,
        project_id=project_id,
        url=payload.url,
        title=payload.title,
        user=user,
    )


@router.get("/{project_id}/documents/{document_id}/download")
def download_project_document(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_view(db, user, project)
    doc = db.scalar(
        select(ProjectDocument).where(
            ProjectDocument.id == document_id,
            ProjectDocument.project_id == project_id,
        )
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    if (doc.kind or "file") == "url" and doc.external_url:
        return RedirectResponse(url=doc.external_url, status_code=302)
    path = docs_svc.resolve_file_path(doc)
    safe_name = quote(doc.original_name or "document")
    return FileResponse(
        path=path,
        filename=doc.original_name,
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{project_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_document(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.manage")),
) -> None:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_manage(db, user, project)
    doc = db.scalar(
        select(ProjectDocument).where(
            ProjectDocument.id == document_id,
            ProjectDocument.project_id == project_id,
        )
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    docs_svc.delete_document(db, doc)


def _require_project_for_discussion(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_scope.require_project_view(db, user, project)
    return project


@router.get("/{project_id}/discussion", response_model=DiscussionListResponse)
def list_project_discussion(
    project_id: int,
    after_id: int | None = Query(default=None),
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> DiscussionListResponse:
    _require_project_for_discussion(db, user, project_id)
    return discussion_svc.list_messages(
        db,
        project_id=project_id,
        current_user_id=user.id,
        after_id=after_id,
        before_id=before_id,
        limit=limit,
    )


@router.post(
    "/{project_id}/discussion",
    response_model=DiscussionMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_project_discussion(
    project_id: int,
    body: str = Form(default=""),
    parent_id: str | None = Form(default=None),
    mention_ids: str = Form(default="[]"),
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> DiscussionMessageOut:
    _require_project_for_discussion(db, user, project_id)
    parsed_parent: int | None = None
    if parent_id not in (None, ""):
        try:
            parsed_parent = int(parent_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="parent_id tidak valid") from None
    try:
        parsed_mentions = json.loads(mention_ids or "[]")
        if not isinstance(parsed_mentions, list):
            raise ValueError("mention_ids must be a list")
        mention_list = [int(x) for x in parsed_mentions]
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Format mention_ids tidak valid") from None
    return await discussion_svc.create_message(
        db,
        project_id=project_id,
        author=user,
        body=body,
        parent_id=parsed_parent,
        mention_ids=mention_list,
        files=files or [],
    )


@router.delete("/{project_id}/discussion/{message_id}", response_model=DiscussionMessageOut)
def delete_project_discussion_message(
    project_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> DiscussionMessageOut:
    _require_project_for_discussion(db, user, project_id)
    can_manage = org_scope.can_manage_project(db, user, db.get(Project, project_id))
    return discussion_svc.soft_delete_message(
        db,
        project_id=project_id,
        message_id=message_id,
        actor=user,
        can_manage=can_manage,
    )


@router.post(
    "/{project_id}/discussion/{message_id}/reactions",
    response_model=DiscussionMessageOut,
)
def react_project_discussion_message(
    project_id: int,
    message_id: int,
    payload: DiscussionReactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> DiscussionMessageOut:
    _require_project_for_discussion(db, user, project_id)
    return discussion_svc.toggle_reaction(
        db,
        project_id=project_id,
        message_id=message_id,
        user=user,
        emoji=payload.emoji,
    )


@router.get("/{project_id}/discussion/attachments/{attachment_id}")
def download_discussion_attachment(
    project_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
):
    _require_project_for_discussion(db, user, project_id)
    att = db.get(ProjectDiscussionAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    message = discussion_svc.get_message(db, project_id, att.message_id)
    if not message or message.project_id != project_id:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    path = discussion_svc.resolve_attachment_path(att, project_id)
    safe_name = quote(att.original_name or "attachment")
    inline = (att.kind or "") == "image"
    return FileResponse(
        path=path,
        filename=att.original_name,
        media_type=att.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{safe_name}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
