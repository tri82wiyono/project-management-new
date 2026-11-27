"""Invite collaborators to a project by email (existing or new users)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Project, TeamMember, User
from app.services.email import send_project_added_email, send_project_invite_email
from app.services.roles import get_role_by_code
from app.services.security import default_avatar, generate_temp_password, hash_password

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_invite_emails(raw_emails: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in raw_emails or []:
        for part in re.split(r"[,;\s]+", str(item or "")):
            email = part.strip().lower()
            if not email or email in seen:
                continue
            if not _EMAIL_RE.match(email):
                continue
            seen.add(email)
            out.append(email)
    return out


def _default_invite_role(db: Session) -> str:
    for code in ("Staff", "Member"):
        role = get_role_by_code(db, code)
        if role and role.is_active:
            return role.code
    return "Member"


def _name_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    return local.title() if local else "Pengguna"


def ensure_team_member(db: Session, project: Project, user: User) -> bool:
    """Add user to project team if missing. Returns True when newly added."""
    existing = db.scalar(
        select(TeamMember.id)
        .where(TeamMember.project_id == project.id, TeamMember.user_id == user.id)
        .limit(1)
    )
    if existing:
        return False
    db.add(TeamMember(project_id=project.id, user_id=user.id, role=user.role or "Member"))
    names = [p.strip() for p in str(project.pic or "").split(",") if p.strip()]
    display = (user.name or "").strip()
    if display and display.lower() not in {n.lower() for n in names}:
        names.append(display)
        project.pic = ", ".join(names)
    return True


def invite_emails_to_project(
    db: Session,
    *,
    project: Project,
    emails: list[str],
    inviter: User,
) -> list[dict]:
    results: list[dict] = []
    role_code = _default_invite_role(db)
    for email in normalize_invite_emails(emails):
        row: dict = {"email": email, "ok": False, "status": "error", "message": ""}
        try:
            user = db.scalar(select(User).where(User.email == email).limit(1))
            created = False
            if user is None:
                temp = generate_temp_password()
                user = User(
                    name=_name_from_email(email),
                    email=email,
                    role=role_code,
                    avatar_url=default_avatar(_name_from_email(email)),
                    is_active=True,
                    password_hash=hash_password(temp),
                    must_change_password=True,
                    primary_bidang_id=None,
                    placement_version=0,
                )
                db.add(user)
                db.flush()
                created = True
            elif not user.is_active:
                row["message"] = "Akun nonaktif. Aktifkan dulu di Users."
                results.append(row)
                continue

            added = ensure_team_member(db, project, user)
            db.flush()

            # Password setup only for brand-new accounts.
            # Existing users (even if prior invite unfinished) are only added as member/PIC.
            if created:
                send_project_invite_email(
                    db,
                    user=user,
                    project_name=project.name,
                    inviter_name=inviter.name or inviter.email,
                    project_id=project.id,
                )
                row["status"] = "invited"
                row["message"] = "User baru: undangan atur password dikirim."
            else:
                send_project_added_email(
                    db,
                    to_email=user.email,
                    name=user.name,
                    project_name=project.name,
                    inviter_name=inviter.name or inviter.email,
                    project_id=project.id,
                )
                if added:
                    row["status"] = "added"
                    row["message"] = "User terdaftar: ditambahkan ke tim/PIC project."
                else:
                    row["status"] = "already_member"
                    row["message"] = "Sudah menjadi anggota/PIC project."
            row["ok"] = True
            row["user_id"] = user.id
            row["created"] = created
            row["added"] = added
            row["password_setup"] = bool(created)
        except Exception as exc:  # noqa: BLE001
            row["ok"] = False
            row["status"] = "error"
            row["message"] = str(exc) or "Gagal mengundang"
        results.append(row)
    return results
