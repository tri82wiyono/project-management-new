"""Dynamic role & permission management (Phase 3).

Compatibility rules:
- Legacy broad keys (*.manage) remain valid and imply documented granular keys.
- Existing Admin/Manager/Member role rows are never wiped on startup.
- Admin permissions stay aligned with the active catalog (secure recovery).
- New business role templates are seeded once; later Admin edits are preserved.
- Organizational scope enforcement is deferred to Phase 4.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Role, User

# status: active = assignable; reserved = documented for later / not assignable yet
PERMISSION_CATALOG = [
    # Dashboard
    {
        "key": "dashboard.view",
        "label": "Lihat Dashboard",
        "description": "Akses halaman dashboard dan ringkasan KPI.",
        "category": "Dashboard",
        "status": "active",
    },
    # Organization
    {
        "key": "organization.view",
        "label": "Lihat Struktur Organisasi",
        "description": "Melihat Divisi, Bidang, dan struktur organisasi.",
        "category": "Organization",
        "status": "active",
    },
    {
        "key": "organization.manage",
        "label": "Kelola Struktur Organisasi",
        "description": "Membuat/mengubah Divisi, Bidang, dan pemimpin unit.",
        "category": "Organization",
        "status": "active",
    },
    # Users
    {
        "key": "users.view",
        "label": "Lihat Users",
        "description": "Melihat daftar dan detail pengguna.",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.manage",
        "label": "Kelola Users (legacy)",
        "description": "Akses penuh User Management (kompatibel dengan kunci granular).",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.create",
        "label": "Buat User",
        "description": "Membuat akun pengguna baru.",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.update",
        "label": "Ubah User",
        "description": "Memperbarui profil, status, dan atribut akun.",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.deactivate",
        "label": "Nonaktifkan User",
        "description": "Menonaktifkan akses login pengguna.",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.assign_role",
        "label": "Assign Role User",
        "description": "Mengubah role aplikasi pengguna.",
        "category": "Users",
        "status": "active",
    },
    {
        "key": "users.assign_organization",
        "label": "Assign Penempatan Organisasi",
        "description": "Menetapkan/mutasi penempatan Divisi/Bidang pengguna.",
        "category": "Users",
        "status": "active",
    },
    # Roles
    {
        "key": "roles.view",
        "label": "Lihat Roles",
        "description": "Melihat daftar role dan permission.",
        "category": "Roles",
        "status": "active",
    },
    {
        "key": "roles.manage",
        "label": "Kelola Roles",
        "description": "Membuat/mengubah role dan permission matrix.",
        "category": "Roles",
        "status": "active",
    },
    # Projects
    {
        "key": "projects.view",
        "label": "Lihat Projects",
        "description": "Melihat daftar dan detail project.",
        "category": "Projects",
        "status": "active",
    },
    {
        "key": "projects.manage",
        "label": "Kelola Projects (legacy)",
        "description": "Akses luas kelola project (kompatibel; tidak termasuk hapus).",
        "category": "Projects",
        "status": "active",
    },
    {
        "key": "projects.create",
        "label": "Buat Project",
        "description": "Membuat project baru.",
        "category": "Projects",
        "status": "active",
    },
    {
        "key": "projects.update",
        "label": "Ubah Project",
        "description": "Memperbarui data project.",
        "category": "Projects",
        "status": "active",
    },
    {
        "key": "projects.assign",
        "label": "Assign Anggota Project",
        "description": "Mengatur keanggotaan project.",
        "category": "Projects",
        "status": "active",
    },
    {
        "key": "projects.approve",
        "label": "Approve Project (reserved)",
        "description": "Reserved — alur approval belum diimplementasikan.",
        "category": "Projects",
        "status": "reserved",
    },
    {
        "key": "projects.delete",
        "label": "Hapus Project (reserved)",
        "description": "Reserved — penghapusan tetap dibatasi role Admin (SEC-05).",
        "category": "Projects",
        "status": "reserved",
    },
    # Tasks
    {
        "key": "tasks.view",
        "label": "Lihat Tasks",
        "description": "Melihat daftar dan detail task.",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.manage",
        "label": "Kelola Tasks (legacy)",
        "description": "Akses luas kelola task (kompatibel dengan kunci granular).",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.create",
        "label": "Buat Task",
        "description": "Membuat task baru.",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.update",
        "label": "Ubah Task",
        "description": "Memperbarui task.",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.assign",
        "label": "Assign Task",
        "description": "Menetapkan assignee task.",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.complete",
        "label": "Selesaikan Task",
        "description": "Menandai task selesai / mengubah status penyelesaian.",
        "category": "Tasks",
        "status": "active",
    },
    {
        "key": "tasks.delete",
        "label": "Hapus Task",
        "description": "Menghapus task. Legacy tasks.manage masih mengizinkan hapus.",
        "category": "Tasks",
        "status": "active",
    },
    # Tickets
    {
        "key": "tickets.view",
        "label": "Lihat Ticket Management",
        "description": "Melihat ticket/kendala dan catatan.",
        "category": "Tickets",
        "status": "active",
    },
    {
        "key": "tickets.manage",
        "label": "Kelola Ticket Management",
        "description": "Membuat dan mengubah ticket.",
        "category": "Tickets",
        "status": "active",
    },
    # Settings / Audit
    {
        "key": "settings.manage",
        "label": "Kelola Settings",
        "description": "Mengelola SMTP, identitas aplikasi, dan keamanan.",
        "category": "Settings",
        "status": "active",
    },
    {
        "key": "audit.view",
        "label": "Lihat Log Audit",
        "description": "Melihat log audit keamanan dan administrasi.",
        "category": "Audit",
        "status": "active",
    },
]

# Legacy broad → granular (effective authorization only; stored role JSON unchanged).
# projects.manage intentionally does NOT imply projects.delete (SEC-05).
LEGACY_PERMISSION_IMPLIES: dict[str, tuple[str, ...]] = {
    "users.manage": (
        "users.view",
        "users.create",
        "users.update",
        "users.deactivate",
        "users.assign_role",
        "users.assign_organization",
    ),
    "roles.manage": ("roles.view",),
    "projects.manage": (
        "projects.view",
        "projects.create",
        "projects.update",
        "projects.assign",
    ),
    "tasks.manage": (
        "tasks.view",
        "tasks.create",
        "tasks.update",
        "tasks.assign",
        "tasks.complete",
        "tasks.delete",
    ),
    "tickets.manage": ("tickets.view",),
    "organization.manage": ("organization.view",),
}

# Permissions safe to grant on business templates ONLY after org-scope enforcement
# is enabled. Do not auto-apply to existing roles — Admin configures via UI.
# Keyed by role code for UI hints (phase4_pending_permissions field name retained).
PHASE4_PENDING_PERMISSIONS = {
    "PemimpinDivisi": [
        "projects.view",
        "projects.create",
        "projects.update",
        "projects.assign",
        "tasks.view",
        "tasks.create",
        "tasks.update",
        "tasks.assign",
        "tickets.view",
        "tickets.manage",
    ],
    "PemimpinBidang": [
        "projects.view",
        "projects.update",
        "projects.assign",
        "tasks.view",
        "tasks.create",
        "tasks.update",
        "tasks.assign",
        "tasks.complete",
        "tickets.view",
        "tickets.manage",
    ],
    "Staff": [
        "tasks.create",
        "tasks.update",
        "tasks.complete",
        "tickets.manage",
    ],
}

DEFAULT_ROLES = [
    {
        "code": "Admin",
        "name": "Administrator",
        "description": "Akses penuh administrasi aplikasi di seluruh organisasi.",
        "permissions": [],  # filled from active catalog at seed time
        "is_system": True,
        "is_active": True,
        "sort_order": 10,
        "seed_mode": "admin_sync",
    },
    {
        "code": "Manager",
        "name": "Manager",
        "description": "Legacy — mengelola proyek dan tugas, tanpa akses admin users/settings.",
        "permissions": [
            "dashboard.view",
            "projects.view",
            "projects.manage",
            "tickets.view",
            "tickets.manage",
            "tasks.view",
            "tasks.manage",
            "users.view",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 20,
        "seed_mode": "legacy_additive",
    },
    {
        "code": "Member",
        "name": "Member",
        "description": "Legacy — akses operasional standar untuk melihat dan mengerjakan tugas.",
        "permissions": [
            "dashboard.view",
            "projects.view",
            "tickets.view",
            "tickets.manage",
            "tasks.view",
            "tasks.manage",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 30,
        "seed_mode": "legacy_additive",
    },
    {
        "code": "PemimpinDivisi",
        "name": "Pemimpin Divisi",
        "description": (
            "Template bisnis — memantau Divisi. Permission project/task luas ditunda "
            "hingga Phase 4 (organizational scope)."
        ),
        "permissions": [
            "dashboard.view",
            "organization.view",
            "projects.view",
            "tasks.view",
            "tickets.view",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 40,
        "seed_mode": "create_only",
    },
    {
        "code": "PemimpinBidang",
        "name": "Pemimpin Bidang",
        "description": (
            "Template bisnis — memantau Bidang. Permission project/task luas ditunda "
            "hingga Phase 4 (organizational scope)."
        ),
        "permissions": [
            "dashboard.view",
            "organization.view",
            "projects.view",
            "tasks.view",
            "tickets.view",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 50,
        "seed_mode": "create_only",
    },
    {
        "code": "Staff",
        "name": "Staff",
        "description": (
            "Template bisnis — akses operasional dasar. Scope assignment penuh di Phase 4."
        ),
        "permissions": [
            "dashboard.view",
            "projects.view",
            "tasks.view",
            "tickets.view",
        ],
        "is_system": True,
        "is_active": True,
        "sort_order": 60,
        "seed_mode": "create_only",
    },
]

PROTECTED_ROLE_CODES = frozenset({"Admin"})


def permission_catalog(*, include_reserved: bool = True) -> list[dict]:
    items = list(PERMISSION_CATALOG)
    if not include_reserved:
        items = [item for item in items if item.get("status", "active") == "active"]
    return items


def assignable_permission_keys() -> set[str]:
    return {item["key"] for item in PERMISSION_CATALOG if item.get("status", "active") == "active"}


def known_permission_keys() -> set[str]:
    return {item["key"] for item in PERMISSION_CATALOG}


def validate_permissions(raw: list[str] | None) -> list[str]:
    """Return sanitized unique permission keys; raise ValueError on unknown/reserved."""
    allowed = assignable_permission_keys()
    known = known_permission_keys()
    values: list[str] = []
    unknown: list[str] = []
    reserved: list[str] = []
    for item in raw or []:
        key = str(item).strip()
        if not key:
            continue
        if key not in known:
            unknown.append(key)
            continue
        if key not in allowed:
            reserved.append(key)
            continue
        if key not in values:
            values.append(key)
    if unknown:
        raise ValueError(f"Permission tidak dikenal: {', '.join(sorted(set(unknown)))}")
    if reserved:
        raise ValueError(
            f"Permission reserved/nonaktif tidak dapat di-assign: {', '.join(sorted(set(reserved)))}"
        )
    return values


def expand_effective_permissions(stored: set[str] | list[str] | None) -> set[str]:
    """Expand legacy broad keys into granular equivalents for authorization checks."""
    effective = set(stored or [])
    for broad, implied in LEGACY_PERMISSION_IMPLIES.items():
        if broad in effective:
            effective.update(implied)
    return effective


def ensure_default_roles(db: Session) -> list[Role]:
    created: list[Role] = []
    dirty = False
    catalog_keys = sorted(assignable_permission_keys())
    for item in DEFAULT_ROLES:
        existing = db.scalar(select(Role).where(Role.code == item["code"]).limit(1))
        seed_mode = item.get("seed_mode", "create_only")
        desired = list(item["permissions"])
        if item["code"] == "Admin":
            desired = list(catalog_keys)

        if existing:
            if seed_mode == "admin_sync" and existing.code == "Admin":
                if set(existing.permissions or []) != set(catalog_keys):
                    existing.permissions = list(catalog_keys)
                    dirty = True
            elif seed_mode == "legacy_additive" and existing.is_system:
                # Add newly introduced *legacy template* perms without wiping custom ones.
                current = set(existing.permissions or [])
                missing = set(desired) - current
                # Never auto-add brand-new granular keys to Manager/Member.
                legacy_safe = missing & {
                    "dashboard.view",
                    "projects.view",
                    "projects.manage",
                    "tickets.view",
                    "tickets.manage",
                    "tasks.view",
                    "tasks.manage",
                    "users.view",
                    "organization.view",
                    "organization.manage",
                    "roles.view",
                    "roles.manage",
                    "settings.manage",
                    "audit.view",
                }
                if legacy_safe:
                    existing.permissions = list(current | legacy_safe)
                    dirty = True
            # create_only: never overwrite admin-managed configuration
            continue

        row = Role(
            code=item["code"],
            name=item["name"],
            description=item["description"],
            permissions=desired,
            is_system=bool(item["is_system"]),
            is_active=bool(item["is_active"]),
            sort_order=int(item["sort_order"]),
        )
        db.add(row)
        created.append(row)

    if created or dirty:
        db.commit()
        invalidate_role_permissions_cache()
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
        "is_protected": role.code in PROTECTED_ROLE_CODES,
        "sort_order": role.sort_order,
        "user_count": user_count,
        "updated_at": role.updated_at,
        "phase4_pending_permissions": PHASE4_PENDING_PERMISSIONS.get(role.code, []),
    }


def list_roles(db: Session, *, active_only: bool = False) -> list[dict]:
    ensure_default_roles(db)
    stmt = select(Role).order_by(Role.sort_order.asc(), Role.name.asc())
    if active_only:
        stmt = stmt.where(Role.is_active.is_(True))
    roles = db.scalars(stmt).all()
    counts = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return [role_to_dict(role, user_count=int(counts.get(role.code, 0))) for role in roles]


def permission_matrix(db: Session) -> dict:
    roles = list_roles(db, active_only=False)
    catalog = permission_catalog(include_reserved=True)
    return {
        "roles": [
            {
                "id": r["id"],
                "code": r["code"],
                "name": r["name"],
                "is_active": r["is_active"],
                "permissions": r["permissions"],
            }
            for r in roles
        ],
        "permissions": catalog,
    }


_ROLE_PERM_CACHE: dict[str, tuple[float, frozenset[str]]] = {}
_ROLE_PERM_TTL = 60.0


def invalidate_role_permissions_cache() -> None:
    _ROLE_PERM_CACHE.clear()


def get_role_by_code(db: Session, code: str) -> Role | None:
    ensure_default_roles(db)
    return db.scalar(select(Role).where(Role.code == code).limit(1))


def get_role_permissions(db: Session, role_code: str) -> set[str]:
    key = (role_code or "").strip()
    now = time.monotonic()
    cached = _ROLE_PERM_CACHE.get(key)
    if cached and now < cached[0]:
        return set(cached[1])

    role = get_role_by_code(db, role_code)
    if not role or not role.is_active:
        perms: set[str] = set()
    else:
        perms = expand_effective_permissions(role.permissions or [])
    _ROLE_PERM_CACHE[key] = (now + _ROLE_PERM_TTL, frozenset(perms))
    return perms


def user_has_permission(db: Session, user: User, permission: str) -> bool:
    # SEC-06: intentional Admin recovery/superuser bypass by role code.
    if user.role == "Admin":
        return True
    return permission in get_role_permissions(db, user.role)


def count_active_admins(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "Admin", User.is_active.is_(True))
        )
        or 0
    )


def is_last_active_admin(db: Session, user: User) -> bool:
    if user.role != "Admin" or not user.is_active:
        return False
    return count_active_admins(db) <= 1


def assert_role_assignment_allowed(
    db: Session,
    *,
    target: User,
    new_role_code: str,
    actor: User | None = None,
) -> Role:
    role = get_role_by_code(db, new_role_code)
    if not role:
        raise ValueError("Role tidak valid")
    if not role.is_active:
        raise ValueError("Role tidak aktif")
    if target.role == "Admin" and new_role_code != "Admin" and is_last_active_admin(db, target):
        raise ValueError("Tidak dapat menurunkan role Administrator terakhir yang aktif")
    if actor and actor.id == target.id and actor.role == "Admin" and new_role_code != "Admin":
        # Self demotion of last admin already covered; still block self-demote when sole admin.
        if is_last_active_admin(db, actor):
            raise ValueError("Tidak dapat menurunkan role akun Administrator sendiri (satu-satunya)")
    return role


def duplicate_role(db: Session, source: Role, *, new_code: str, new_name: str | None = None) -> Role:
    code = (new_code or "").strip()
    if not code:
        raise ValueError("Kode role baru wajib diisi")
    clash = db.scalar(select(Role.id).where(func.lower(Role.code) == code.lower()).limit(1))
    if clash:
        raise ValueError("Kode role sudah ada")
    perms = validate_permissions(list(source.permissions or []))
    row = Role(
        code=code,
        name=(new_name or f"{source.name} (Copy)").strip()[:80],
        description=(source.description or "").strip()[:255],
        permissions=perms,
        is_system=False,
        is_active=True,
        sort_order=int(source.sort_order or 100),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_role_permissions_cache()
    return row
