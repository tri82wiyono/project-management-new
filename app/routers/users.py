from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.auth import require_admin
from app.services.email import send_welcome_user_email
from app.services.roles import get_role_by_code, list_roles
from app.services.security import default_avatar, generate_temp_password, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _resolve_role_code(db, role_code: str | None, *, fallback: str = "Member") -> str:
    code = (role_code or fallback).strip()
    role = get_role_by_code(db, code)
    if not role or not role.is_active:
        fallback_role = get_role_by_code(db, fallback)
        if fallback_role and fallback_role.is_active:
            return fallback_role.code
        raise HTTPException(status_code=400, detail="Role tidak valid atau nonaktif")
    return role.code


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=180)
    role: str = Field(default="Member", max_length=80)
    is_active: bool = True
    send_email: bool = True
    temporary_password: str | None = Field(default=None, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=180)
    role: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=255)


class ResetPasswordRequest(BaseModel):
    send_email: bool = True
    temporary_password: str | None = Field(default=None, max_length=128)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _serialize(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "must_change_password": bool(user.must_change_password),
        "has_password": bool(user.password_hash),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "locked_until": user.locked_until,
    }


@router.get("")
def list_users(
    q: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    stmt = select(User).order_by(User.name.asc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.email.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    users = db.scalars(stmt).all()
    total = db.scalar(select(func.count()).select_from(User)) or 0
    active_count = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    return {
        "items": [_serialize(u) for u in users],
        "roles": list_roles(db, active_only=True),
        "stats": {
            "total": total,
            "active": active_count,
            "inactive": total - active_count,
            "admins": db.scalar(select(func.count()).select_from(User).where(User.role == "Admin")) or 0,
        },
    }


@router.post("")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    email = _normalize_email(payload.email)
    role = _resolve_role_code(db, payload.role)
    exists = db.scalar(select(User.id).where(User.email == email).limit(1))
    if exists:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    temp_password = payload.temporary_password or generate_temp_password()
    user = User(
        name=payload.name.strip(),
        email=email,
        role=role,
        avatar_url=default_avatar(payload.name.strip()),
        is_active=payload.is_active,
        password_hash=hash_password(temp_password),
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    email_sent = False
    email_error = None
    if payload.send_email:
        try:
            send_welcome_user_email(
                db,
                to_email=user.email,
                name=user.name,
                temporary_password=temp_password,
            )
            email_sent = True
        except Exception as exc:  # noqa: BLE001
            email_error = str(exc)

    data = _serialize(user)
    data["email_sent"] = email_sent
    data["email_error"] = email_error
    # Only reveal temp password when email failed (admin must copy manually).
    if not email_sent:
        data["temporary_password"] = temp_password
    return data


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize(user)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None:
        email = _normalize_email(payload.email)
        clash = db.scalar(select(User.id).where(User.email == email, User.id != user_id).limit(1))
        if clash:
            raise HTTPException(status_code=400, detail="Email sudah dipakai user lain")
        user.email = email
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        new_role = _resolve_role_code(db, payload.role)
        if user.id == current.id and new_role != "Admin" and current.role == "Admin":
            raise HTTPException(status_code=400, detail="Tidak dapat menurunkan role akun sendiri")
        user.role = new_role
    if payload.is_active is not None:
        if user.id == current.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")
        user.is_active = payload.is_active
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip()

    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = payload.temporary_password or generate_temp_password()
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)

    email_sent = False
    email_error = None
    if payload.send_email:
        try:
            send_welcome_user_email(
                db,
                to_email=user.email,
                name=user.name,
                temporary_password=temp_password,
            )
            email_sent = True
        except Exception as exc:  # noqa: BLE001
            email_error = str(exc)

    data = {
        **_serialize(user),
        "email_sent": email_sent,
        "email_error": email_error,
        "message": "Password direset. User harus login dengan password sementara.",
    }
    if not email_sent:
        data["temporary_password"] = temp_password
    return data


@router.delete("/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus akun sendiri")
    user.is_active = False
    db.commit()
    return {"ok": True, "message": "User dinonaktifkan"}
