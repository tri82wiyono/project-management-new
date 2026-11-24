from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    Project,
    ProjectDiscussionMention,
    ProjectDiscussionMessage,
    User,
)
from app.schemas.schemas import ChatThreadListResponse, ChatThreadOut
from app.services import org_scope


def _preview(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def list_chat_threads(
    db: Session,
    *,
    user: User,
    q: str | None = None,
    limit: int = 100,
) -> ChatThreadListResponse:
    limit = max(1, min(int(limit or 100), 200))
    scope = org_scope.project_visibility_filter(db, user)

    project_stmt = select(Project).where(True)
    if scope is not None:
        project_stmt = project_stmt.where(scope)
    query = (q or "").strip()
    if query:
        like = f"%{query}%"
        project_stmt = project_stmt.where(Project.name.ilike(like))

    projects = list(db.scalars(project_stmt.order_by(Project.name.asc())).all())
    if not projects:
        return ChatThreadListResponse(items=[], total=0, unread_threads=0)

    project_ids = [p.id for p in projects]

    # Latest message id per project
    latest_id_rows = db.execute(
        select(
            ProjectDiscussionMessage.project_id,
            func.max(ProjectDiscussionMessage.id).label("max_id"),
        )
        .where(
            ProjectDiscussionMessage.project_id.in_(project_ids),
            ProjectDiscussionMessage.deleted_at.is_(None),
        )
        .group_by(ProjectDiscussionMessage.project_id)
    ).all()
    latest_ids = [int(row.max_id) for row in latest_id_rows if row.max_id]
    latest_by_project = {int(row.project_id): int(row.max_id) for row in latest_id_rows if row.max_id}

    latest_messages: dict[int, ProjectDiscussionMessage] = {}
    if latest_ids:
        rows = db.scalars(
            select(ProjectDiscussionMessage)
            .where(ProjectDiscussionMessage.id.in_(latest_ids))
            .options(selectinload(ProjectDiscussionMessage.author))
        ).all()
        for msg in rows:
            latest_messages[msg.project_id] = msg

    # Message counts
    count_rows = db.execute(
        select(
            ProjectDiscussionMessage.project_id,
            func.count().label("cnt"),
        )
        .where(
            ProjectDiscussionMessage.project_id.in_(project_ids),
            ProjectDiscussionMessage.deleted_at.is_(None),
        )
        .group_by(ProjectDiscussionMessage.project_id)
    ).all()
    counts = {int(row.project_id): int(row.cnt) for row in count_rows}

    # Unread mention counts for current user
    unread_rows = db.execute(
        select(
            ProjectDiscussionMessage.project_id,
            func.count().label("cnt"),
        )
        .select_from(ProjectDiscussionMention)
        .join(
            ProjectDiscussionMessage,
            ProjectDiscussionMessage.id == ProjectDiscussionMention.message_id,
        )
        .where(
            ProjectDiscussionMention.user_id == user.id,
            ProjectDiscussionMention.read_at.is_(None),
            ProjectDiscussionMessage.deleted_at.is_(None),
            ProjectDiscussionMessage.project_id.in_(project_ids),
        )
        .group_by(ProjectDiscussionMessage.project_id)
    ).all()
    unread_map = {int(row.project_id): int(row.cnt) for row in unread_rows}

    items: list[ChatThreadOut] = []
    for project in projects:
        msg = latest_messages.get(project.id)
        message_count = counts.get(project.id, 0)
        unread = unread_map.get(project.id, 0)
        # Keep rooms with activity, or rooms where user is a member (always show visible projects)
        # Prefer showing all visible projects so users can start chatting.
        focus = latest_by_project.get(project.id)
        open_url = f"/projects/{project.id}"
        if focus:
            open_url = f"/projects/{project.id}?focus_msg={focus}"

        items.append(
            ChatThreadOut(
                project_id=project.id,
                project_name=project.name,
                project_status=getattr(project.status, "value", str(project.status or "")),
                project_color=project.color or "#4F7CFF",
                last_message_id=msg.id if msg else None,
                last_message_preview=_preview(msg.body if msg else "") or (
                    "Belum ada pesan. Mulai diskusi project."
                ),
                last_message_at=msg.created_at if msg else None,
                last_author_name=(msg.author.name if msg and msg.author else ""),
                last_author_avatar_url=(msg.author.avatar_url if msg and msg.author else ""),
                unread_mentions=unread,
                message_count=message_count,
                open_url=open_url,
            )
        )

    items.sort(
        key=lambda item: (
            0 if item.unread_mentions else 1,
            -(item.last_message_at.timestamp() if item.last_message_at else 0),
            item.project_name.lower(),
        )
    )
    items = items[:limit]
    unread_threads = sum(1 for item in items if item.unread_mentions > 0)
    return ChatThreadListResponse(
        items=items,
        total=len(items),
        unread_threads=unread_threads,
    )
