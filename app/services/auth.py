from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.models import User
from app.services.security import hash_password, verify_password


def ensure_default_admin(db: Session) -> User | None:
    settings = get_settings()
    existing_admin = db.scalar(
        select(User).where(User.email == settings.default_admin_email).limit(1)
    )
    if existing_admin:
        if not existing_admin.password_hash:
            existing_admin.password_hash = hash_password(settings.default_admin_password)
            existing_admin.role = "Admin"
            existing_admin.is_active = True
            db.commit()
            db.refresh(existing_admin)
        return existing_admin

    any_with_password = db.scalar(select(User.id).where(User.password_hash.is_not(None)).limit(1))
    if any_with_password:
        return None

    admin = User(
        name=settings.default_admin_name,
        email=settings.default_admin_email,
        role="Admin",
        avatar_url="https://api.dicebear.com/7.x/initials/svg?seed=Admin&backgroundColor=453a82",
        is_active=True,
        password_hash=hash_password(settings.default_admin_password),
        must_change_password=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def get_user_by_email(db: Session, email: str) -> User | None:
    from sqlalchemy import func

    normalized = email.strip().lower()
    return db.scalar(select(User).where(func.lower(User.email) == normalized).limit(1))


def lockout_remaining_minutes(user: User) -> int:
    if not user.locked_until:
        return 0
    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    remaining = locked_until - now
    if remaining.total_seconds() <= 0:
        return 0
    return max(1, int((remaining.total_seconds() + 59) // 60))


def is_locked(user: User) -> bool:
    return lockout_remaining_minutes(user) > 0


def register_failed_login(db: Session, user: User) -> None:
    from app.services.security_settings import get_or_create_security_settings

    policy = get_or_create_security_settings(db)
    max_fails = max(1, int(policy.max_failed_logins or 6))
    lock_mins = max(1, int(policy.lockout_minutes or 30))

    user.failed_login_count = int(user.failed_login_count or 0) + 1
    if user.failed_login_count >= max_fails:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lock_mins)
        user.failed_login_count = 0
    db.commit()


def register_successful_login(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def authenticate_user(db: Session, email: str, password: str, *, complete_login: bool = True) -> User:
    user = get_user_by_email(db, email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun nonaktif. Hubungi administrator.")
    if is_locked(user):
        mins = lockout_remaining_minutes(user)
        raise HTTPException(
            status_code=423,
            detail=(
                f"Akun terkunci sementara karena terlalu banyak percobaan gagal. "
                f"Coba lagi dalam {mins} menit."
            ),
        )
    if not verify_password(password, user.password_hash):
        register_failed_login(db, user)
        if is_locked(user):
            mins = lockout_remaining_minutes(user)
            raise HTTPException(
                status_code=423,
                detail=(
                    f"Akun terkunci sementara karena terlalu banyak percobaan gagal. "
                    f"Coba lagi dalam {mins} menit."
                ),
            )
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if complete_login:
        register_successful_login(db, user)
    return user


def set_session_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["user_name"] = user.name
    request.session["user_email"] = user.email
    request.session["user_role"] = user.role
    request.session["must_change_password"] = bool(user.must_change_password)
    request.session["authenticated_at"] = datetime.now(timezone.utc).isoformat()


def set_pending_mfa(request: Request, user: User) -> None:
    request.session.clear()
    request.session["pending_mfa_user_id"] = user.id


def get_pending_mfa_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("pending_mfa_user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active or not user.mfa_enabled:
        request.session.pop("pending_mfa_user_id", None)
        return None
    return user


def set_pending_device(request: Request, user: User) -> None:
    # Keep only device-pending marker (no authenticated session yet)
    request.session.clear()
    request.session["pending_device_user_id"] = user.id


def get_pending_device_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("pending_device_user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.pop("pending_device_user_id", None)
        return None
    return user


def clear_session(request: Request) -> None:
    request.session.clear()


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        clear_session(request)
        return None
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
    from app.services.roles import user_has_permission

    if not user_has_permission(db, user, "users.manage") and user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_permission(permission: str):
    def _dependency(user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
        from app.services.roles import user_has_permission

        if not user_has_permission(db, user, permission):
            raise HTTPException(status_code=403, detail=f"Permission {permission} required")
        return user

    return _dependency
