"""User organizational placement (Phase 2).

Single source of truth: users.primary_bidang_id.
Division is always derived from the Bidang parent.
Leadership (Division/Bidang leader_user_id) is independent metadata — placement
mutations never grant permissions and never silently clear leadership.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.models import Bidang, Division, User, UserPlacementHistory


class PlacementConflictError(ValueError):
    """Raised when transfer conflicts with active leadership and was not acknowledged."""

    def __init__(self, message: str, conflicts: list[dict]):
        super().__init__(message)
        self.conflicts = conflicts


class PlacementVersionError(ValueError):
    """Raised when expected_version does not match the current placement_version."""

    def __init__(self, message: str, current_version: int):
        super().__init__(message)
        self.current_version = current_version


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _unit_snapshot(bidang: Bidang | None) -> dict:
    if not bidang:
        return {
            "bidang_id": None,
            "bidang_code": "",
            "bidang_name": "",
            "division_id": None,
            "division_code": "",
            "division_name": "",
        }
    division = bidang.division
    return {
        "bidang_id": bidang.id,
        "bidang_code": bidang.code or "",
        "bidang_name": bidang.name or "",
        "division_id": bidang.division_id,
        "division_code": (division.code if division else "") or "",
        "division_name": (division.name if division else "") or "",
    }


def leadership_roles_for_user(db: Session, user_id: int) -> list[dict]:
    """Return units where the user is currently recorded as leader (metadata only)."""
    roles: list[dict] = []
    divisions = db.scalars(
        select(Division).where(Division.leader_user_id == user_id).order_by(Division.name.asc())
    ).all()
    for div in divisions:
        roles.append(
            {
                "unit_type": "division",
                "unit_id": div.id,
                "code": div.code,
                "name": div.name,
                "is_active": bool(div.is_active),
            }
        )
    bidangs = db.scalars(
        select(Bidang)
        .options(joinedload(Bidang.division))
        .where(Bidang.leader_user_id == user_id)
        .order_by(Bidang.name.asc())
    ).unique().all()
    for bidang in bidangs:
        roles.append(
            {
                "unit_type": "bidang",
                "unit_id": bidang.id,
                "code": bidang.code,
                "name": bidang.name,
                "division_id": bidang.division_id,
                "division_code": bidang.division.code if bidang.division else "",
                "division_name": bidang.division.name if bidang.division else "",
                "is_active": bool(bidang.is_active),
            }
        )
    return roles


def placement_summary(user: User) -> dict:
    bidang = user.primary_bidang
    snap = _unit_snapshot(bidang)
    return {
        "bidang_id": snap["bidang_id"],
        "bidang_code": snap["bidang_code"],
        "bidang_name": snap["bidang_name"],
        "division_id": snap["division_id"],
        "division_code": snap["division_code"],
        "division_name": snap["division_name"],
        "is_assigned": snap["bidang_id"] is not None,
        "placement_version": int(user.placement_version or 0),
        "placement_updated_at": user.placement_updated_at,
    }


def serialize_user_with_placement(db: Session, user: User) -> dict:
    placement = placement_summary(user)
    leadership = leadership_roles_for_user(db, user.id)
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
        "placement": placement,
        "leadership": leadership,
        "is_leader": bool(leadership),
    }


def history_to_dict(row: UserPlacementHistory) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "action": row.action,
        "from_bidang_id": row.from_bidang_id,
        "to_bidang_id": row.to_bidang_id,
        "from_division_id": row.from_division_id,
        "to_division_id": row.to_division_id,
        "from_bidang_code": row.from_bidang_code or "",
        "from_bidang_name": row.from_bidang_name or "",
        "from_division_code": row.from_division_code or "",
        "from_division_name": row.from_division_name or "",
        "to_bidang_code": row.to_bidang_code or "",
        "to_bidang_name": row.to_bidang_name or "",
        "to_division_code": row.to_division_code or "",
        "to_division_name": row.to_division_name or "",
        "reason": row.reason or "",
        "actor_user_id": row.actor_user_id,
        "actor_name": row.actor.name if row.actor else "",
        "placement_version": row.placement_version,
        "leadership_conflict_acknowledged": bool(row.leadership_conflict_acknowledged),
        "created_at": row.created_at,
    }


def load_user_with_placement(db: Session, user_id: int) -> User | None:
    return db.scalar(
        select(User)
        .options(
            joinedload(User.primary_bidang).joinedload(Bidang.division),
        )
        .where(User.id == user_id)
        .limit(1)
    )


def list_users_with_placement(
    db: Session,
    *,
    q: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    division_id: int | None = None,
    bidang_id: int | None = None,
    unassigned: bool | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[User], int]:
    """Return matching users and filtered total. Optional page/page_size for pagination."""
    filters = []
    join_bidang = False
    if q:
        like = f"%{q.strip()}%"
        filters.append((User.name.ilike(like)) | (User.email.ilike(like)))
    if role:
        filters.append(User.role == role)
    if active is not None:
        filters.append(User.is_active.is_(active))
    if bidang_id is not None:
        filters.append(User.primary_bidang_id == int(bidang_id))
    if division_id is not None:
        join_bidang = True
        filters.append(Bidang.division_id == int(division_id))
    if unassigned is True:
        filters.append(User.primary_bidang_id.is_(None))
    elif unassigned is False:
        filters.append(User.primary_bidang_id.is_not(None))

    count_stmt = select(func.count()).select_from(User)
    if join_bidang:
        count_stmt = count_stmt.join(Bidang, User.primary_bidang_id == Bidang.id, isouter=False)
    if filters:
        count_stmt = count_stmt.where(*filters)
    filtered_total = int(db.scalar(count_stmt) or 0)

    stmt = (
        select(User)
        .options(joinedload(User.primary_bidang).joinedload(Bidang.division))
        .order_by(User.name.asc(), User.id.asc())
    )
    if join_bidang:
        stmt = stmt.join(Bidang, User.primary_bidang_id == Bidang.id, isouter=False)
    if filters:
        stmt = stmt.where(*filters)

    if page is not None and page_size is not None:
        size = max(1, int(page_size))
        pages = max(1, (filtered_total + size - 1) // size) if filtered_total else 1
        current = min(max(1, int(page)), pages)
        stmt = stmt.offset((current - 1) * size).limit(size)

    users = list(db.scalars(stmt).unique().all())
    return users, filtered_total


def count_members_by_bidang(db: Session, bidang_ids: list[int] | None = None) -> dict[int, int]:
    stmt = (
        select(User.primary_bidang_id, func.count())
        .where(User.primary_bidang_id.is_not(None))
        .group_by(User.primary_bidang_id)
    )
    if bidang_ids is not None:
        if not bidang_ids:
            return {}
        stmt = stmt.where(User.primary_bidang_id.in_(bidang_ids))
    rows = db.execute(stmt).all()
    return {int(bidang_id): int(count) for bidang_id, count in rows if bidang_id is not None}


def count_unassigned_users(db: Session) -> int:
    return int(
        db.scalar(select(func.count()).select_from(User).where(User.primary_bidang_id.is_(None))) or 0
    )


def list_unassigned_users(db: Session, *, active_only: bool = False) -> list[User]:
    stmt = select(User).where(User.primary_bidang_id.is_(None)).order_by(User.name.asc())
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    return list(db.scalars(stmt).all())


def list_bidang_members(db: Session, bidang_id: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.primary_bidang_id == int(bidang_id))
            .order_by(User.name.asc())
        ).all()
    )


def list_placement_history(db: Session, user_id: int) -> list[UserPlacementHistory]:
    return list(
        db.scalars(
            select(UserPlacementHistory)
            .options(joinedload(UserPlacementHistory.actor))
            .where(UserPlacementHistory.user_id == int(user_id))
            .order_by(UserPlacementHistory.created_at.desc(), UserPlacementHistory.id.desc())
        ).unique().all()
    )


def _require_destination_bidang(db: Session, bidang_id: int) -> Bidang:
    bidang = db.scalar(
        select(Bidang)
        .options(joinedload(Bidang.division))
        .where(Bidang.id == int(bidang_id))
        .limit(1)
    )
    if not bidang:
        raise ValueError("Bidang tujuan tidak ditemukan")
    if not bidang.is_active:
        raise ValueError("Bidang tujuan tidak aktif")
    if not bidang.division:
        raise ValueError("Divisi induk Bidang tidak ditemukan")
    if not bidang.division.is_active:
        raise ValueError("Divisi induk tidak aktif")
    return bidang


def set_user_placement(
    db: Session,
    user: User,
    *,
    bidang_id: int | None,
    actor: User | None = None,
    reason: str = "",
    expected_version: int | None = None,
    acknowledge_leadership_conflict: bool = False,
) -> tuple[User, UserPlacementHistory | None, bool]:
    """Assign, transfer, or clear a user's primary Bidang placement.

    Returns (user, history_row_or_None, unchanged).
    Does not modify role, permissions, project memberships, or leadership FKs.
    """
    # Refresh placement under row lock to reduce concurrent overwrite risk.
    locked = db.scalar(select(User).where(User.id == user.id).with_for_update().limit(1))
    if not locked:
        raise ValueError("User tidak ditemukan")
    user = locked

    current_version = int(user.placement_version or 0)
    if expected_version is not None and int(expected_version) != current_version:
        raise PlacementVersionError(
            "Penempatan sudah diubah oleh proses lain. Muat ulang data lalu coba lagi.",
            current_version=current_version,
        )

    current_bidang = None
    if user.primary_bidang_id:
        current_bidang = db.scalar(
            select(Bidang)
            .options(joinedload(Bidang.division))
            .where(Bidang.id == user.primary_bidang_id)
            .limit(1)
        )

    destination: Bidang | None = None
    if bidang_id is not None:
        destination = _require_destination_bidang(db, bidang_id)

    # Idempotent: identical assignment creates no history.
    if (current_bidang.id if current_bidang else None) == (destination.id if destination else None):
        return user, None, True

    conflicts = leadership_roles_for_user(db, user.id)
    if conflicts and not acknowledge_leadership_conflict:
        raise PlacementConflictError(
            "Pengguna masih menjadi pemimpin unit organisasi. "
            "Konfirmasi transfer tanpa mengubah kepemimpinan, atau ubah pemimpin di Organization Management terlebih dahulu.",
            conflicts=conflicts,
        )

    from_snap = _unit_snapshot(current_bidang)
    to_snap = _unit_snapshot(destination)

    if destination is None:
        action = "clear"
    elif current_bidang is None:
        action = "assign"
    else:
        action = "transfer"

    new_version = current_version + 1
    user.primary_bidang_id = destination.id if destination else None
    user.placement_version = new_version
    user.placement_updated_at = _utc_now()

    history = UserPlacementHistory(
        user_id=user.id,
        action=action,
        from_bidang_id=from_snap["bidang_id"],
        to_bidang_id=to_snap["bidang_id"],
        from_division_id=from_snap["division_id"],
        to_division_id=to_snap["division_id"],
        from_bidang_code=from_snap["bidang_code"],
        from_bidang_name=from_snap["bidang_name"],
        from_division_code=from_snap["division_code"],
        from_division_name=from_snap["division_name"],
        to_bidang_code=to_snap["bidang_code"],
        to_bidang_name=to_snap["bidang_name"],
        to_division_code=to_snap["division_code"],
        to_division_name=to_snap["division_name"],
        reason=(reason or "").strip()[:500],
        actor_user_id=actor.id if actor else None,
        placement_version=new_version,
        leadership_conflict_acknowledged=bool(acknowledge_leadership_conflict and conflicts),
    )
    db.add(history)
    db.commit()
    refreshed = load_user_with_placement(db, user.id)
    return refreshed or user, history, False
