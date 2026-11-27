"""One-shot import: List_Solusi ITGOV → projects/tasks under Bidang Government.

Usage (inside app container / venv):
  python -m app.import_list_solusi_gov
  python -m app.import_list_solusi_gov --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Project, ProjectOwnerType, Task, TaskStatus, TeamMember, User
from app.services.project_progress import recalculate_project_progress

DEFAULT_JSON = Path(__file__).resolve().parent / "data" / "list_solusi_gov_import.json"
IMPORT_MARKER = "[import:itgov-list-solusi-2026-06]"
OWNER_BIDANG_ID = 5
OWNER_DIVISION_ID = 1


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_import(db: Session, payload: dict, *, dry_run: bool = False) -> dict:
    admin = db.scalar(select(User).where(User.email == "admin@banksumut.co.id").limit(1))
    if not admin:
        admin = db.scalar(select(User).order_by(User.id.asc()).limit(1))
    if not admin:
        raise RuntimeError("No user found to own imported projects")

    fernando = db.scalar(
        select(User).where(User.email == "fernando@banksumut.co.id").limit(1)
    )

    created_projects = 0
    skipped_projects = 0
    created_tasks = 0
    details: list[dict] = []

    for item in payload.get("projects") or []:
        name = str(item["name"]).strip()
        existing = db.scalar(
            select(Project).where(
                Project.name == name,
                Project.owner_bidang_id == OWNER_BIDANG_ID,
            ).limit(1)
        )
        if existing:
            skipped_projects += 1
            details.append({"name": name, "action": "skip_exists", "project_id": existing.id})
            continue

        desc = (item.get("description") or "").strip()
        if IMPORT_MARKER not in desc:
            desc = f"{desc}\n\n{IMPORT_MARKER}".strip()

        project = Project(
            name=name,
            description=desc,
            pic=str(item.get("pic") or "Fernando Sebayang"),
            status="backlog",
            progress=0,
            color=str(item.get("color") or "#1f5fd6"),
            start_date=_parse_date(item["start_date"]),
            end_date=_parse_date(item["end_date"]),
            developed_by=item.get("developed_by") or "internal",
            work_type=item.get("work_type") or "enhancement",
            work_categories=list(item.get("work_categories") or ["business_support"]),
            owner_type=ProjectOwnerType.bidang.value,
            owner_division_id=int(item.get("owner_division_id") or OWNER_DIVISION_ID),
            owner_bidang_id=int(item.get("owner_bidang_id") or OWNER_BIDANG_ID),
            ownership_classified_at=datetime.now(timezone.utc),
            ownership_classified_by_id=admin.id,
        )
        if dry_run:
            task_count = len(item.get("tasks") or [])
            created_projects += 1
            created_tasks += task_count
            details.append({"name": name, "action": "dry_create", "tasks": task_count})
            continue

        db.add(project)
        db.flush()

        db.add(TeamMember(project_id=project.id, user_id=admin.id, role="Owner"))
        if fernando and fernando.id != admin.id:
            db.add(TeamMember(project_id=project.id, user_id=fernando.id, role="Member"))

        task_n = 0
        for t in item.get("tasks") or []:
            status_raw = str(t.get("status") or "todo")
            try:
                status = TaskStatus(status_raw)
            except ValueError:
                status = TaskStatus.todo
            task = Task(
                project_id=project.id,
                title=str(t["title"])[:200],
                description=t.get("description"),
                category=str(t.get("category") or "Implementasi PEMDA")[:60],
                status=status,
                priority=str(t.get("priority") or "medium")[:20],
                completed_at=datetime.now(timezone.utc) if status == TaskStatus.done else None,
            )
            db.add(task)
            task_n += 1

        db.flush()
        recalculate_project_progress(db, project.id)
        created_projects += 1
        created_tasks += task_n
        details.append(
            {
                "name": name,
                "action": "created",
                "project_id": project.id,
                "tasks": task_n,
                "progress": project.progress,
                "status": str(project.status.value if hasattr(project.status, "value") else project.status),
            }
        )

    if not dry_run:
        db.commit()

    return {
        "created_projects": created_projects,
        "skipped_projects": skipped_projects,
        "created_tasks": created_tasks,
        "dry_run": dry_run,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import List_Solusi Government coverage")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = _load_payload(args.json)
    db = SessionLocal()
    try:
        result = run_import(db, payload, dry_run=args.dry_run)
    finally:
        db.close()

    print(json.dumps({k: result[k] for k in ("created_projects", "skipped_projects", "created_tasks", "dry_run")}, indent=2))
    for row in result["details"]:
        print(f"- {row['action']}: {row['name']}" + (f" tasks={row.get('tasks')}" if "tasks" in row else ""))


if __name__ == "__main__":
    main()
