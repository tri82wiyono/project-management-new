from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.schemas.schemas import ChatThreadListResponse
from app.services.auth import require_permission
from app.services import chat_threads as chat_svc

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/threads", response_model=ChatThreadListResponse)
def list_chat_threads(
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("projects.view")),
) -> ChatThreadListResponse:
    return chat_svc.list_chat_threads(db, user=user, q=q, limit=limit)
