from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.database import get_db
from app.models.models import Bidang, Division, User
from app.services.auth import require_permission, require_user
from app.services.audit import write_audit_log
from app.services import organization as org_svc
from app.services import placement as placement_svc
from app.services.roles import user_has_permission

router = APIRouter(prefix="/api", tags=["organization"])


def _require_ownership_options_access(user: User, db: Session) -> User:
    """Minimal org options for project ownership UI — not full organization.view."""
    if user.role == "Admin":
        return user
    allowed = (
        user_has_permission(db, user, "projects.manage")
        or user_has_permission(db, user, "projects.create")
        or user_has_permission(db, user, "projects.update")
        or user_has_permission(db, user, "projects.assign")
        or user_has_permission(db, user, "organization.view")
        or user_has_permission(db, user, "organization.manage")
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Permission required to load project ownership options",
        )
    return user


class DivisionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    is_active: bool = True
    leader_user_id: int | None = None


class DivisionUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    leader_user_id: int | None = None
    clear_leader: bool = False


class BidangCreate(BaseModel):
    division_id: int
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    is_active: bool = True
    leader_user_id: int | None = None


class BidangUpdate(BaseModel):
    division_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    leader_user_id: int | None = None
    clear_leader: bool = False


def _http_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/organization/ownership-options")
def organization_ownership_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Read-only active Division/Bidang list for project ownership pickers.

    Does not expose leadership, member counts, or inactive units.
    Accessible with project create/update/assign/manage (or organization.view).
    """
    _require_ownership_options_access(user, db)
    divisions = list(
        db.scalars(
            select(Division)
            .where(Division.is_active.is_(True))
            .order_by(Division.name.asc(), Division.id.asc())
        ).all()
    )
    bidangs = list(
        db.scalars(
            select(Bidang)
            .where(Bidang.is_active.is_(True))
            .order_by(Bidang.name.asc(), Bidang.id.asc())
        ).all()
    )
    return {
        "divisions": [
            {"id": d.id, "code": d.code, "name": d.name}
            for d in divisions
        ],
        "bidangs": [
            {
                "id": b.id,
                "code": b.code,
                "name": b.name,
                "division_id": b.division_id,
            }
            for b in bidangs
        ],
    }


@router.get("/organization/tree")
def get_organization_tree(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    return org_svc.organization_tree(db)


@router.get("/divisions")
def list_divisions(
    q: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    items = org_svc.list_divisions(db, q=q, active=active)
    return {"items": items, "total": len(items)}


@router.get("/divisions/{division_id}")
def get_division(
    division_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    row = org_svc.get_division(db, division_id)
    if not row:
        raise HTTPException(status_code=404, detail="Divisi tidak ditemukan")
    bidangs = row.bidangs or []
    member_counts = placement_svc.count_members_by_bidang(db, [b.id for b in bidangs])
    bidang_payload = [
        org_svc.bidang_to_dict(b, member_count=member_counts.get(b.id, 0)) for b in bidangs
    ]
    data = org_svc.division_to_dict(
        row,
        bidang_count=len(bidangs),
        member_count=sum(b["member_count"] for b in bidang_payload),
    )
    data["bidangs"] = bidang_payload
    return data


@router.post("/divisions", status_code=201)
def create_division(
    payload: DivisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("organization.manage")),
) -> dict:
    try:
        row = org_svc.create_division(
            db,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            leader_user_id=payload.leader_user_id,
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    write_audit_log(
        db,
        action="division_created",
        success=True,
        actor=current,
        message=f"Divisi {row.code} dibuat",
        request=request,
        meta={"division_id": row.id, "code": row.code, "leader_user_id": row.leader_user_id},
    )
    return org_svc.division_to_dict(row, bidang_count=len(row.bidangs or []))


@router.patch("/divisions/{division_id}")
def update_division(
    division_id: int,
    payload: DivisionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("organization.manage")),
) -> dict:
    row = org_svc.get_division(db, division_id)
    if not row:
        raise HTTPException(status_code=404, detail="Divisi tidak ditemukan")
    before_leader = row.leader_user_id
    before_active = row.is_active
    leader_arg: int | None | object = ...
    if payload.clear_leader:
        leader_arg = None
    elif "leader_user_id" in payload.model_fields_set:
        leader_arg = payload.leader_user_id
    try:
        row = org_svc.update_division(
            db,
            row,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            leader_user_id=leader_arg,
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc

    if before_leader != row.leader_user_id:
        write_audit_log(
            db,
            action="division_leader_changed",
            success=True,
            actor=current,
            message=f"Pemimpin Divisi {row.code} diubah",
            request=request,
            meta={
                "division_id": row.id,
                "code": row.code,
                "from_leader_user_id": before_leader,
                "to_leader_user_id": row.leader_user_id,
            },
        )
    if before_active != row.is_active:
        write_audit_log(
            db,
            action="division_activated" if row.is_active else "division_deactivated",
            success=True,
            actor=current,
            message=f"Divisi {row.code} {'diaktifkan' if row.is_active else 'dinonaktifkan'}",
            request=request,
            meta={"division_id": row.id, "code": row.code},
        )
    if before_leader == row.leader_user_id and before_active == row.is_active:
        write_audit_log(
            db,
            action="division_updated",
            success=True,
            actor=current,
            message=f"Divisi {row.code} diubah",
            request=request,
            meta={"division_id": row.id, "code": row.code},
        )
    return org_svc.division_to_dict(row, bidang_count=len(row.bidangs or []))


@router.get("/divisions/{division_id}/bidang")
def list_bidang_for_division(
    division_id: int,
    q: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    if not org_svc.get_division(db, division_id):
        raise HTTPException(status_code=404, detail="Divisi tidak ditemukan")
    items = org_svc.list_bidangs(db, division_id=division_id, q=q, active=active)
    return {"items": items, "total": len(items)}


@router.get("/bidang")
def list_bidang(
    division_id: int | None = None,
    q: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    items = org_svc.list_bidangs(db, division_id=division_id, q=q, active=active)
    return {"items": items, "total": len(items)}


@router.get("/bidang/{bidang_id}")
def get_bidang(
    bidang_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    row = org_svc.get_bidang(db, bidang_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bidang tidak ditemukan")
    counts = placement_svc.count_members_by_bidang(db, [row.id])
    return org_svc.bidang_to_dict(row, member_count=counts.get(row.id, 0))


@router.get("/bidang/{bidang_id}/members")
def list_bidang_members(
    bidang_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    row = org_svc.get_bidang(db, bidang_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bidang tidak ditemukan")
    members = placement_svc.list_bidang_members(db, bidang_id)
    return {
        "bidang": org_svc.bidang_to_dict(row, member_count=len(members)),
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "is_active": bool(u.is_active),
                "avatar_url": u.avatar_url,
            }
            for u in members
        ],
        "total": len(members),
    }


@router.get("/organization/unassigned-users")
def list_unassigned_users(
    active_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    users = placement_svc.list_unassigned_users(db, active_only=active_only)
    return {
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "is_active": bool(u.is_active),
                "avatar_url": u.avatar_url,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.get("/organization/leaders")
def list_organization_leaders(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("organization.view")),
) -> dict:
    divisions = org_svc.list_divisions(db)
    bidangs = org_svc.list_bidangs(db)
    items = []
    for div in divisions:
        if div.get("leader"):
            items.append(
                {
                    "unit_type": "division",
                    "unit_id": div["id"],
                    "code": div["code"],
                    "name": div["name"],
                    "leader": div["leader"],
                }
            )
    for bidang in bidangs:
        if bidang.get("leader"):
            items.append(
                {
                    "unit_type": "bidang",
                    "unit_id": bidang["id"],
                    "code": bidang["code"],
                    "name": bidang["name"],
                    "division_id": bidang["division_id"],
                    "division_code": bidang["division_code"],
                    "division_name": bidang["division_name"],
                    "leader": bidang["leader"],
                }
            )
    return {"items": items, "total": len(items)}


@router.post("/bidang", status_code=201)
def create_bidang(
    payload: BidangCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("organization.manage")),
) -> dict:
    try:
        row = org_svc.create_bidang(
            db,
            division_id=payload.division_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            leader_user_id=payload.leader_user_id,
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    write_audit_log(
        db,
        action="bidang_created",
        success=True,
        actor=current,
        message=f"Bidang {row.code} dibuat",
        request=request,
        meta={
            "bidang_id": row.id,
            "division_id": row.division_id,
            "code": row.code,
            "leader_user_id": row.leader_user_id,
        },
    )
    return org_svc.bidang_to_dict(row)


@router.patch("/bidang/{bidang_id}")
def update_bidang(
    bidang_id: int,
    payload: BidangUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("organization.manage")),
) -> dict:
    row = org_svc.get_bidang(db, bidang_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bidang tidak ditemukan")
    before_leader = row.leader_user_id
    before_active = row.is_active
    leader_arg: int | None | object = ...
    if payload.clear_leader:
        leader_arg = None
    elif "leader_user_id" in payload.model_fields_set:
        leader_arg = payload.leader_user_id
    try:
        row = org_svc.update_bidang(
            db,
            row,
            division_id=payload.division_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            leader_user_id=leader_arg,
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc

    if before_leader != row.leader_user_id:
        write_audit_log(
            db,
            action="bidang_leader_changed",
            success=True,
            actor=current,
            message=f"Pemimpin Bidang {row.code} diubah",
            request=request,
            meta={
                "bidang_id": row.id,
                "division_id": row.division_id,
                "code": row.code,
                "from_leader_user_id": before_leader,
                "to_leader_user_id": row.leader_user_id,
            },
        )
    if before_active != row.is_active:
        write_audit_log(
            db,
            action="bidang_activated" if row.is_active else "bidang_deactivated",
            success=True,
            actor=current,
            message=f"Bidang {row.code} {'diaktifkan' if row.is_active else 'dinonaktifkan'}",
            request=request,
            meta={"bidang_id": row.id, "division_id": row.division_id, "code": row.code},
        )
    if before_leader == row.leader_user_id and before_active == row.is_active:
        write_audit_log(
            db,
            action="bidang_updated",
            success=True,
            actor=current,
            message=f"Bidang {row.code} diubah",
            request=request,
            meta={"bidang_id": row.id, "division_id": row.division_id, "code": row.code},
        )
    return org_svc.bidang_to_dict(row)
