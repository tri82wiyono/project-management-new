from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Role, User
from app.services.audit import write_audit_log
from app.services.auth import require_user
from app.services.roles import (
    PROTECTED_ROLE_CODES,
    duplicate_role,
    ensure_default_roles,
    get_role_by_code,
    invalidate_role_permissions_cache,
    list_roles,
    permission_catalog,
    permission_matrix,
    role_to_dict,
    user_has_permission,
    validate_permissions,
)

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=9999)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class RoleDuplicate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str | None = Field(default=None, max_length=80)


def _require_roles_manage(db: Session, user: User) -> None:
    if not user_has_permission(db, user, "roles.manage"):
        raise HTTPException(status_code=403, detail="Permission roles.manage required")


def _normalize_code(code: str) -> str:
    cleaned = "".join(ch for ch in code.strip() if ch.isalnum() or ch in {"_", "-"})
    if not cleaned:
        raise HTTPException(status_code=400, detail="Kode role tidak valid")
    return cleaned[:40]


def _sanitize_permissions(raw: list[str] | None) -> list[str]:
    try:
        return validate_permissions(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _user_count(db: Session, role_code: str) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == role_code)) or 0)


@router.get("/permissions")
def get_permission_catalog(
    include_reserved: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not (
        user_has_permission(db, user, "roles.manage")
        or user_has_permission(db, user, "roles.view")
        or user_has_permission(db, user, "users.manage")
    ):
        raise HTTPException(status_code=403, detail="Permission required")
    return {"items": permission_catalog(include_reserved=include_reserved)}


@router.get("/matrix")
def get_permission_matrix(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    return permission_matrix(db)


@router.get("")
def get_roles(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    # Active role list can be used by user form; manage permission for full list.
    if not active_only and not user_has_permission(db, user, "roles.manage"):
        if not (
            user_has_permission(db, user, "users.manage")
            or user_has_permission(db, user, "roles.view")
        ):
            raise HTTPException(status_code=403, detail="Permission required")
        active_only = True
    return {
        "items": list_roles(db, active_only=active_only),
        "permissions": permission_catalog(include_reserved=True),
    }


@router.post("")
def create_role(
    payload: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    ensure_default_roles(db)
    code = _normalize_code(payload.code)
    exists = db.scalar(select(Role.id).where(func.lower(Role.code) == code.lower()).limit(1))
    if exists:
        raise HTTPException(status_code=400, detail="Kode role sudah ada")

    perms = _sanitize_permissions(payload.permissions)
    row = Role(
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        permissions=perms,
        is_system=False,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_role_permissions_cache()
    write_audit_log(
        db,
        action="role_created",
        success=True,
        actor=user,
        message=f"Role {row.code} dibuat",
        request=request,
        meta={"role_id": row.id, "code": row.code, "permissions": perms},
    )
    return role_to_dict(row, user_count=0)


@router.put("/{role_id}")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    row = db.get(Role, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")

    before = {
        "name": row.name,
        "description": row.description or "",
        "permissions": list(row.permissions or []),
        "is_active": bool(row.is_active),
        "sort_order": row.sort_order,
    }

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description.strip()
    if payload.permissions is not None:
        perms = _sanitize_permissions(payload.permissions)
        if row.code == "Admin":
            for required in ("roles.manage", "users.manage"):
                if required not in perms:
                    perms.append(required)
        row.permissions = perms
    if payload.is_active is not None:
        if row.code in PROTECTED_ROLE_CODES and not payload.is_active:
            raise HTTPException(status_code=400, detail="Role Admin tidak dapat dinonaktifkan")
        if not payload.is_active:
            in_use = _user_count(db, row.code)
            if in_use:
                raise HTTPException(
                    status_code=400,
                    detail=f"Role masih dipakai {in_use} user. Pindahkan user sebelum menonaktifkan.",
                )
        row.is_active = payload.is_active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order

    db.commit()
    db.refresh(row)
    invalidate_role_permissions_cache()

    after = {
        "name": row.name,
        "description": row.description or "",
        "permissions": list(row.permissions or []),
        "is_active": bool(row.is_active),
        "sort_order": row.sort_order,
    }
    action = "role_updated"
    if before["is_active"] != after["is_active"]:
        action = "role_activated" if after["is_active"] else "role_deactivated"
    elif before["permissions"] != after["permissions"]:
        action = "role_permissions_changed"
    write_audit_log(
        db,
        action=action,
        success=True,
        actor=user,
        message=f"Role {row.code} diubah",
        request=request,
        meta={"role_id": row.id, "code": row.code, "before": before, "after": after},
    )
    return role_to_dict(row, user_count=_user_count(db, row.code))


@router.post("/{role_id}/duplicate")
def duplicate_role_endpoint(
    role_id: int,
    payload: RoleDuplicate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    source = db.get(Role, role_id)
    if not source:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    code = _normalize_code(payload.code)
    try:
        row = duplicate_role(db, source, new_code=code, new_name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit_log(
        db,
        action="role_duplicated",
        success=True,
        actor=user,
        message=f"Role {source.code} digandakan menjadi {row.code}",
        request=request,
        meta={
            "source_role_id": source.id,
            "source_code": source.code,
            "role_id": row.id,
            "code": row.code,
            "permissions": list(row.permissions or []),
        },
    )
    return role_to_dict(row, user_count=0)


@router.get("/{role_id}/users")
def list_role_users(
    role_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not (
        user_has_permission(db, user, "roles.manage")
        or user_has_permission(db, user, "roles.view")
        or user_has_permission(db, user, "users.manage")
    ):
        raise HTTPException(status_code=403, detail="Permission required")
    row = db.get(Role, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    users = db.scalars(select(User).where(User.role == row.code).order_by(User.name.asc())).all()
    return {
        "role": role_to_dict(row, user_count=len(users)),
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "is_active": bool(u.is_active),
                "avatar_url": u.avatar_url,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    row = db.get(Role, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    if row.is_system or row.code in PROTECTED_ROLE_CODES:
        raise HTTPException(status_code=400, detail="Role sistem tidak dapat dihapus")

    in_use = _user_count(db, row.code)
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Role masih dipakai {in_use} user. Pindahkan user ke role lain terlebih dahulu.",
        )

    code = row.code
    role_id_val = row.id
    db.delete(row)
    db.commit()
    invalidate_role_permissions_cache()
    write_audit_log(
        db,
        action="role_deleted",
        success=True,
        actor=user,
        message=f"Role {code} dihapus",
        request=request,
        meta={"role_id": role_id_val, "code": code},
    )
    return {"ok": True, "message": "Role dihapus"}


@router.get("/by-code/{code}")
def get_role(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not (
        user_has_permission(db, user, "roles.manage")
        or user_has_permission(db, user, "roles.view")
        or user_has_permission(db, user, "users.manage")
    ):
        raise HTTPException(status_code=403, detail="Permission required")
    row = get_role_by_code(db, code)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    return role_to_dict(row, user_count=_user_count(db, row.code))
