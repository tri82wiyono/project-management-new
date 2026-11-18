from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Role, User
from app.services.auth import require_user
from app.services.roles import (
    ensure_default_roles,
    get_role_by_code,
    list_roles,
    permission_catalog,
    role_to_dict,
    user_has_permission,
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


def _require_roles_manage(db: Session, user: User) -> None:
    if not user_has_permission(db, user, "roles.manage"):
        raise HTTPException(status_code=403, detail="Permission roles.manage required")


def _normalize_code(code: str) -> str:
    cleaned = "".join(ch for ch in code.strip() if ch.isalnum() or ch in {"_", "-"})
    if not cleaned:
        raise HTTPException(status_code=400, detail="Kode role tidak valid")
    return cleaned[:40]


def _sanitize_permissions(raw: list[str] | None) -> list[str]:
    allowed = {item["key"] for item in permission_catalog()}
    values = []
    for item in raw or []:
        key = str(item).strip()
        if key in allowed and key not in values:
            values.append(key)
    return values


@router.get("/permissions")
def get_permission_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    return {"items": permission_catalog()}


@router.get("")
def get_roles(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    # Active role list can be used by user form; manage permission for full list.
    if not active_only and not user_has_permission(db, user, "roles.manage"):
        if not user_has_permission(db, user, "users.manage"):
            raise HTTPException(status_code=403, detail="Permission required")
        active_only = True
    return {"items": list_roles(db, active_only=active_only), "permissions": permission_catalog()}


@router.post("")
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    ensure_default_roles(db)
    code = _normalize_code(payload.code)
    exists = db.scalar(select(Role.id).where(func.lower(Role.code) == code.lower()).limit(1))
    if exists:
        raise HTTPException(status_code=400, detail="Kode role sudah ada")

    row = Role(
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        permissions=_sanitize_permissions(payload.permissions),
        is_system=False,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return role_to_dict(row, user_count=0)


@router.put("/{role_id}")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    row = db.get(Role, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description.strip()
    if payload.permissions is not None:
        perms = _sanitize_permissions(payload.permissions)
        if row.code == "Admin" and "roles.manage" not in perms:
            perms.append("roles.manage")
        if row.code == "Admin" and "users.manage" not in perms:
            perms.append("users.manage")
        row.permissions = perms
    if payload.is_active is not None:
        if row.is_system and row.code == "Admin" and not payload.is_active:
            raise HTTPException(status_code=400, detail="Role Admin tidak dapat dinonaktifkan")
        row.is_active = payload.is_active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order

    db.commit()
    db.refresh(row)
    count = db.scalar(select(func.count()).select_from(User).where(User.role == row.code)) or 0
    return role_to_dict(row, user_count=int(count))


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    _require_roles_manage(db, user)
    row = db.get(Role, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    if row.is_system:
        raise HTTPException(status_code=400, detail="Role sistem tidak dapat dihapus")

    in_use = db.scalar(select(func.count()).select_from(User).where(User.role == row.code)) or 0
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Role masih dipakai {in_use} user. Pindahkan user ke role lain terlebih dahulu.",
        )

    db.delete(row)
    db.commit()
    return {"ok": True, "message": "Role dihapus"}


@router.get("/by-code/{code}")
def get_role(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not (
        user_has_permission(db, user, "roles.manage")
        or user_has_permission(db, user, "users.manage")
    ):
        raise HTTPException(status_code=403, detail="Permission required")
    row = get_role_by_code(db, code)
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    count = db.scalar(select(func.count()).select_from(User).where(User.role == row.code)) or 0
    return role_to_dict(row, user_count=int(count))
