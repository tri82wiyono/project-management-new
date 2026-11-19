"""Import projects + modules from legacy Project Management Excel export."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import (
    Project,
    ProjectStatus,
    Task,
    TaskAssignee,
    TaskStatus,
    TeamMember,
    User,
)
from app.services.project_progress import recalculate_project_progress
from app.services.security import default_avatar, hash_password

DEFAULT_XLSX = Path(__file__).resolve().parent / "data" / "Project_Management_2026-11-18.xlsx"

COLORS = [
    "#4F7CFF",
    "#22C55E",
    "#F59E0B",
    "#8B5CF6",
    "#06B6D4",
    "#F97316",
    "#EC4899",
    "#14B8A6",
    "#6366F1",
    "#84CC16",
]

# Legacy nickname / short name → match against User.name / email
PIC_ALIASES: dict[str, list[str]] = {
    "roy": ["roy miduk", "roy"],
    "adhhal": ["adhhal"],
    "ali": ["muhammad ali", "ali husein", "ali"],
    "gilang": ["gilang"],
    "deno": ["denovriyanto", "deno"],
    "frandc": ["fran festus", "fran"],
    "fran": ["fran festus", "fran"],
    "tri wiyono": ["tri wiyono"],
    "tri": ["tri wiyono"],
}

KEADAAN_MAP = {
    "belum mulai": ProjectStatus.backlog,
    "berjalan": ProjectStatus.dev,
    "selesai": ProjectStatus.release,
}

MODULE_STATUS_TO_PROJECT = {
    "backlog": ProjectStatus.backlog,
    "development": ProjectStatus.dev,
    "dev": ProjectStatus.dev,
    "sit": ProjectStatus.sit,
    "uat": ProjectStatus.uat,
    "to": ProjectStatus.to,
    "perizinan": ProjectStatus.izin,
    "izin": ProjectStatus.izin,
    "release": ProjectStatus.release,
}

MODULE_STATUS_TO_TASK = {
    "backlog": TaskStatus.todo,
    "development": TaskStatus.in_progress,
    "dev": TaskStatus.in_progress,
    "sit": TaskStatus.review,
    "uat": TaskStatus.review,
    "to": TaskStatus.review,
    "perizinan": TaskStatus.review,
    "izin": TaskStatus.review,
    "release": TaskStatus.done,
}

PROJECT_STATUS_RANK = {
    ProjectStatus.backlog: 0,
    ProjectStatus.dev: 1,
    ProjectStatus.sit: 2,
    ProjectStatus.uat: 3,
    ProjectStatus.to: 4,
    ProjectStatus.izin: 5,
    ProjectStatus.release: 6,
}


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _as_date(value, fallback: date | None = None) -> date | None:
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return fallback


def _priority(value) -> str:
    text = str(value or "medium").strip().lower()
    if text in {"critical", "high", "tinggi"}:
        return "high"
    if text in {"low", "rendah"}:
        return "low"
    return "medium"


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().upper()


def _project_aliases(name: str) -> set[str]:
    base = _norm_name(name)
    aliases = {base}
    if base.startswith("NEW "):
        aliases.add(base[4:].strip())
    else:
        aliases.add(f"NEW {base}")
    return aliases


def _split_pics(value) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;/|]+", str(value))
    return [p.strip() for p in parts if p and p.strip()]


def _resolve_user(users: list[User], token: str) -> User | None:
    key = token.strip().lower()
    if not key:
        return None
    aliases = PIC_ALIASES.get(key, [key])
    for user in users:
        hay = f"{user.name} {user.email}".lower()
        for alias in aliases:
            if alias in hay or hay.startswith(alias):
                return user
        if user.name.lower() == key:
            return user
    return None


def _ensure_user(db: Session, name: str, users: list[User]) -> User:
    existing = _resolve_user(users, name)
    if existing:
        return existing
    email_local = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")
    email = f"{email_local}@banksumut.co.id"
    clash = db.scalar(select(User).where(User.email == email))
    if clash:
        users.append(clash)
        return clash
    user = User(
        name=name.strip(),
        email=email,
        role="Member",
        avatar_url=default_avatar(name),
        is_active=True,
        password_hash=hash_password("ChangeMe@123"),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    users.append(user)
    return user


def _derive_project_status(keadaan: str | None, module_statuses: list[str]) -> ProjectStatus:
    mapped_modules = [
        MODULE_STATUS_TO_PROJECT[s]
        for s in module_statuses
        if s in MODULE_STATUS_TO_PROJECT
    ]
    if mapped_modules:
        # Use the least-advanced module so "Release" is not set while others lag.
        return min(mapped_modules, key=lambda st: PROJECT_STATUS_RANK[st])

    key = (keadaan or "").strip().lower()
    return KEADAAN_MAP.get(key, ProjectStatus.backlog)


def _parse_sheet(ws) -> dict | None:
    title = _clean_text(ws.cell(1, 1).value) or ws.title
    if not title:
        return None

    manager = _clean_text(ws.cell(2, 2).value)
    start = _as_date(ws.cell(2, 4).value)
    end = _as_date(ws.cell(2, 6).value)
    keadaan = _clean_text(ws.cell(3, 4).value)
    progress_raw = ws.cell(3, 6).value
    try:
        sheet_progress = float(progress_raw) if progress_raw is not None else None
    except (TypeError, ValueError):
        sheet_progress = None
    description = _clean_text(ws.cell(4, 2).value)

    modules: list[dict] = []
    for row in range(7, ws.max_row + 1):
        modul = _clean_text(ws.cell(row, 2).value)
        if not modul or modul.lower().startswith("belum ada"):
            # Some sheets put "Belum ada modul" in column A
            maybe = _clean_text(ws.cell(row, 1).value)
            if maybe and maybe.lower().startswith("belum ada"):
                continue
            if not modul:
                continue
        status_raw = _clean_text(ws.cell(row, 3).value) or "Backlog"
        pics = _split_pics(ws.cell(row, 4).value)
        priority = _priority(ws.cell(row, 5).value)
        m_start = _as_date(ws.cell(row, 6).value)
        m_due = _as_date(ws.cell(row, 7).value)
        desc = _clean_text(ws.cell(row, 9).value)
        modules.append(
            {
                "title": modul[:200],
                "status_raw": status_raw,
                "pics": pics,
                "priority": priority,
                "start": m_start,
                "due": m_due or m_start,
                "description": desc,
            }
        )

    return {
        "name": title[:160],
        "manager": manager,
        "start": start,
        "end": end,
        "keadaan": keadaan,
        "sheet_progress": sheet_progress,
        "description": description,
        "modules": modules,
    }


def import_workbook(db: Session, path: Path) -> dict:
    wb = load_workbook(path, data_only=True)
    users = list(db.scalars(select(User).order_by(User.id.asc())).all())
    # Ensure known managers exist
    for manager_name in ("Tri Wiyono",):
        _ensure_user(db, manager_name, users)

    existing_projects = list(db.scalars(select(Project)).all())
    by_alias: dict[str, Project] = {}
    for project in existing_projects:
        for alias in _project_aliases(project.name):
            by_alias[alias] = project

    created = updated = modules_imported = 0
    seen_titles: set[str] = set()

    for index, sheet_name in enumerate(wb.sheetnames):
        parsed = _parse_sheet(wb[sheet_name])
        if not parsed:
            continue

        # Keep sheet identity when multiple sheets share the same title (e.g. EWS / EWS (2)).
        display_name = parsed["name"]
        if _norm_name(display_name) in seen_titles and _norm_name(display_name) != _norm_name(sheet_name):
            display_name = sheet_name.strip()[:160]
        seen_titles.add(_norm_name(display_name))
        parsed["name"] = display_name

        module_status_keys = [
            (m["status_raw"] or "").strip().lower() for m in parsed["modules"]
        ]
        status = _derive_project_status(parsed["keadaan"], module_status_keys)

        starts = [d for d in [parsed["start"], *[m["start"] for m in parsed["modules"]]] if d]
        ends = [d for d in [parsed["end"], *[m["due"] for m in parsed["modules"]]] if d]
        start_date = min(starts) if starts else date.today()
        end_date = max(ends) if ends else start_date + timedelta(days=90)
        if end_date < start_date:
            end_date = start_date + timedelta(days=90)

        # Project PIC names (manager + unique module PICs resolved to full names)
        pic_names: list[str] = []
        member_ids: list[int] = []
        if parsed["manager"]:
            manager_user = _ensure_user(db, parsed["manager"], users)
            pic_names.append(manager_user.name)
            member_ids.append(manager_user.id)
        for module in parsed["modules"]:
            for token in module["pics"]:
                user = _resolve_user(users, token) or _ensure_user(db, token, users)
                if user.name not in pic_names:
                    pic_names.append(user.name)
                if user.id not in member_ids:
                    member_ids.append(user.id)

        aliases = _project_aliases(parsed["name"])
        project = None
        for alias in aliases:
            if alias in by_alias:
                project = by_alias[alias]
                break

        color = COLORS[index % len(COLORS)]
        if project is None:
            project = Project(
                name=parsed["name"],
                description=parsed["description"],
                pic=", ".join(pic_names)[:500],
                status=status,
                progress=0,
                color=color,
                start_date=start_date,
                end_date=end_date,
            )
            db.add(project)
            db.flush()
            created += 1
        else:
            project.name = parsed["name"]
            project.description = parsed["description"]
            project.pic = ", ".join(pic_names)[:500]
            project.status = status
            project.color = color
            project.start_date = start_date
            project.end_date = end_date
            updated += 1

        for alias in _project_aliases(project.name):
            by_alias[alias] = project

        # Replace members
        project.members.clear()
        db.flush()
        for user_id in member_ids:
            user = next(u for u in users if u.id == user_id)
            db.add(TeamMember(project_id=project.id, user_id=user.id, role=user.role))

        # Replace tasks/modules for this project
        db.execute(delete(TaskAssignee).where(TaskAssignee.task_id.in_(select(Task.id).where(Task.project_id == project.id))))
        db.execute(delete(Task).where(Task.project_id == project.id))
        db.flush()

        for module in parsed["modules"]:
            status_key = (module["status_raw"] or "backlog").strip().lower()
            task_status = MODULE_STATUS_TO_TASK.get(status_key, TaskStatus.todo)
            assignee_users: list[User] = []
            for token in module["pics"]:
                user = _resolve_user(users, token)
                if user and user not in assignee_users:
                    assignee_users.append(user)

            due = module["due"] or end_date
            task = Task(
                project_id=project.id,
                title=module["title"],
                description=module["description"]
                or f"Status modul: {module['status_raw']}",
                category=module["status_raw"][:60] if module["status_raw"] else "General",
                status=task_status,
                priority=module["priority"],
                due_date=due,
                assignee_id=assignee_users[0].id if assignee_users else None,
                completed_at=(
                    datetime.combine(due, datetime.min.time(), tzinfo=timezone.utc)
                    if task_status == TaskStatus.done
                    else None
                ),
            )
            db.add(task)
            db.flush()
            for user in assignee_users:
                db.add(TaskAssignee(task_id=task.id, user_id=user.id))
            modules_imported += 1

        recalculate_project_progress(db, project.id)
        # Keep spreadsheet progress as fallback when no modules
        if not parsed["modules"] and parsed["sheet_progress"] is not None:
            project.progress = max(0.0, min(100.0, float(parsed["sheet_progress"])))

    db.commit()
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    total_tasks = db.scalar(select(func.count()).select_from(Task)) or 0
    return {
        "created": created,
        "updated": updated,
        "modules": modules_imported,
        "projects_total": total_projects,
        "tasks_total": total_tasks,
    }


def main(path: str | None = None) -> None:
    xlsx = Path(path) if path else DEFAULT_XLSX
    if not xlsx.exists():
        raise SystemExit(f"File not found: {xlsx}")
    db = SessionLocal()
    try:
        result = import_workbook(db, xlsx)
        print(
            f"Import selesai: created={result['created']} updated={result['updated']} "
            f"modules={result['modules']} | DB projects={result['projects_total']} tasks={result['tasks_total']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else None)
