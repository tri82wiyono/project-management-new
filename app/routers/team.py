from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.schemas.schemas import UserOut
from app.services.auth import require_permission, require_user

router = APIRouter(prefix="/api/team", tags=["team"])


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str
    role: str = "Member"
    avatar_url: str = "https://i.pravatar.cc/150?img=1"


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None


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


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.manage")),
) -> User:
    exists = db.scalar(select(User).where(User.email == payload.email))
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_member(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.manage")),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Team member not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user
