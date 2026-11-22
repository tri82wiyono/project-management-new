"""Organization master data (Division / Bidang). Leadership is metadata only."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.models import Bidang, Division, User


def _norm_code(code: str) -> str:
    return (code or "").strip().upper()


def _norm_name(name: str) -> str:
    return (name or "").strip()


def leader_summary(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_active": bool(user.is_active),
    }


def require_active_leader(db: Session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, int(user_id))
    if not user:
        raise ValueError("Pemimpin tidak ditemukan")
    if not user.is_active:
        raise ValueError("Pemimpin harus pengguna aktif")
    return user


def division_to_dict(row: Division, *, bidang_count: int | None = None) -> dict:
    count = bidang_count
    if count is None:
        count = len(row.bidangs) if row.bidangs is not None else 0
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "description": row.description or "",
        "is_active": bool(row.is_active),
        "leader_user_id": row.leader_user_id,
        "leader": leader_summary(row.leader),
        "bidang_count": int(count),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def bidang_to_dict(row: Bidang) -> dict:
    return {
        "id": row.id,
        "division_id": row.division_id,
        "division_code": row.division.code if row.division else "",
        "division_name": row.division.name if row.division else "",
        "code": row.code,
        "name": row.name,
        "description": row.description or "",
        "is_active": bool(row.is_active),
        "leader_user_id": row.leader_user_id,
        "leader": leader_summary(row.leader),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_divisions(
    db: Session,
    *,
    q: str | None = None,
    active: bool | None = None,
) -> list[dict]:
    stmt = (
        select(Division)
        .options(joinedload(Division.leader), joinedload(Division.bidangs))
        .order_by(Division.name.asc())
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Division.code.ilike(like), Division.name.ilike(like)))
    if active is not None:
        stmt = stmt.where(Division.is_active.is_(active))
    rows = db.scalars(stmt).unique().all()
    return [division_to_dict(row, bidang_count=len(row.bidangs or [])) for row in rows]


def get_division(db: Session, division_id: int) -> Division | None:
    return db.scalar(
        select(Division)
        .options(joinedload(Division.leader), joinedload(Division.bidangs).joinedload(Bidang.leader))
        .where(Division.id == division_id)
        .limit(1)
    )


def create_division(
    db: Session,
    *,
    code: str,
    name: str,
    description: str = "",
    is_active: bool = True,
    leader_user_id: int | None = None,
) -> Division:
    code_n = _norm_code(code)
    name_n = _norm_name(name)
    if not code_n or not name_n:
        raise ValueError("Kode dan nama Divisi wajib diisi")
    if db.scalar(select(Division.id).where(Division.code == code_n).limit(1)):
        raise ValueError("Kode Divisi sudah digunakan")
    leader = require_active_leader(db, leader_user_id)
    row = Division(
        code=code_n,
        name=name_n,
        description=(description or "").strip()[:500],
        is_active=bool(is_active),
        leader_user_id=leader.id if leader else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Kode Divisi sudah digunakan") from exc
    db.refresh(row)
    return get_division(db, row.id) or row


def update_division(
    db: Session,
    row: Division,
    *,
    code: str | None = None,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
    leader_user_id: int | None | object = ...,
) -> Division:
    if code is not None:
        code_n = _norm_code(code)
        if not code_n:
            raise ValueError("Kode Divisi wajib diisi")
        clash = db.scalar(
            select(Division.id).where(Division.code == code_n, Division.id != row.id).limit(1)
        )
        if clash:
            raise ValueError("Kode Divisi sudah digunakan")
        row.code = code_n
    if name is not None:
        name_n = _norm_name(name)
        if not name_n:
            raise ValueError("Nama Divisi wajib diisi")
        row.name = name_n
    if description is not None:
        row.description = (description or "").strip()[:500]
    if is_active is not None:
        row.is_active = bool(is_active)
    if leader_user_id is not ...:
        leader = require_active_leader(db, leader_user_id)
        row.leader_user_id = leader.id if leader else None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Kode Divisi sudah digunakan") from exc
    db.refresh(row)
    return get_division(db, row.id) or row


def list_bidangs(
    db: Session,
    *,
    division_id: int | None = None,
    q: str | None = None,
    active: bool | None = None,
) -> list[dict]:
    stmt = (
        select(Bidang)
        .options(joinedload(Bidang.leader), joinedload(Bidang.division))
        .order_by(Bidang.name.asc())
    )
    if division_id is not None:
        stmt = stmt.where(Bidang.division_id == division_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Bidang.code.ilike(like), Bidang.name.ilike(like)))
    if active is not None:
        stmt = stmt.where(Bidang.is_active.is_(active))
    rows = db.scalars(stmt).unique().all()
    return [bidang_to_dict(row) for row in rows]


def get_bidang(db: Session, bidang_id: int) -> Bidang | None:
    return db.scalar(
        select(Bidang)
        .options(joinedload(Bidang.leader), joinedload(Bidang.division))
        .where(Bidang.id == bidang_id)
        .limit(1)
    )


def create_bidang(
    db: Session,
    *,
    division_id: int,
    code: str,
    name: str,
    description: str = "",
    is_active: bool = True,
    leader_user_id: int | None = None,
) -> Bidang:
    division = db.get(Division, int(division_id))
    if not division:
        raise ValueError("Divisi tidak ditemukan")
    code_n = _norm_code(code)
    name_n = _norm_name(name)
    if not code_n or not name_n:
        raise ValueError("Kode dan nama Bidang wajib diisi")
    if is_active and not division.is_active:
        raise ValueError("Tidak dapat membuat Bidang aktif pada Divisi nonaktif")
    if db.scalar(
        select(Bidang.id)
        .where(Bidang.division_id == division.id, Bidang.code == code_n)
        .limit(1)
    ):
        raise ValueError("Kode Bidang sudah digunakan pada Divisi ini")
    leader = require_active_leader(db, leader_user_id)
    row = Bidang(
        division_id=division.id,
        code=code_n,
        name=name_n,
        description=(description or "").strip()[:500],
        is_active=bool(is_active),
        leader_user_id=leader.id if leader else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Kode Bidang sudah digunakan pada Divisi ini") from exc
    db.refresh(row)
    return get_bidang(db, row.id) or row


def update_bidang(
    db: Session,
    row: Bidang,
    *,
    division_id: int | None = None,
    code: str | None = None,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
    leader_user_id: int | None | object = ...,
) -> Bidang:
    target_division = row.division
    if division_id is not None and int(division_id) != row.division_id:
        target_division = db.get(Division, int(division_id))
        if not target_division:
            raise ValueError("Divisi tidak ditemukan")
        row.division_id = target_division.id

    code_n = _norm_code(code) if code is not None else row.code
    if code is not None and not code_n:
        raise ValueError("Kode Bidang wajib diisi")
    if code is not None or division_id is not None:
        clash = db.scalar(
            select(Bidang.id)
            .where(
                Bidang.division_id == row.division_id,
                Bidang.code == code_n,
                Bidang.id != row.id,
            )
            .limit(1)
        )
        if clash:
            raise ValueError("Kode Bidang sudah digunakan pada Divisi ini")
        row.code = code_n

    if name is not None:
        name_n = _norm_name(name)
        if not name_n:
            raise ValueError("Nama Bidang wajib diisi")
        row.name = name_n
    if description is not None:
        row.description = (description or "").strip()[:500]

    next_active = row.is_active if is_active is None else bool(is_active)
    if next_active and target_division and not target_division.is_active:
        raise ValueError("Tidak dapat mengaktifkan Bidang pada Divisi nonaktif")
    if is_active is not None:
        row.is_active = bool(is_active)

    if leader_user_id is not ...:
        leader = require_active_leader(db, leader_user_id)
        row.leader_user_id = leader.id if leader else None

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Kode Bidang sudah digunakan pada Divisi ini") from exc
    db.refresh(row)
    return get_bidang(db, row.id) or row


def organization_tree(db: Session) -> dict:
    from app.services.identity import get_identity_dict

    identity = get_identity_dict()
    divisions = (
        db.scalars(
            select(Division)
            .options(joinedload(Division.leader), joinedload(Division.bidangs).joinedload(Bidang.leader))
            .order_by(Division.name.asc())
        )
        .unique()
        .all()
    )
    return {
        "organization_name": identity.get("organization_name") or "Bank Sumut",
        "divisions": [
            {
                **division_to_dict(div, bidang_count=len(div.bidangs or [])),
                "bidangs": [bidang_to_dict(b) for b in (div.bidangs or [])],
            }
            for div in divisions
        ],
        "stats": {
            "divisions": len(divisions),
            "bidangs": int(db.scalar(select(func.count()).select_from(Bidang)) or 0),
            "active_divisions": int(
                db.scalar(select(func.count()).select_from(Division).where(Division.is_active.is_(True))) or 0
            ),
            "active_bidangs": int(
                db.scalar(select(func.count()).select_from(Bidang).where(Bidang.is_active.is_(True))) or 0
            ),
        },
    }
