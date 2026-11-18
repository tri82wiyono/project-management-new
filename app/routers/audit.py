from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.services.audit import audit_summary, list_audit_logs
from app.services.auth import require_permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def get_audit_logs(
    q: str | None = None,
    action: str | None = None,
    category: str | None = None,
    success: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("audit.view")),
) -> dict:
    cat = (category or "").strip().lower() or None
    if cat and cat not in {"login", "email"}:
        cat = None
    return list_audit_logs(
        db,
        q=q,
        action=action,
        category=cat,
        success=success,
        page=page,
        page_size=page_size,
    )


@router.get("/summary")
def get_audit_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("audit.view")),
) -> dict:
    return audit_summary(db)
