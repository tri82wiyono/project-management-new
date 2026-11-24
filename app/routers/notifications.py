from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.schemas.schemas import MentionNotificationListResponse
from app.services.auth import require_user
from app.services import mention_notifications as notif_svc

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class MarkReadPayload(BaseModel):
    notification_id: int | None = None
    message_id: int | None = None
    mark_all: bool = False


@router.get("/mentions", response_model=MentionNotificationListResponse)
def list_mention_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> MentionNotificationListResponse:
    return notif_svc.list_notifications(
        db,
        user=user,
        unread_only=unread_only,
        limit=limit,
    )


@router.get("/mentions/unread-count")
def mention_unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return {"unread_count": notif_svc.unread_count(db, user_id=user.id)}


@router.post("/mentions/read", response_model=MentionNotificationListResponse)
def mark_mention_notifications_read(
    payload: MarkReadPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> MentionNotificationListResponse:
    return notif_svc.mark_read(
        db,
        user=user,
        notification_id=payload.notification_id,
        message_id=payload.message_id,
        mark_all=payload.mark_all,
    )
