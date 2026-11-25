from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.auth import require_permission
from app.services import reports as reports_svc
from app.services.audit import write_audit_log
from fastapi import Request

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/options")
def report_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> dict:
    return reports_svc.resolve_report_scope(db, user)


@router.get("/projects.xlsx")
def download_projects_report(
    request: Request,
    division_id: int | None = Query(default=None),
    bidang_id: int | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    project_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> Response:
    try:
        projects = reports_svc.query_report_projects(
            db,
            user,
            division_id=division_id,
            bidang_id=bidang_id,
            workspace_id=workspace_id,
            project_status=(project_status or "").strip() or None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    content = reports_svc.build_projects_excel(projects)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"project-report_{stamp}.xlsx"
    write_audit_log(
        db,
        action="report_exported",
        success=True,
        actor=user,
        message=f"Export report {len(projects)} project",
        request=request,
        meta={
            "division_id": division_id,
            "bidang_id": bidang_id,
            "workspace_id": workspace_id,
            "project_status": project_status,
            "project_count": len(projects),
        },
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
