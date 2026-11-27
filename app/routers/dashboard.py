from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.schemas.schemas import (
    AnalyticsResponse,
    CalendarResponse,
    ClassificationOverview,
    DashboardKPI,
    DashboardSprintOverview,
    KanbanBoard,
    OverdueAlert,
    ProjectProgress,
    TeamOverview,
    TimelineItem,
)
from app.services import dashboard as svc
from app.services.auth import require_permission

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpi", response_model=DashboardKPI)
def kpi(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> DashboardKPI:
    return svc.get_kpi(db, user=user)


@router.get("/progress", response_model=list[ProjectProgress])
def progress(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> list[ProjectProgress]:
    return svc.get_project_progress(db, user=user)


@router.get("/kanban", response_model=KanbanBoard)
def kanban(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> KanbanBoard:
    return svc.get_kanban(db, project_id, user=user)


@router.get("/timeline", response_model=list[TimelineItem])
def timeline(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> list[TimelineItem]:
    return svc.get_timeline(db, limit=None, user=user)


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> AnalyticsResponse:
    return svc.get_analytics(db, days, user=user)


@router.get("/calendar", response_model=CalendarResponse)
def calendar(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> CalendarResponse:
    return svc.get_calendar(db, year, month, user=user)


@router.get("/team", response_model=TeamOverview)
def team(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("dashboard.view")),
) -> TeamOverview:
    return svc.get_team_overview(db)


@router.get("/overdue", response_model=OverdueAlert)
def overdue(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> OverdueAlert:
    return svc.get_overdue_alert(db, user=user)


@router.get("/sprints", response_model=DashboardSprintOverview)
def sprints_overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> DashboardSprintOverview:
    return svc.get_sprint_overview(db, user=user)


@router.get("/classifications", response_model=ClassificationOverview)
def classifications_overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> ClassificationOverview:
    return svc.get_classification_overview(db, user=user)


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.view")),
) -> dict:
    """Bootstrap dashboard dalam 1 request."""
    return svc.get_dashboard_summary(db, user=user)
