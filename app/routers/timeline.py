from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.auth import require_permission
from app.services.timeline import get_timeline_page

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("")
def timeline_page_data(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("projects.view")),
) -> dict:
    today = date.today()
    return get_timeline_page(
        db,
        year=year or today.year,
        month=month or today.month,
        project_id=project_id,
    )
