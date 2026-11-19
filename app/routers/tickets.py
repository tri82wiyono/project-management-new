from __future__ import annotations

import math
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import ColumnElement

from app.database import get_db
from app.models.models import (
    Project,
    Task,
    TeamMember,
    Ticket,
    TicketAttachment,
    TicketPic,
    TicketPriority,
    TicketRecordType,
    TicketStatus,
    User,
)
from app.schemas.schemas import (
    TicketAttachmentOut,
    TicketCreate,
    TicketListResponse,
    TicketModulesResponse,
    TicketOut,
    TicketStats,
    TicketUpdate,
    UserOut,
)
from app.services.auth import require_permission
from app.services import ticket_attachments as attach_svc

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
    )


def _build_ticket_number(ticket_id: int, created_at: datetime | None = None) -> str:
    when = created_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return f"TKT-{when.year}-{ticket_id:05d}"


def _to_out(ticket: Ticket) -> TicketOut:
    pics = []
    pic_ids = []
    for link in ticket.pics or []:
        if link.user:
            pics.append(_user_out(link.user))
            pic_ids.append(link.user.id)
    return TicketOut(
        id=ticket.id,
        ticket_number=ticket.ticket_number or _build_ticket_number(ticket.id, ticket.created_at),
        record_type=ticket.record_type,
        project_id=ticket.project_id,
        project_name=ticket.project.name if ticket.project else None,
        module_name=ticket.module_name or "",
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        environment=ticket.environment,
        follow_up_target=ticket.follow_up_target,
        status=ticket.status,
        pic_ids=pic_ids,
        pics=pics,
        attachments=[attach_svc.attachment_to_out(a) for a in (ticket.attachments or [])],
        created_by_id=ticket.created_by_id,
        created_by_name=ticket.created_by.name if ticket.created_by else None,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _unrestricted_ticket_access(user: User) -> bool:
    """Admin/Manager may access all tickets; others are object-scoped."""
    return (user.role or "") in {"Admin", "Manager"}


def _ticket_scope_clause(user: User) -> ColumnElement[bool] | None:
    if _unrestricted_ticket_access(user):
        return None
    pic_ids = select(TicketPic.ticket_id).where(TicketPic.user_id == user.id)
    member_projects = select(TeamMember.project_id).where(TeamMember.user_id == user.id)
    return or_(
        Ticket.created_by_id == user.id,
        Ticket.id.in_(pic_ids),
        Ticket.project_id.in_(member_projects),
    )


def _ensure_ticket_access(db: Session, user: User, ticket: Ticket) -> None:
    if _unrestricted_ticket_access(user):
        return
    if ticket.created_by_id == user.id:
        return
    if any(link.user_id == user.id for link in (ticket.pics or [])):
        return
    is_member = db.scalar(
        select(TeamMember.id).where(
            TeamMember.project_id == ticket.project_id,
            TeamMember.user_id == user.id,
        )
    )
    if is_member:
        return
    raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")


def _ensure_can_delete(user: User, ticket: Ticket) -> None:
    if _unrestricted_ticket_access(user):
        return
    if ticket.created_by_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Hanya pembuat ticket yang dapat menghapus")


def _load_ticket(db: Session, ticket_id: int) -> Ticket:
    ticket = db.scalar(
        select(Ticket)
        .options(
            joinedload(Ticket.project),
            joinedload(Ticket.created_by),
            joinedload(Ticket.pics).joinedload(TicketPic.user),
            joinedload(Ticket.attachments),
        )
        .where(Ticket.id == ticket_id)
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")
    return ticket


def _validate_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=400, detail="Project tidak ditemukan")
    return project


def _set_pics(db: Session, ticket: Ticket, pic_ids: list[int]) -> None:
    unique_ids = sorted({int(uid) for uid in pic_ids if uid})
    if unique_ids:
        found = set(
            db.scalars(select(User.id).where(User.id.in_(unique_ids), User.is_active.is_(True))).all()
        )
        missing = [uid for uid in unique_ids if uid not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"PIC tidak valid: {missing}")
    ticket.pics.clear()
    db.flush()
    for uid in unique_ids:
        ticket.pics.append(TicketPic(user_id=uid))


@router.get("/stats", response_model=TicketStats)
def ticket_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.view")),
) -> TicketStats:
    scope = _ticket_scope_clause(user)
    stmt = select(Ticket.status, func.count()).group_by(Ticket.status)
    if scope is not None:
        stmt = stmt.where(scope)
    rows = db.execute(stmt).all()
    by_status = {row[0]: int(row[1]) for row in rows}
    open_count = by_status.get(TicketStatus.open, 0)
    in_progress = by_status.get(TicketStatus.in_progress, 0)
    resolved = by_status.get(TicketStatus.done, 0) + by_status.get(TicketStatus.closed, 0)
    total = sum(by_status.values())
    return TicketStats(
        total=total,
        open=open_count,
        in_progress=in_progress,
        resolved=resolved,
    )


@router.get("/modules", response_model=TicketModulesResponse)
def list_modules(
    project_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("tickets.view")),
) -> TicketModulesResponse:
    modules: list[str] = []
    seen: set[str] = set()

    def _push(raw: str | None) -> None:
        value = (raw or "").strip()
        if not value:
            return
        key = value.casefold()
        if key in seen:
            return
        seen.add(key)
        modules.append(value)

    if project_id:
        _validate_project(db, project_id)
        # Modules are sub-units of a project, taken from task categories on that project.
        categories = db.scalars(
            select(Task.category)
            .where(
                Task.project_id == project_id,
                Task.category.is_not(None),
                Task.category != "",
            )
            .order_by(Task.category.asc())
            .distinct()
        ).all()
        for category in categories:
            _push(category)
    else:
        # Filter dropdown: modules already used on tickets.
        ticket_mods = db.scalars(
            select(Ticket.module_name)
            .where(Ticket.module_name.is_not(None), Ticket.module_name != "")
            .order_by(Ticket.module_name.asc())
            .distinct()
        ).all()
        for name in ticket_mods:
            _push(name)

    return TicketModulesResponse(project_id=project_id, modules=modules)


@router.get("", response_model=TicketListResponse)
def list_tickets(
    q: str | None = Query(default=None),
    project_id: int | None = Query(default=None, ge=1),
    module_name: str | None = Query(default=None),
    record_type: TicketRecordType | None = Query(default=None),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.view")),
) -> TicketListResponse:
    filters = []
    scope = _ticket_scope_clause(user)
    if scope is not None:
        filters.append(scope)
    if project_id:
        filters.append(Ticket.project_id == project_id)
    if module_name and module_name.strip():
        filters.append(Ticket.module_name == module_name.strip())
    if record_type:
        filters.append(Ticket.record_type == record_type)
    if status_filter:
        filters.append(Ticket.status == status_filter)
    if priority:
        filters.append(Ticket.priority == priority)
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Ticket.ticket_number.ilike(like),
                Ticket.title.ilike(like),
                Ticket.module_name.ilike(like),
                Ticket.description.ilike(like),
            )
        )

    where = filters if filters else [True]
    total = db.scalar(select(func.count()).select_from(Ticket).where(*where)) or 0
    pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(page, pages)

    rows = db.scalars(
        select(Ticket)
        .options(
            joinedload(Ticket.project),
            joinedload(Ticket.created_by),
            joinedload(Ticket.pics).joinedload(TicketPic.user),
            joinedload(Ticket.attachments),
        )
        .where(*where)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    return TicketListResponse(
        items=[_to_out(row) for row in rows],
        total=int(total),
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.view")),
) -> TicketOut:
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    return _to_out(ticket)


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.manage")),
) -> TicketOut:
    _validate_project(db, payload.project_id)
    ticket = Ticket(
        record_type=payload.record_type,
        project_id=payload.project_id,
        module_name=(payload.module_name or "").strip(),
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        environment=payload.environment,
        follow_up_target=payload.follow_up_target,
        status=TicketStatus.open,
        created_by_id=user.id,
    )
    db.add(ticket)
    db.flush()
    ticket.ticket_number = _build_ticket_number(ticket.id, ticket.created_at)
    _set_pics(db, ticket, payload.pic_ids or [])
    db.commit()
    return _to_out(_load_ticket(db, ticket.id))


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.manage")),
) -> TicketOut:
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    data = payload.model_dump(exclude_unset=True)
    pic_ids = data.pop("pic_ids", None)

    if "project_id" in data and data["project_id"] is not None:
        _validate_project(db, data["project_id"])
        ticket.project_id = data["project_id"]
    if "record_type" in data and data["record_type"] is not None:
        ticket.record_type = data["record_type"]
    if "module_name" in data and data["module_name"] is not None:
        ticket.module_name = data["module_name"].strip()
    if "title" in data and data["title"] is not None:
        ticket.title = data["title"].strip()
    if "description" in data:
        ticket.description = data["description"]
    if "priority" in data and data["priority"] is not None:
        ticket.priority = data["priority"]
    if "environment" in data and data["environment"] is not None:
        ticket.environment = data["environment"]
    if "follow_up_target" in data:
        ticket.follow_up_target = data["follow_up_target"]
    if "status" in data and data["status"] is not None:
        ticket.status = data["status"]
    if pic_ids is not None:
        _set_pics(db, ticket, pic_ids)

    db.commit()
    return _to_out(_load_ticket(db, ticket.id))


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.manage")),
) -> Response:
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    _ensure_can_delete(user, ticket)
    db.delete(ticket)
    db.commit()
    attach_svc.delete_ticket_files(ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{ticket_id}/attachments",
    response_model=list[TicketAttachmentOut],
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachments(
    ticket_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.manage")),
) -> list[TicketAttachmentOut]:
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    return await attach_svc.save_uploads(db, ticket_id=ticket_id, files=files, user=user)


@router.get("/{ticket_id}/attachments/{attachment_id}/download")
def download_attachment(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.view")),
):
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    row = db.scalar(
        select(TicketAttachment).where(
            TicketAttachment.id == attachment_id,
            TicketAttachment.ticket_id == ticket_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    path = attach_svc.resolve_file_path(row)
    # Force download; never inline-render untrusted content in the browser.
    safe_name = quote(row.original_name or "attachment")
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.original_name,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_attachment(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tickets.manage")),
) -> Response:
    ticket = _load_ticket(db, ticket_id)
    _ensure_ticket_access(db, user, ticket)
    row = db.scalar(
        select(TicketAttachment).where(
            TicketAttachment.id == attachment_id,
            TicketAttachment.ticket_id == ticket_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    attach_svc.delete_attachment(db, row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
