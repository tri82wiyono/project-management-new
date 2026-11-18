from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Role, User

PERMISSION_CATALOG = [
    {"key": "dashboard.view", "label": "Lihat Dashboard"},
    {"key": "projects.view", "label": "Lihat Projects"},
    {"key": "projects.manage", "label": "Kelola Projects"},
    {"key": "tasks.view", "label": "Lihat Tasks"},
    {"key": "tasks.manage", "label": "Kelola Tasks"},
    {"key": "users.view", "label": "Lihat Users"},
    {"key": "users.manage", "label": "Kelola Users"},
    {"key": "roles.manage", "label": "Kelola Roles"},
    {"key": "settings.manage", "label": "Kelola Settings"},
    {"key": "audit.view", "label": "Lihat Log Audit"},
]

DEFAULT_ROLES = [
    {
        "code": "Admin",
        "name": "Administrator",
        "description": "Akses penuh ke seluruh modul dan parameter sistem.",
        "permissions": [item["key"] for item in PERMISSION_CATALOG],
        "is_system": True,
        "is_active": True,
        "sort_order": 10,
    },
    {
        "code": "Manager",
        "name": "Manager",
        "description": "Mengelola proyek dan tugas, tanpa akses admin users/settings.",
        "permissions": [
            "dashboard.view",
            "projects.view",
            "projects.manage",
            "tasks.view",
            "tasks.manage",
            "users.view",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 20,
    },
    {
        "code": "Member",
        "name": "Member",
        "description": "Akses operasional standar untuk melihat dan mengerjakan tugas.",
        "permissions": [
            "dashboard.view",
            "projects.view",
            "tasks.view",
            "tasks.manage",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 30,
    },
]


def ensure_default_roles(db: Session) -> list[Role]:
    created: list[Role] = []
    dirty = False
    catalog_keys = [item["key"] for item in PERMISSION_CATALOG]
    for item in DEFAULT_ROLES:
        existing = db.scalar(select(Role).where(Role.code == item["code"]).limit(1))
        if existing:
            # Keep Admin permissions aligned with catalog (e.g. audit.view)
            if existing.code == "Admin" and set(existing.permissions or []) != set(catalog_keys):
                existing.permissions = list(catalog_keys)
                dirty = True
            continue
        row = Role(**item)
        db.add(row)
        created.append(row)
    if created or dirty:
        db.commit()
        for row in created:
            db.refresh(row)
    return created


def role_to_dict(role: Role, *, user_count: int | None = None) -> dict:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description or "",
        "permissions": list(role.permissions or []),
        "is_system": bool(role.is_system),
        "is_active": bool(role.is_active),
        "sort_order": role.sort_order,
        "user_count": user_count,
        "updated_at": role.updated_at,
    }


def list_roles(db: Session, *, active_only: bool = False) -> list[dict]:
    ensure_default_roles(db)
    stmt = select(Role).order_by(Role.sort_order.asc(), Role.name.asc())
    if active_only:
        stmt = stmt.where(Role.is_active.is_(True))
    roles = db.scalars(stmt).all()
    counts = dict(
        db.execute(
            select(User.role, func.count())
            .group_by(User.role)
        ).all()
    )
    return [role_to_dict(role, user_count=int(counts.get(role.code, 0))) for role in roles]


def get_role_by_code(db: Session, code: str) -> Role | None:
    ensure_default_roles(db)
    return db.scalar(select(Role).where(Role.code == code).limit(1))


def get_role_permissions(db: Session, role_code: str) -> set[str]:
    role = get_role_by_code(db, role_code)
    if not role or not role.is_active:
        return set()
    return set(role.permissions or [])


def user_has_permission(db: Session, user: User, permission: str) -> bool:
    if user.role == "Admin":
        # Keep Admin always privileged even if catalog changes
        return True
    return permission in get_role_permissions(db, user.role)


def permission_catalog() -> list[dict]:
    return list(PERMISSION_CATALOG)
