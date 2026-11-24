from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    ProjectDiscussionMention,
    ProjectDiscussionMessage,
    User,
)
from app.schemas.schemas import MentionNotificationListResponse, MentionNotificationOut


def _preview(text: str, limit: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _to_out(row: ProjectDiscussionMention) -> MentionNotificationOut:
    message = row.message
    project = message.project if message else None
    author = message.author if message else None
    project_id = message.project_id if message else 0
    message_id = message.id if message else 0
    return MentionNotificationOut(
        id=row.id,
        project_id=project_id,
        project_name=project.name if project else f"Project #{project_id}",
        message_id=message_id,
        body_preview=_preview("" if (message and message.deleted_at) else (message.body if message else "")),
        actor_name=author.name if author else "Pengguna",
        actor_avatar_url=author.avatar_url if author else "",
        actor_role=author.role if author else "",
        created_at=row.created_at or (message.created_at if message else datetime.now(timezone.utc)),
        is_read=row.read_at is not None,
        open_url=f"/projects/{project_id}?focus_msg={message_id}&notif={row.id}",
    )


def _base_query(user_id: int):
    return (
        select(ProjectDiscussionMention)
        .join(ProjectDiscussionMessage, ProjectDiscussionMessage.id == ProjectDiscussionMention.message_id)
        .where(
            ProjectDiscussionMention.user_id == user_id,
            ProjectDiscussionMessage.deleted_at.is_(None),
        )
        .options(
            selectinload(ProjectDiscussionMention.message).selectinload(ProjectDiscussionMessage.author),
            selectinload(ProjectDiscussionMention.message).selectinload(ProjectDiscussionMessage.project),
        )
    )


def list_notifications(
    db: Session,
    *,
    user: User,
    unread_only: bool = False,
    limit: int = 30,
) -> MentionNotificationListResponse:
    limit = max(1, min(int(limit or 30), 100))
    stmt = _base_query(user.id)
    if unread_only:
        stmt = stmt.where(ProjectDiscussionMention.read_at.is_(None))
    stmt = stmt.order_by(
        ProjectDiscussionMention.read_at.is_(None).desc(),
        ProjectDiscussionMention.created_at.desc(),
        ProjectDiscussionMention.id.desc(),
    ).limit(limit)

    rows = list(db.scalars(stmt).all())
    unread_count = (
        db.scalar(
            select(func.count())
            .select_from(ProjectDiscussionMention)
            .join(
                ProjectDiscussionMessage,
                ProjectDiscussionMessage.id == ProjectDiscussionMention.message_id,
            )
            .where(
                ProjectDiscussionMention.user_id == user.id,
                ProjectDiscussionMention.read_at.is_(None),
                ProjectDiscussionMessage.deleted_at.is_(None),
            )
        )
        or 0
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(ProjectDiscussionMention)
            .join(
                ProjectDiscussionMessage,
                ProjectDiscussionMessage.id == ProjectDiscussionMention.message_id,
            )
            .where(
                ProjectDiscussionMention.user_id == user.id,
                ProjectDiscussionMessage.deleted_at.is_(None),
            )
        )
        or 0
    )
    return MentionNotificationListResponse(
        items=[_to_out(row) for row in rows],
        unread_count=int(unread_count),
        total=int(total),
    )


def unread_count(db: Session, *, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProjectDiscussionMention)
            .join(
                ProjectDiscussionMessage,
                ProjectDiscussionMessage.id == ProjectDiscussionMention.message_id,
            )
            .where(
                ProjectDiscussionMention.user_id == user_id,
                ProjectDiscussionMention.read_at.is_(None),
                ProjectDiscussionMessage.deleted_at.is_(None),
            )
        )
        or 0
    )


def mark_read(
    db: Session,
    *,
    user: User,
    notification_id: int | None = None,
    message_id: int | None = None,
    mark_all: bool = False,
) -> MentionNotificationListResponse:
    now = datetime.now(timezone.utc)
    if mark_all:
        rows = list(
            db.scalars(
                select(ProjectDiscussionMention).where(
                    ProjectDiscussionMention.user_id == user.id,
                    ProjectDiscussionMention.read_at.is_(None),
                )
            ).all()
        )
        for row in rows:
            row.read_at = now
        db.commit()
        return list_notifications(db, user=user)

    if notification_id:
        row = db.get(ProjectDiscussionMention, notification_id)
        if not row or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
        if row.read_at is None:
            row.read_at = now
            db.commit()
        return list_notifications(db, user=user)

    if message_id:
        rows = list(
            db.scalars(
                select(ProjectDiscussionMention).where(
                    ProjectDiscussionMention.user_id == user.id,
                    ProjectDiscussionMention.message_id == message_id,
                    ProjectDiscussionMention.read_at.is_(None),
                )
            ).all()
        )
        for row in rows:
            row.read_at = now
        db.commit()
        return list_notifications(db, user=user)

    raise HTTPException(status_code=400, detail="Parameter mark-read tidak valid")
