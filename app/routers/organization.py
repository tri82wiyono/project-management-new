from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.auth import require_permission
from app.services.audit import write_audit_log
from app.services import organization as org_svc

router = APIRouter(prefix="/api", tags=["organization"])


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
    data = org_svc.division_to_dict(row, bidang_count=len(row.bidangs or []))
    data["bidangs"] = [org_svc.bidang_to_dict(b) for b in (row.bidangs or [])]
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
    return org_svc.bidang_to_dict(row)


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
