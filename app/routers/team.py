from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.schemas.schemas import UserOut
from app.services.auth import require_user

router = APIRouter(prefix="/api/team", tags=["team"])

LEGACY_MUTATION_DISABLED_DETAIL = (
    "Legacy team mutations are disabled. Use /api/users for account administration."
)


def _require_team_directory_access(user: User, db: Session) -> User:
    """Team directory is for pickers; require a related module permission."""
    from app.services.roles import user_has_permission

    allowed = (
        user.role == "Admin"
        or user_has_permission(db, user, "projects.view")
        or user_has_permission(db, user, "tasks.view")
        or user_has_permission(db, user, "tickets.view")
        or user_has_permission(db, user, "users.view")
        or user_has_permission(db, user, "users.manage")
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Permission required to list team")
    return user


@router.get("", response_model=list[UserOut])
def list_team(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[User]:
    _require_team_directory_access(user, db)
    stmt = select(User).order_by(User.name.asc())
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    return list(db.scalars(stmt).all())


@router.get("/{user_id}", response_model=UserOut)
def get_member(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> User:
    _require_team_directory_access(user, db)
    member = db.get(User, user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    return member


@router.post("", include_in_schema=False)
def create_member_disabled() -> None:
    """SEC-01: legacy account creation removed; canonical path is /api/users."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_MUTATION_DISABLED_DETAIL)


@router.patch("/{user_id}", include_in_schema=False)
def update_member_disabled(user_id: int) -> None:
    """SEC-02: legacy role/active mass-assignment removed; canonical path is /api/users."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_MUTATION_DISABLED_DETAIL)
