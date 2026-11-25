"""Project/task Excel reports scoped by the caller's organizational role."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.models import Bidang, Division, Project, ProjectOwnerType, ProjectStatus, Task, User
from app.services import org_scope

PROJECT_STATUS_LABEL = {
    "backlog": "Backlog",
    "dev": "Dev",
    "sit": "SIT",
    "uat": "UAT",
    "to": "TO",
    "izin": "Izin",
    "release": "Release",
}

TASK_STATUS_LABEL = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "review": "Review",
    "done": "Done",
}


def _workspace_label(name: str) -> str:
    text = (name or "").strip()
    for prefix in ("Pemimpin Bidang ", "Bidang "):
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix) :].strip() or text
    return text


def resolve_report_scope(db: Session, user: User) -> dict:
    """Build filter options visible to the current user based on org role."""
    ctx = org_scope.load_user_org_context(db, user)

    if ctx.is_admin:
        divisions = list(
            db.scalars(select(Division).where(Division.is_active.is_(True)).order_by(Division.name)).all()
        )
        bidangs = list(
            db.scalars(select(Bidang).where(Bidang.is_active.is_(True)).order_by(Bidang.name)).all()
        )
        mode = "admin"
        locked_division_id = None
        locked_bidang_id = None
    elif ctx.led_division_ids:
        divisions = list(
            db.scalars(
                select(Division)
                .where(Division.id.in_(ctx.led_division_ids), Division.is_active.is_(True))
                .order_by(Division.name)
            ).all()
        )
        bidangs = list(
            db.scalars(
                select(Bidang)
                .where(Bidang.division_id.in_(ctx.led_division_ids), Bidang.is_active.is_(True))
                .order_by(Bidang.name)
            ).all()
        )
        mode = "division"
        locked_division_id = divisions[0].id if len(divisions) == 1 else None
        locked_bidang_id = None
    else:
        bidang_ids = set(ctx.led_bidang_ids)
        if ctx.primary_bidang_id:
            bidang_ids.add(ctx.primary_bidang_id)
        if bidang_ids:
            bidangs = list(
                db.scalars(
                    select(Bidang)
                    .where(Bidang.id.in_(bidang_ids), Bidang.is_active.is_(True))
                    .order_by(Bidang.name)
                ).all()
            )
            div_ids = {b.division_id for b in bidangs}
            divisions = list(
                db.scalars(
                    select(Division)
                    .where(Division.id.in_(div_ids), Division.is_active.is_(True))
                    .order_by(Division.name)
                ).all()
            )
            mode = "bidang"
            locked_division_id = divisions[0].id if len(divisions) == 1 else None
            locked_bidang_id = bidangs[0].id if len(bidangs) == 1 else None
        else:
            # Staff / member fallback — no org picker; export only visible membership projects.
            divisions = []
            bidangs = []
            mode = "member"
            locked_division_id = None
            locked_bidang_id = None

    return {
        "mode": mode,
        "locked_division_id": locked_division_id,
        "locked_bidang_id": locked_bidang_id,
        "can_choose_division": mode in {"admin", "division"} and len(divisions) > 1,
        "can_choose_bidang": mode in {"admin", "division"} or (mode == "bidang" and len(bidangs) > 1),
        "can_choose_workspace": mode in {"admin", "division"} or (mode == "bidang" and len(bidangs) > 1),
        "divisions": [
            {"id": d.id, "code": d.code, "name": d.name}
            for d in divisions
        ],
        "bidangs": [
            {
                "id": b.id,
                "code": b.code,
                "name": b.name,
                "label": _workspace_label(b.name),
                "division_id": b.division_id,
            }
            for b in bidangs
        ],
        "workspaces": [
            {
                "id": b.id,
                "code": b.code,
                "name": b.name,
                "label": _workspace_label(b.name),
                "division_id": b.division_id,
            }
            for b in bidangs
        ],
    }


def _allowed_bidang_ids(scope: dict) -> set[int] | None:
    if scope["mode"] == "admin":
        return None
    return {int(b["id"]) for b in scope["bidangs"]}


def _allowed_division_ids(scope: dict) -> set[int] | None:
    if scope["mode"] == "admin":
        return None
    return {int(d["id"]) for d in scope["divisions"]}


def query_report_projects(
    db: Session,
    user: User,
    *,
    division_id: int | None = None,
    bidang_id: int | None = None,
    workspace_id: int | None = None,
    project_status: str | None = None,
) -> list[Project]:
    scope = resolve_report_scope(db, user)
    target_bidang = bidang_id or workspace_id

    if scope["mode"] == "member":
        ctx = org_scope.load_user_org_context(db, user)
        ids = sorted(ctx.member_project_ids | ctx.assigned_project_ids)
        if not ids:
            return []
        stmt = (
            select(Project)
            .options(
                selectinload(Project.tasks).joinedload(Task.assignee),
                joinedload(Project.owner_division),
                joinedload(Project.owner_bidang),
            )
            .where(Project.id.in_(ids))
            .order_by(Project.name.asc(), Project.id.asc())
        )
        if project_status:
            try:
                stmt = stmt.where(Project.status == ProjectStatus(project_status))
            except ValueError as exc:
                raise PermissionError("Status project tidak valid") from exc
        return list(db.scalars(stmt).unique().all())

    allowed_div = _allowed_division_ids(scope)
    allowed_bid = _allowed_bidang_ids(scope)

    if scope["mode"] == "bidang" and scope.get("locked_bidang_id") and not target_bidang:
        target_bidang = scope["locked_bidang_id"]
    if scope["mode"] in {"bidang", "division"} and scope.get("locked_division_id") and not division_id:
        division_id = scope["locked_division_id"]

    if division_id is not None and allowed_div is not None and division_id not in allowed_div:
        raise PermissionError("Divisi di luar cakupan Anda")
    if target_bidang is not None and allowed_bid is not None and target_bidang not in allowed_bid:
        raise PermissionError("Bidang/workspace di luar cakupan Anda")

    filters = []
    vis = org_scope.project_visibility_filter(db, user)
    if vis is not None:
        filters.append(vis)

    if target_bidang is not None:
        filters.append(Project.owner_type == ProjectOwnerType.bidang.value)
        filters.append(Project.owner_bidang_id == target_bidang)
    elif division_id is not None:
        filters.append(Project.owner_division_id == division_id)
        if allowed_bid is not None:
            # Division leader: include Bidang-owned under division + division-owned.
            filters.append(
                Project.owner_type.in_(
                    [ProjectOwnerType.bidang.value, ProjectOwnerType.division.value]
                )
            )
    elif allowed_bid is not None and scope["mode"] == "bidang":
        filters.append(Project.owner_type == ProjectOwnerType.bidang.value)
        filters.append(Project.owner_bidang_id.in_(allowed_bid or [-1]))
    elif allowed_div is not None and scope["mode"] == "division":
        filters.append(Project.owner_division_id.in_(allowed_div or [-1]))

    if project_status:
        try:
            filters.append(Project.status == ProjectStatus(project_status))
        except ValueError as exc:
            raise PermissionError("Status project tidak valid") from exc

    stmt = (
        select(Project)
        .options(
            selectinload(Project.tasks).joinedload(Task.assignee),
            joinedload(Project.owner_division),
            joinedload(Project.owner_bidang),
        )
        .order_by(Project.name.asc(), Project.id.asc())
    )
    if filters:
        stmt = stmt.where(*filters)
    return list(db.scalars(stmt).unique().all())


def build_projects_excel(projects: list[Project]) -> bytes:
    wb = Workbook()
    ws_proj = wb.active
    ws_proj.title = "Projects"
    ws_task = wb.create_sheet("Tasks")

    header_fill = PatternFill("solid", fgColor="1F5FD6")
    header_font = Font(color="FFFFFF", bold=True)
    done_fill = PatternFill("solid", fgColor="DCFCE7")
    open_fill = PatternFill("solid", fgColor="FEF3C7")

    proj_headers = [
        "No",
        "Nama Project",
        "Status Project",
        "Progress %",
        "PIC",
        "Divisi",
        "Bidang / Workspace",
        "Start",
        "Target",
        "Jumlah Task",
        "Task Selesai",
        "Task Belum Selesai",
    ]
    task_headers = [
        "No",
        "Nama Project",
        "Status Project",
        "Nama Task / Modul",
        "Status Task",
        "Kategori",
        "Priority",
        "Assignee",
        "Due Date",
        "Selesai?",
    ]

    for col, title in enumerate(proj_headers, start=1):
        cell = ws_proj.cell(1, col, title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")
    for col, title in enumerate(task_headers, start=1):
        cell = ws_task.cell(1, col, title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    task_row = 2
    for idx, project in enumerate(projects, start=1):
        tasks = list(project.tasks or [])
        done_n = sum(1 for t in tasks if str(getattr(t.status, "value", t.status)) == "done")
        open_n = len(tasks) - done_n
        status_val = str(getattr(project.status, "value", project.status) or "")
        ownership = org_scope.ownership_summary(project)
        ws_proj.append(
            [
                idx,
                project.name,
                PROJECT_STATUS_LABEL.get(status_val, status_val),
                round(float(project.progress or 0), 1),
                project.pic or "",
                ownership.get("owner_division_name") or "",
                _workspace_label(ownership.get("owner_bidang_name") or "") or ownership.get("owner_bidang_name") or "",
                project.start_date.isoformat() if project.start_date else "",
                project.end_date.isoformat() if project.end_date else "",
                len(tasks),
                done_n,
                open_n,
            ]
        )
        status_cell = ws_proj.cell(idx + 1, 3)
        status_cell.fill = done_fill if status_val == "release" else open_fill

        if not tasks:
            ws_task.append(
                [
                    task_row - 1,
                    project.name,
                    PROJECT_STATUS_LABEL.get(status_val, status_val),
                    "(Belum ada task/modul)",
                    "-",
                    "",
                    "",
                    "",
                    "",
                    "Tidak",
                ]
            )
            task_row += 1
            continue

        for task in sorted(tasks, key=lambda t: (t.title or "").lower()):
            t_status = str(getattr(task.status, "value", task.status) or "")
            assignee_name = ""
            if task.assignee:
                assignee_name = task.assignee.name or ""
            ws_task.append(
                [
                    task_row - 1,
                    project.name,
                    PROJECT_STATUS_LABEL.get(status_val, status_val),
                    task.title,
                    TASK_STATUS_LABEL.get(t_status, t_status),
                    task.category or "",
                    task.priority or "",
                    assignee_name,
                    task.due_date.isoformat() if task.due_date else "",
                    "Ya" if t_status == "done" else "Tidak",
                ]
            )
            ws_task.cell(task_row, 5).fill = done_fill if t_status == "done" else open_fill
            task_row += 1

    for ws, widths in (
        (ws_proj, [6, 36, 14, 12, 28, 28, 36, 12, 12, 12, 12, 16]),
        (ws_task, [6, 36, 14, 40, 14, 14, 12, 22, 12, 10]),
    ):
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"

    meta = wb.create_sheet("Info", 0)
    meta["A1"] = "Project Management Report"
    meta["A1"].font = Font(bold=True, size=14)
    meta["A3"] = "Generated at (UTC)"
    meta["B3"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    meta["A4"] = "Total projects"
    meta["B4"] = len(projects)
    meta["A5"] = "Sheets"
    meta["B5"] = "Projects = ringkasan project; Tasks = detail task/modul + status"
    meta.column_dimensions["A"].width = 24
    meta.column_dimensions["B"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
