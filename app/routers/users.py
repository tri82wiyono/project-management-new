from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.audit import write_audit_log
from app.services.auth import require_admin
from app.services.email import send_welcome_user_email
from app.services import placement as placement_svc
from app.services.placement import PlacementConflictError, PlacementVersionError
from app.services.roles import (
    assert_role_assignment_allowed,
    get_role_by_code,
    is_last_active_admin,
    list_roles,
)
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


class PlacementUpdate(BaseModel):
    bidang_id: int | None = None
    clear: bool = False
    reason: str = Field(default="", max_length=500)
    expected_version: int | None = None
    acknowledge_leadership_conflict: bool = False


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _serialize(db, user: User) -> dict:
    return placement_svc.serialize_user_with_placement(db, user)


def _placement_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlacementConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "code": "leadership_conflict",
                "conflicts": exc.conflicts,
            },
        )
    if isinstance(exc, PlacementVersionError):
        return HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "code": "placement_version_conflict",
                "current_version": exc.current_version,
            },
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("")
def list_users(
    q: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    division_id: int | None = None,
    bidang_id: int | None = None,
    unassigned: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    users = placement_svc.list_users_with_placement(
        db,
        q=q,
        role=role,
        active=active,
        division_id=division_id,
        bidang_id=bidang_id,
        unassigned=unassigned,
    )
    total = db.scalar(select(func.count()).select_from(User)) or 0
    active_count = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    unassigned_count = placement_svc.count_unassigned_users(db)
    return {
        "items": [_serialize(db, u) for u in users],
        "roles": list_roles(db, active_only=True),
        "stats": {
            "total": total,
            "active": active_count,
            "inactive": total - active_count,
            "admins": db.scalar(select(func.count()).select_from(User).where(User.role == "Admin")) or 0,
            "unassigned": unassigned_count,
            "assigned": int(total) - int(unassigned_count),
        },
    }


@router.post("")
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
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
        primary_bidang_id=None,
        placement_version=0,
    )
    db.add(user)
    db.commit()
    user = placement_svc.load_user_with_placement(db, user.id) or user

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
            write_audit_log(
                db,
                action="welcome_email_sent",
                success=True,
                actor=current,
                target=user,
                message=f"Email welcome/password terkirim ke {user.email}",
                request=request,
            )
        except Exception as exc:  # noqa: BLE001
            email_error = str(exc)
            write_audit_log(
                db,
                action="welcome_email_failed",
                success=False,
                actor=current,
                target=user,
                message=f"Gagal kirim email welcome ke {user.email}: {email_error}",
                request=request,
            )

    data = _serialize(db, user)
    data["email_sent"] = email_sent
    data["email_error"] = email_error
    # Always return temp password to admin so support can confirm login
    # even when email delivery is delayed or the user opens an older message.
    data["temporary_password"] = temp_password
    return data


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    user = placement_svc.load_user_with_placement(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize(db, user)


@router.get("/{user_id}/placement-history")
def get_placement_history(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    rows = placement_svc.list_placement_history(db, user_id)
    return {
        "user_id": user_id,
        "items": [placement_svc.history_to_dict(row) for row in rows],
        "total": len(rows),
        "placement": placement_svc.placement_summary(
            placement_svc.load_user_with_placement(db, user_id) or user
        ),
        "leadership": placement_svc.leadership_roles_for_user(db, user_id),
    }


@router.put("/{user_id}/placement")
def update_placement(
    user_id: int,
    payload: PlacementUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> dict:
    user = placement_svc.load_user_with_placement(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # clear=True always unassigns; otherwise bidang_id=null means clear, bidang_id=N assigns/transfers.
    target_bidang_id: int | None = None if payload.clear else payload.bidang_id

    def _audit_placement(summary: dict) -> dict:
        return {
            "bidang_id": summary.get("bidang_id"),
            "bidang_code": summary.get("bidang_code") or "",
            "bidang_name": summary.get("bidang_name") or "",
            "division_id": summary.get("division_id"),
            "division_code": summary.get("division_code") or "",
            "division_name": summary.get("division_name") or "",
            "is_assigned": bool(summary.get("is_assigned")),
            "placement_version": int(summary.get("placement_version") or 0),
            "placement_updated_at": (
                summary["placement_updated_at"].isoformat()
                if summary.get("placement_updated_at") is not None
                else None
            ),
        }

    previous = placement_svc.placement_summary(user)
    try:
        user, history, unchanged = placement_svc.set_user_placement(
            db,
            user,
            bidang_id=target_bidang_id,
            actor=current,
            reason=payload.reason,
            expected_version=payload.expected_version,
            acknowledge_leadership_conflict=payload.acknowledge_leadership_conflict,
        )
    except (PlacementConflictError, PlacementVersionError, ValueError) as exc:
        raise _placement_http_error(exc) from exc

    data = _serialize(db, user)
    data["unchanged"] = unchanged
    if history is not None:
        data["history_entry"] = placement_svc.history_to_dict(history)
        action = history.action
        audit_action = {
            "assign": "user_placement_assigned",
            "transfer": "user_placement_transferred",
            "clear": "user_placement_cleared",
        }.get(action, "user_placement_updated")
        write_audit_log(
            db,
            action=audit_action,
            success=True,
            actor=current,
            target=user,
            message={
                "assign": f"Penempatan awal ke Bidang {history.to_bidang_code}",
                "transfer": (
                    f"Transfer penempatan dari {history.from_bidang_code or '—'} "
                    f"ke {history.to_bidang_code or '—'}"
                ),
                "clear": f"Penempatan organisasi dihapus (sebelumnya {history.from_bidang_code or '—'})",
            }.get(action, "Penempatan organisasi diubah"),
            request=request,
            meta={
                "previous": _audit_placement(previous),
                "new": _audit_placement(data["placement"]),
                "reason": payload.reason or "",
                "placement_version": history.placement_version,
                "leadership_conflict_acknowledged": history.leadership_conflict_acknowledged,
                "action": action,
            },
        )
    return data


@router.put("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    previous_role = user.role

    if payload.email is not None:
        email = _normalize_email(payload.email)
        clash = db.scalar(select(User.id).where(User.email == email, User.id != user_id).limit(1))
        if clash:
            raise HTTPException(status_code=400, detail="Email sudah dipakai user lain")
        user.email = email
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        try:
            role_row = assert_role_assignment_allowed(
                db, target=user, new_role_code=_resolve_role_code(db, payload.role), actor=current
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if user.id == current.id and role_row.code != "Admin" and current.role == "Admin":
            raise HTTPException(status_code=400, detail="Tidak dapat menurunkan role akun sendiri")
        user.role = role_row.code
    if payload.is_active is not None:
        if user.id == current.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")
        if not payload.is_active and is_last_active_admin(db, user):
            raise HTTPException(
                status_code=400,
                detail="Tidak dapat menonaktifkan Administrator terakhir yang aktif",
            )
        user.is_active = payload.is_active
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip()

    db.commit()
    user = placement_svc.load_user_with_placement(db, user.id) or user

    if payload.role is not None and previous_role != user.role:
        write_audit_log(
            db,
            action="user_role_changed",
            success=True,
            actor=current,
            target=user,
            message=f"Role pengguna diubah dari {previous_role} ke {user.role}",
            request=request,
            meta={
                "from_role": previous_role,
                "to_role": user.role,
                "placement_bidang_id": user.primary_bidang_id,
            },
        )
    return _serialize(db, user)


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
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
    user = placement_svc.load_user_with_placement(db, user.id) or user

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
            write_audit_log(
                db,
                action="password_email_sent",
                success=True,
                actor=current,
                target=user,
                message=f"Email reset password terkirim ke {user.email}",
                request=request,
            )
        except Exception as exc:  # noqa: BLE001
            email_error = str(exc)
            write_audit_log(
                db,
                action="password_email_failed",
                success=False,
                actor=current,
                target=user,
                message=f"Gagal kirim email reset password ke {user.email}: {email_error}",
                request=request,
            )

    data = {
        **_serialize(db, user),
        "email_sent": email_sent,
        "email_error": email_error,
        "message": "Password direset. User harus login dengan password sementara.",
        # Always return to admin (email may be delayed / user may open older mail).
        "temporary_password": temp_password,
    }
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
    if is_last_active_admin(db, user):
        raise HTTPException(
            status_code=400,
            detail="Tidak dapat menonaktifkan Administrator terakhir yang aktif",
        )
    user.is_active = False
    db.commit()
    return {"ok": True, "message": "User dinonaktifkan"}
