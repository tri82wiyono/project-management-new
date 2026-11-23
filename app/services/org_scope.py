"""Phase 4 — Project/Task organizational authorization.

Combines: action permission + organizational scope + membership + assignment.
Leadership is derived from trusted Division/Bidang.leader_user_id rows, never from role names alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import ColumnElement, false

from app.config import get_settings
from app.models.models import (
    Bidang,
    Division,
    Project,
    ProjectOwnerType,
    Task,
    TaskAssignee,
    TeamMember,
    User,
)
from app.services.roles import user_has_permission


@dataclass
class UserOrgContext:
    user_id: int
    is_admin: bool
    led_division_ids: set[int] = field(default_factory=set)
    led_bidang_ids: set[int] = field(default_factory=set)
    primary_bidang_id: int | None = None
    primary_division_id: int | None = None
    member_project_ids: set[int] = field(default_factory=set)
    assigned_project_ids: set[int] = field(default_factory=set)


def org_scope_enforcement_enabled() -> bool:
    """Feature flag. When false, Phase 3 permission-only behavior is preserved.

    Must not be treated as a silent production disable — operators enable after
    classifying legacy projects. Default is False for safe rollout.
    """
    return bool(getattr(get_settings(), "org_scope_enforcement", False))


def load_user_org_context(db: Session, user: User) -> UserOrgContext:
    led_divisions = set(
        db.scalars(select(Division.id).where(Division.leader_user_id == user.id)).all()
    )
    led_bidangs = set(
        db.scalars(select(Bidang.id).where(Bidang.leader_user_id == user.id)).all()
    )
    primary_bidang_id = user.primary_bidang_id
    primary_division_id = None
    if primary_bidang_id:
        primary_division_id = db.scalar(
            select(Bidang.division_id).where(Bidang.id == primary_bidang_id).limit(1)
        )
    member_project_ids = set(
        db.scalars(select(TeamMember.project_id).where(TeamMember.user_id == user.id)).all()
    )
    assigned_project_ids = set(
        db.scalars(
            select(Task.project_id)
            .join(TaskAssignee, TaskAssignee.task_id == Task.id)
            .where(TaskAssignee.user_id == user.id)
        ).all()
    )
    # Include legacy single assignee_id
    assigned_project_ids.update(
        db.scalars(
            select(Task.project_id).where(Task.assignee_id == user.id)
        ).all()
    )
    return UserOrgContext(
        user_id=user.id,
        is_admin=(user.role == "Admin"),
        led_division_ids=led_divisions,
        led_bidang_ids=led_bidangs,
        primary_bidang_id=primary_bidang_id,
        primary_division_id=int(primary_division_id) if primary_division_id else None,
        member_project_ids=member_project_ids,
        assigned_project_ids=assigned_project_ids,
    )


def ownership_summary(project: Project) -> dict:
    owner_type = (project.owner_type or ProjectOwnerType.unassigned.value).strip()
    division = getattr(project, "owner_division", None)
    bidang = getattr(project, "owner_bidang", None)
    classified_at = project.ownership_classified_at
    return {
        "owner_type": owner_type,
        "owner_division_id": project.owner_division_id,
        "owner_bidang_id": project.owner_bidang_id,
        "owner_division_code": division.code if division else "",
        "owner_division_name": division.name if division else "",
        "owner_bidang_code": bidang.code if bidang else "",
        "owner_bidang_name": bidang.name if bidang else "",
        "is_classified": owner_type != ProjectOwnerType.unassigned.value,
        # ISO string for JSON/audit meta safety (datetime is not JSON-serializable).
        "ownership_classified_at": classified_at.isoformat() if classified_at else None,
    }


def validate_and_normalize_ownership(
    db: Session,
    *,
    owner_type: str,
    owner_division_id: int | None,
    owner_bidang_id: int | None,
) -> tuple[str, int | None, int | None]:
    kind = (owner_type or ProjectOwnerType.unassigned.value).strip().lower()
    if kind not in {
        ProjectOwnerType.unassigned.value,
        ProjectOwnerType.division.value,
        ProjectOwnerType.bidang.value,
    }:
        raise ValueError("Tipe kepemilikan project tidak valid")

    if kind == ProjectOwnerType.unassigned.value:
        return kind, None, None

    if kind == ProjectOwnerType.division.value:
        if not owner_division_id:
            raise ValueError("Divisi pemilik wajib dipilih")
        division = db.get(Division, int(owner_division_id))
        if not division:
            raise ValueError("Divisi pemilik tidak ditemukan")
        if not division.is_active:
            raise ValueError("Divisi pemilik tidak aktif")
        return kind, division.id, None

    # bidang
    if not owner_bidang_id:
        raise ValueError("Bidang pemilik wajib dipilih")
    bidang = db.scalar(
        select(Bidang).options(joinedload(Bidang.division)).where(Bidang.id == int(owner_bidang_id)).limit(1)
    )
    if not bidang:
        raise ValueError("Bidang pemilik tidak ditemukan")
    if not bidang.is_active:
        raise ValueError("Bidang pemilik tidak aktif")
    if not bidang.division or not bidang.division.is_active:
        raise ValueError("Divisi induk Bidang tidak aktif")
    # Store parent division for efficient Division-leader scope queries.
    return kind, bidang.division_id, bidang.id


def apply_project_ownership(
    db: Session,
    project: Project,
    *,
    owner_type: str,
    owner_division_id: int | None,
    owner_bidang_id: int | None,
    actor: User | None = None,
) -> Project:
    kind, div_id, bidang_id = validate_and_normalize_ownership(
        db,
        owner_type=owner_type,
        owner_division_id=owner_division_id,
        owner_bidang_id=owner_bidang_id,
    )
    previous = (project.owner_type, project.owner_division_id, project.owner_bidang_id)
    project.owner_type = kind
    project.owner_division_id = div_id
    project.owner_bidang_id = bidang_id
    if previous != (kind, div_id, bidang_id):
        project.ownership_classified_at = datetime.now(timezone.utc)
        project.ownership_classified_by_id = actor.id if actor else None
    return project


def _has_org_ownership(ctx: UserOrgContext, project: Project) -> bool:
    owner_type = (project.owner_type or ProjectOwnerType.unassigned.value).strip()
    if owner_type == ProjectOwnerType.unassigned.value:
        return False
    if owner_type == ProjectOwnerType.division.value:
        return bool(project.owner_division_id and project.owner_division_id in ctx.led_division_ids)
    if owner_type == ProjectOwnerType.bidang.value:
        if project.owner_bidang_id and project.owner_bidang_id in ctx.led_bidang_ids:
            return True
        # Pemimpin Divisi may access Bidang-owned projects under their Division.
        if project.owner_division_id and project.owner_division_id in ctx.led_division_ids:
            return True
    return False


def can_view_project(db: Session, user: User, project: Project, *, ctx: UserOrgContext | None = None) -> bool:
    if not user_has_permission(db, user, "projects.view") and not user_has_permission(
        db, user, "projects.manage"
    ):
        # Still allow if user can view tasks and is assigned — checked separately for tasks.
        if not user_has_permission(db, user, "tasks.view") and not user_has_permission(
            db, user, "tasks.manage"
        ):
            return False

    context = ctx or load_user_org_context(db, user)
    if context.is_admin:
        return True

    if not org_scope_enforcement_enabled():
        # Phase 3 compatibility: permission alone grants global visibility.
        return user_has_permission(db, user, "projects.view") or user_has_permission(
            db, user, "projects.manage"
        )

    # Enforcement ON — Admin already returned. Legacy broad manage does NOT bypass scope.
    if project.id in context.member_project_ids:
        return True
    if project.id in context.assigned_project_ids:
        return True
    if _has_org_ownership(context, project):
        return True
    return False


def can_manage_project(db: Session, user: User, project: Project, *, ctx: UserOrgContext | None = None) -> bool:
    if not (
        user_has_permission(db, user, "projects.manage")
        or user_has_permission(db, user, "projects.update")
    ):
        return False
    return can_view_project(db, user, project, ctx=ctx)


def can_create_project(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "projects.manage") or user_has_permission(
        db, user, "projects.create"
    )


def can_delete_project(db: Session, user: User, project: Project) -> bool:
    # SEC-05 — Admin role hard check retained.
    return user.role == "Admin"


def can_view_task(db: Session, user: User, task: Task, *, ctx: UserOrgContext | None = None) -> bool:
    if not (
        user_has_permission(db, user, "tasks.view")
        or user_has_permission(db, user, "tasks.manage")
    ):
        return False
    context = ctx or load_user_org_context(db, user)
    if context.is_admin:
        return True
    if not org_scope_enforcement_enabled():
        # Phase 3 compatibility: tasks.view|manage alone is global.
        return True
    project = task.project or db.get(Project, task.project_id)
    if not project:
        return False
    # When enforced, task access follows project visibility (membership/assignment/ownership).
    return can_view_project(db, user, project, ctx=context)


def can_manage_task(db: Session, user: User, task: Task, *, ctx: UserOrgContext | None = None) -> bool:
    if not (
        user_has_permission(db, user, "tasks.manage")
        or user_has_permission(db, user, "tasks.update")
        or user_has_permission(db, user, "tasks.assign")
        or user_has_permission(db, user, "tasks.complete")
    ):
        return False
    return can_view_task(db, user, task, ctx=ctx)


def require_project_view(db: Session, user: User, project: Project) -> None:
    if not can_view_project(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found")


def require_project_manage(db: Session, user: User, project: Project) -> None:
    if not can_manage_project(db, user, project):
        raise HTTPException(status_code=403, detail="Tidak berwenang mengubah project ini")


def require_task_view(db: Session, user: User, task: Task) -> None:
    if not can_view_task(db, user, task):
        raise HTTPException(status_code=404, detail="Task not found")


def require_task_manage(db: Session, user: User, task: Task) -> None:
    if not can_manage_task(db, user, task):
        raise HTTPException(status_code=403, detail="Tidak berwenang mengubah task ini")


def visible_project_ids_subquery(db: Session, user: User, *, ctx: UserOrgContext | None = None):
    """Return a selectable of project IDs the user may see, or None meaning unrestricted."""
    context = ctx or load_user_org_context(db, user)
    if context.is_admin:
        return None
    if not org_scope_enforcement_enabled():
        return None

    clauses = []
    if context.member_project_ids:
        clauses.append(Project.id.in_(context.member_project_ids))
    if context.assigned_project_ids:
        clauses.append(Project.id.in_(context.assigned_project_ids))
    if context.led_division_ids:
        clauses.append(
            and_(
                Project.owner_type == ProjectOwnerType.division.value,
                Project.owner_division_id.in_(context.led_division_ids),
            )
        )
        clauses.append(
            and_(
                Project.owner_type == ProjectOwnerType.bidang.value,
                Project.owner_division_id.in_(context.led_division_ids),
            )
        )
    if context.led_bidang_ids:
        clauses.append(
            and_(
                Project.owner_type == ProjectOwnerType.bidang.value,
                Project.owner_bidang_id.in_(context.led_bidang_ids),
            )
        )
    if not clauses:
        return select(Project.id).where(false())
    return select(Project.id).where(or_(*clauses))


def project_visibility_filter(
    db: Session, user: User, *, ctx: UserOrgContext | None = None
) -> ColumnElement[bool] | None:
    """SQLAlchemy filter for Project rows. None = no extra filter (unrestricted)."""
    context = ctx or load_user_org_context(db, user)
    if context.is_admin or not org_scope_enforcement_enabled():
        return None
    subq = visible_project_ids_subquery(db, user, ctx=context)
    if subq is None:
        return None
    return Project.id.in_(subq)


def task_visibility_filter(
    db: Session, user: User, *, ctx: UserOrgContext | None = None
) -> ColumnElement[bool] | None:
    context = ctx or load_user_org_context(db, user)
    if context.is_admin or not org_scope_enforcement_enabled():
        return None
    subq = visible_project_ids_subquery(db, user, ctx=context)
    if subq is None:
        return None
    return Task.project_id.in_(subq)


def scope_status(db: Session, user: User) -> dict:
    ctx = load_user_org_context(db, user)
    unassigned_count = int(
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                or_(
                    Project.owner_type == ProjectOwnerType.unassigned.value,
                    Project.owner_type.is_(None),
                    Project.owner_type == "",
                )
            )
        )
        or 0
    )
    return {
        "enforcement_enabled": org_scope_enforcement_enabled(),
        "is_admin": ctx.is_admin,
        "led_division_ids": sorted(ctx.led_division_ids),
        "led_bidang_ids": sorted(ctx.led_bidang_ids),
        "member_project_count": len(ctx.member_project_ids),
        "unassigned_project_count": unassigned_count,
        "note": (
            "When enforcement is enabled, unclassified projects are visible only to "
            "Administrators and explicit members/assignees."
        ),
    }
