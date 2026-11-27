"""Project/task Excel reports scoped by the caller's organizational role."""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
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

# Canonical order for report grouping (matches UI klasifikasi project).
CLASSIFICATION_ORDER = (
    "business_support",
    "supporting",
    "security",
    "compliance",
)
CLASSIFICATION_LABEL = {
    "business_support": "Business Support",
    "supporting": "Supporting",
    "security": "Security",
    "compliance": "Compliance",
    "rbb": "RBB",
    "inisiatif": "Inisiatif",
    "temuan_audit": "Temuan Audit",
    "regulasi": "Regulasi",
    "penugasan_manajemen": "Penugasan Manajemen",
    "operasional": "Operasional",
    "unassigned": "Belum diklasifikasi",
}
CLASSIFICATION_SECTION_FILL = {
    "business_support": "1D4ED8",
    "supporting": "0F766E",
    "security": "B45309",
    "compliance": "6D28D9",
    "unassigned": "475569",
}
DEFAULT_SECTION_FILL = "334155"


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


def _project_classification_key(project: Project) -> str:
    cats = getattr(project, "work_categories", None) or []
    for item in cats:
        key = str(item or "").strip()
        if key:
            return key
    return "unassigned"


def _classification_label(key: str) -> str:
    return CLASSIFICATION_LABEL.get(key, key.replace("_", " ").title() if key else "Belum diklasifikasi")


def _classification_sort_index(key: str) -> tuple[int, str]:
    if key in CLASSIFICATION_ORDER:
        return (CLASSIFICATION_ORDER.index(key), key)
    if key == "unassigned":
        return (len(CLASSIFICATION_ORDER) + 100, key)
    # Legacy / other values after the four main classifications.
    return (len(CLASSIFICATION_ORDER) + 10, key)


def _group_projects_by_classification(projects: list[Project]) -> list[tuple[str, list[Project]]]:
    buckets: dict[str, list[Project]] = defaultdict(list)
    for project in projects:
        buckets[_project_classification_key(project)].append(project)

    ordered_keys = sorted(buckets.keys(), key=_classification_sort_index)
    groups: list[tuple[str, list[Project]]] = []
    for key in ordered_keys:
        items = sorted(buckets[key], key=lambda p: ((p.name or "").lower(), p.id or 0))
        groups.append((key, items))
    return groups


def _write_section_header(
    ws,
    *,
    row: int,
    col_count: int,
    title: str,
    fill_hex: str,
) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=col_count)
    cell = ws.cell(row, 1, title)
    cell.fill = PatternFill("solid", fgColor=fill_hex)
    cell.font = Font(color="FFFFFF", bold=True, size=11)
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    thin = Border(bottom=Side(style="thin", color="FFFFFF"))
    for col in range(1, col_count + 1):
        ws.cell(row, col).fill = PatternFill("solid", fgColor=fill_hex)
        ws.cell(row, col).border = thin
    ws.row_dimensions[row].height = 22


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
        "Klasifikasi",
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
        "Klasifikasi",
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

    groups = _group_projects_by_classification(projects)
    class_counts: list[tuple[str, int]] = []

    proj_row = 2
    task_row = 2
    global_proj_no = 0
    global_task_no = 0

    for class_key, class_projects in groups:
        label = _classification_label(class_key)
        fill_hex = CLASSIFICATION_SECTION_FILL.get(class_key, DEFAULT_SECTION_FILL)
        class_counts.append((label, len(class_projects)))

        _write_section_header(
            ws_proj,
            row=proj_row,
            col_count=len(proj_headers),
            title=f"{label}  ·  {len(class_projects)} project",
            fill_hex=fill_hex,
        )
        proj_row += 1

        _write_section_header(
            ws_task,
            row=task_row,
            col_count=len(task_headers),
            title=f"{label}  ·  {len(class_projects)} project",
            fill_hex=fill_hex,
        )
        task_row += 1

        for project in class_projects:
            global_proj_no += 1
            tasks = list(project.tasks or [])
            done_n = sum(1 for t in tasks if str(getattr(t.status, "value", t.status)) == "done")
            open_n = len(tasks) - done_n
            status_val = str(getattr(project.status, "value", project.status) or "")
            ownership = org_scope.ownership_summary(project)
            ws_proj.cell(proj_row, 1, global_proj_no)
            ws_proj.cell(proj_row, 2, label)
            ws_proj.cell(proj_row, 3, project.name)
            status_cell = ws_proj.cell(proj_row, 4, PROJECT_STATUS_LABEL.get(status_val, status_val))
            status_cell.fill = done_fill if status_val == "release" else open_fill
            ws_proj.cell(proj_row, 5, round(float(project.progress or 0), 1))
            ws_proj.cell(proj_row, 6, project.pic or "")
            ws_proj.cell(proj_row, 7, ownership.get("owner_division_name") or "")
            ws_proj.cell(
                proj_row,
                8,
                _workspace_label(ownership.get("owner_bidang_name") or "")
                or ownership.get("owner_bidang_name")
                or "",
            )
            ws_proj.cell(proj_row, 9, project.start_date.isoformat() if project.start_date else "")
            ws_proj.cell(proj_row, 10, project.end_date.isoformat() if project.end_date else "")
            ws_proj.cell(proj_row, 11, len(tasks))
            ws_proj.cell(proj_row, 12, done_n)
            ws_proj.cell(proj_row, 13, open_n)
            proj_row += 1

            if not tasks:
                global_task_no += 1
                ws_task.cell(task_row, 1, global_task_no)
                ws_task.cell(task_row, 2, label)
                ws_task.cell(task_row, 3, project.name)
                ws_task.cell(task_row, 4, PROJECT_STATUS_LABEL.get(status_val, status_val))
                ws_task.cell(task_row, 5, "(Belum ada task/modul)")
                ws_task.cell(task_row, 6, "-")
                ws_task.cell(task_row, 7, "")
                ws_task.cell(task_row, 8, "")
                ws_task.cell(task_row, 9, "")
                ws_task.cell(task_row, 10, "")
                ws_task.cell(task_row, 11, "Tidak")
                task_row += 1
                continue

            for task in sorted(tasks, key=lambda t: (t.title or "").lower()):
                global_task_no += 1
                t_status = str(getattr(task.status, "value", task.status) or "")
                assignee_name = ""
                if task.assignee:
                    assignee_name = task.assignee.name or ""
                ws_task.cell(task_row, 1, global_task_no)
                ws_task.cell(task_row, 2, label)
                ws_task.cell(task_row, 3, project.name)
                ws_task.cell(task_row, 4, PROJECT_STATUS_LABEL.get(status_val, status_val))
                ws_task.cell(task_row, 5, task.title)
                status_task_cell = ws_task.cell(
                    task_row, 6, TASK_STATUS_LABEL.get(t_status, t_status)
                )
                status_task_cell.fill = done_fill if t_status == "done" else open_fill
                ws_task.cell(task_row, 7, task.category or "")
                ws_task.cell(task_row, 8, task.priority or "")
                ws_task.cell(task_row, 9, assignee_name)
                ws_task.cell(task_row, 10, task.due_date.isoformat() if task.due_date else "")
                ws_task.cell(task_row, 11, "Ya" if t_status == "done" else "Tidak")
                task_row += 1

    for ws, widths in (
        (ws_proj, [6, 18, 36, 14, 12, 28, 28, 36, 12, 12, 12, 12, 16]),
        (ws_task, [6, 18, 36, 14, 40, 14, 14, 12, 22, 12, 10]),
    ):
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
        # Freeze header only; auto-filter skipped because section rows break contiguous tables.
        ws.freeze_panes = "A2"

    meta = wb.create_sheet("Info", 0)
    meta["A1"] = "Project Management Report"
    meta["A1"].font = Font(bold=True, size=14)
    meta["A3"] = "Generated at (UTC)"
    meta["B3"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    meta["A4"] = "Total projects"
    meta["B4"] = len(projects)
    meta["A5"] = "Grouping"
    meta["B5"] = (
        "Projects & Tasks dikelompokkan berdasarkan klasifikasi: "
        "Business Support, Supporting, Security, Compliance"
    )
    meta["A6"] = "Sheets"
    meta["B6"] = "Projects = ringkasan project; Tasks = detail task/modul + status"

    meta["A8"] = "Ringkasan klasifikasi"
    meta["A8"].font = Font(bold=True)
    meta["A9"] = "Klasifikasi"
    meta["B9"] = "Jumlah Project"
    meta["A9"].font = Font(bold=True)
    meta["B9"].font = Font(bold=True)
    for i, (label, count) in enumerate(class_counts, start=10):
        meta.cell(i, 1, label)
        meta.cell(i, 2, count)
    if not class_counts:
        meta.cell(10, 1, "(Tidak ada project)")
        meta.cell(10, 2, 0)

    meta.column_dimensions["A"].width = 28
    meta.column_dimensions["B"].width = 72

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
