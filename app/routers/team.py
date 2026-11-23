from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Project, TeamMember, User
from app.schemas.schemas import UserOut
from app.services.auth import require_user
from app.services import org_scope
from app.services.roles import user_has_permission

router = APIRouter(prefix="/api/team", tags=["team"])

LEGACY_MUTATION_DISABLED_DETAIL = (
    "Legacy team mutations are disabled. Use /api/users for account administration."
)


def _require_team_directory_access(user: User, db: Session) -> User:
    """Full/active directory for pickers requires assign/manage-level permission.

    View-only users must not receive the organization-wide user list.
    Organization admin pages may use organization.view / users.view.
    """
    allowed = (
        user.role == "Admin"
        or user_has_permission(db, user, "projects.manage")
        or user_has_permission(db, user, "projects.assign")
        or user_has_permission(db, user, "projects.create")
        or user_has_permission(db, user, "projects.update")
        or user_has_permission(db, user, "tasks.manage")
        or user_has_permission(db, user, "tasks.assign")
        or user_has_permission(db, user, "tickets.manage")
        or user_has_permission(db, user, "users.view")
        or user_has_permission(db, user, "users.manage")
        or user_has_permission(db, user, "organization.view")
        or user_has_permission(db, user, "organization.manage")
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Permission required to list team")
    return user


def _to_directory_out(row: User) -> UserOut:
    """Minimal identity for pickers — never expose password/MFA/secrets."""
    return UserOut(
        id=row.id,
        name=row.name,
        email=row.email,
        role=row.role,
        avatar_url=row.avatar_url or "",
        is_active=bool(row.is_active),
    )


@router.get("", response_model=list[UserOut])
def list_team(
    active_only: bool = True,
    q: str | None = Query(default=None, max_length=120),
    project_id: int | None = Query(default=None, ge=1),
    bidang_id: int | None = Query(default=None, ge=1),
    purpose: str = Query(
        default="assign",
        pattern="^(assign|members|bidang)$",
        description="assign=collaboration directory; members=project members; bidang=placement unit",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[UserOut]:
    _require_team_directory_access(user, db)

    stmt = select(User).order_by(User.name.asc(), User.id.asc())
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))

    if purpose == "members":
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id wajib untuk purpose=members")
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        org_scope.require_project_view(db, user, project)
        member_ids = select(TeamMember.user_id).where(TeamMember.project_id == project_id)
        stmt = stmt.where(User.id.in_(member_ids))
    elif purpose == "bidang":
        if not bidang_id:
            raise HTTPException(status_code=400, detail="bidang_id wajib untuk purpose=bidang")
        # Bidang staff list is for org/placement contexts — require org or users permission.
        if not (
            user.role == "Admin"
            or user_has_permission(db, user, "organization.view")
            or user_has_permission(db, user, "organization.manage")
            or user_has_permission(db, user, "users.view")
            or user_has_permission(db, user, "users.manage")
            or user_has_permission(db, user, "users.assign_organization")
        ):
            raise HTTPException(status_code=403, detail="Permission required to list Bidang members")
        stmt = stmt.where(User.primary_bidang_id == bidang_id)
    else:
        # purpose=assign — organization-wide active directory for cross-unit collaboration.
        # Optional project_id: caller must be able to view the project (prevents probing).
        if project_id is not None:
            project = db.get(Project, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            org_scope.require_project_view(db, user, project)
        if bidang_id is not None:
            stmt = stmt.where(User.primary_bidang_id == bidang_id)

    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.email.ilike(like), User.role.ilike(like)))

    rows = list(db.scalars(stmt.limit(500)).all())
    return [_to_directory_out(row) for row in rows]


@router.get("/{user_id}", response_model=UserOut)
def get_member(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> UserOut:
    _require_team_directory_access(user, db)
    member = db.get(User, user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    return _to_directory_out(member)


@router.post("", include_in_schema=False)
def create_member_disabled() -> None:
    """SEC-01: legacy account creation removed; canonical path is /api/users."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_MUTATION_DISABLED_DETAIL)


@router.patch("/{user_id}", include_in_schema=False)
def update_member_disabled(user_id: int) -> None:
    """SEC-02: legacy role/active mass-assignment removed; canonical path is /api/users."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_MUTATION_DISABLED_DETAIL)
