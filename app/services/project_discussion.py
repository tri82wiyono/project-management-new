from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.models import (
    ProjectDiscussionAttachment,
    ProjectDiscussionMention,
    ProjectDiscussionMessage,
    ProjectDiscussionReaction,
    User,
)
from app.schemas.schemas import (
    DiscussionAttachmentOut,
    DiscussionAuthorOut,
    DiscussionListResponse,
    DiscussionMentionOut,
    DiscussionMessageOut,
    DiscussionParentPreview,
    DiscussionReactionOut,
)
from app.services.upload_security import resolve_under, validate_file_content

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".txt",
    ".csv",
    ".zip",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_REACTIONS = {"👍", "❤️", "😄", "🎉", "✅", "👀", "🔥", "🙏"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\s()]+")
MAX_ATTACHMENTS = 5
MAX_BODY = 8000


def uploads_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def discussion_dir(project_id: int) -> Path:
    path = uploads_root() / "projects" / str(project_id) / "discussion"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_original_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "file").strip()) or "file"
    return cleaned[:200]


def _extension(name: str) -> str:
    return Path(name or "").suffix.lower()


def _preview(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _attachment_out(att: ProjectDiscussionAttachment, project_id: int) -> DiscussionAttachmentOut:
    return DiscussionAttachmentOut(
        id=att.id,
        kind=att.kind or "file",
        original_name=att.original_name,
        content_type=att.content_type or "application/octet-stream",
        size_bytes=int(att.size_bytes or 0),
        url=f"/api/projects/{project_id}/discussion/attachments/{att.id}",
    )


def message_to_out(
    row: ProjectDiscussionMessage,
    *,
    current_user_id: int | None = None,
) -> DiscussionMessageOut:
    is_deleted = row.deleted_at is not None
    author = row.author
    reactions_map: dict[str, list[int]] = defaultdict(list)
    for reaction in row.reactions or []:
        reactions_map[reaction.emoji].append(reaction.user_id)

    reaction_out = [
        DiscussionReactionOut(
            emoji=emoji,
            count=len(user_ids),
            reacted_by_me=bool(current_user_id and current_user_id in user_ids),
            user_ids=user_ids,
        )
        for emoji, user_ids in sorted(reactions_map.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    parent_preview = None
    if row.parent_id and row.parent is not None:
        parent_body = "" if row.parent.deleted_at else (row.parent.body or "")
        parent_preview = DiscussionParentPreview(
            id=row.parent.id,
            author_name=(row.parent.author.name if row.parent.author else "Pengguna"),
            body_preview=_preview(parent_body) or "(pesan dihapus)",
        )

    return DiscussionMessageOut(
        id=row.id,
        project_id=row.project_id,
        body="" if is_deleted else (row.body or ""),
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_deleted=is_deleted,
        author=DiscussionAuthorOut(
            id=author.id if author else 0,
            name=author.name if author else "Pengguna",
            role=author.role if author else "",
            avatar_url=author.avatar_url if author else "",
        ),
        parent=parent_preview,
        attachments=[]
        if is_deleted
        else [_attachment_out(att, row.project_id) for att in (row.attachments or [])],
        reactions=reaction_out,
        mentions=[
            DiscussionMentionOut(id=m.user.id, name=m.user.name)
            for m in (row.mentions or [])
            if m.user is not None
        ],
    )


def _message_query():
    return (
        select(ProjectDiscussionMessage)
        .options(
            selectinload(ProjectDiscussionMessage.author),
            selectinload(ProjectDiscussionMessage.parent).selectinload(ProjectDiscussionMessage.author),
            selectinload(ProjectDiscussionMessage.attachments),
            selectinload(ProjectDiscussionMessage.reactions),
            selectinload(ProjectDiscussionMessage.mentions).selectinload(ProjectDiscussionMention.user),
        )
    )


def list_messages(
    db: Session,
    *,
    project_id: int,
    current_user_id: int | None,
    after_id: int | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> DiscussionListResponse:
    limit = max(1, min(int(limit or 50), 100))
    stmt = _message_query().where(ProjectDiscussionMessage.project_id == project_id)
    if after_id:
        stmt = stmt.where(ProjectDiscussionMessage.id > after_id).order_by(
            ProjectDiscussionMessage.id.asc()
        )
    elif before_id:
        stmt = stmt.where(ProjectDiscussionMessage.id < before_id).order_by(
            ProjectDiscussionMessage.id.desc()
        )
    else:
        stmt = stmt.order_by(ProjectDiscussionMessage.id.desc())

    rows = list(db.scalars(stmt.limit(limit + 1)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    if not after_id:
        rows.reverse()

    total = (
        db.scalar(
            select(func.count())
            .select_from(ProjectDiscussionMessage)
            .where(ProjectDiscussionMessage.project_id == project_id)
        )
        or 0
    )
    return DiscussionListResponse(
        items=[message_to_out(row, current_user_id=current_user_id) for row in rows],
        total=int(total),
        has_more=has_more,
    )


def get_message(db: Session, project_id: int, message_id: int) -> ProjectDiscussionMessage | None:
    return db.scalar(
        _message_query().where(
            ProjectDiscussionMessage.id == message_id,
            ProjectDiscussionMessage.project_id == project_id,
        )
    )


async def create_message(
    db: Session,
    *,
    project_id: int,
    author: User,
    body: str,
    parent_id: int | None,
    mention_ids: list[int],
    files: list[UploadFile] | None,
) -> DiscussionMessageOut:
    text = (body or "").strip()
    incoming = [f for f in (files or []) if f and f.filename]
    if not text and not incoming:
        raise HTTPException(status_code=400, detail="Pesan atau lampiran wajib diisi")
    if len(text) > MAX_BODY:
        raise HTTPException(status_code=400, detail=f"Pesan terlalu panjang (maks {MAX_BODY} karakter)")
    if len(incoming) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"Maksimal {MAX_ATTACHMENTS} lampiran per pesan")

    parent = None
    if parent_id:
        parent = get_message(db, project_id, parent_id)
        if not parent or parent.deleted_at is not None:
            raise HTTPException(status_code=400, detail="Pesan yang dibalas tidak ditemukan")

    mention_ids = sorted({int(x) for x in (mention_ids or []) if int(x) > 0})
    mention_users: list[User] = []
    if mention_ids:
        mention_users = list(
            db.scalars(select(User).where(User.id.in_(mention_ids), User.is_active.is_(True))).all()
        )
        found = {u.id for u in mention_users}
        missing = [mid for mid in mention_ids if mid not in found]
        if missing:
            raise HTTPException(status_code=400, detail="Mention berisi user yang tidak valid")

    row = ProjectDiscussionMessage(
        project_id=project_id,
        author_id=author.id,
        body=text,
        parent_id=parent.id if parent else None,
    )
    db.add(row)
    db.flush()

    for user in mention_users:
        db.add(ProjectDiscussionMention(message_id=row.id, user_id=user.id))

    settings = get_settings()
    max_bytes = int(settings.max_upload_bytes)
    dest = discussion_dir(project_id)
    for upload in incoming:
        original = _safe_original_name(upload.filename or "file")
        ext = _extension(original)
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Tipe file tidak diizinkan: {original}",
            )
        data = await upload.read()
        size = len(data)
        if size <= 0:
            raise HTTPException(status_code=400, detail=f"File kosong: {original}")
        if size > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File terlalu besar (maks {max_bytes // (1024 * 1024)} MB): {original}",
            )
        content_type = validate_file_content(data=data, ext=ext, original_name=original)
        stored = f"{uuid.uuid4().hex}{ext}"
        (dest / stored).write_bytes(data)
        kind = "image" if ext in IMAGE_EXTENSIONS else "file"
        db.add(
            ProjectDiscussionAttachment(
                message_id=row.id,
                kind=kind,
                original_name=original,
                stored_name=stored,
                content_type=content_type[:120],
                size_bytes=size,
            )
        )

    db.commit()
    loaded = get_message(db, project_id, row.id)
    assert loaded is not None
    return message_to_out(loaded, current_user_id=author.id)


def soft_delete_message(
    db: Session,
    *,
    project_id: int,
    message_id: int,
    actor: User,
    can_manage: bool,
) -> DiscussionMessageOut:
    row = get_message(db, project_id, message_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    if row.author_id != actor.id and not can_manage:
        raise HTTPException(status_code=403, detail="Anda tidak dapat menghapus pesan ini")
    row.deleted_at = datetime.now(timezone.utc)
    row.body = ""
    db.commit()
    loaded = get_message(db, project_id, message_id)
    assert loaded is not None
    return message_to_out(loaded, current_user_id=actor.id)


def toggle_reaction(
    db: Session,
    *,
    project_id: int,
    message_id: int,
    user: User,
    emoji: str,
) -> DiscussionMessageOut:
    emoji = (emoji or "").strip()
    if emoji not in ALLOWED_REACTIONS:
        raise HTTPException(status_code=400, detail="Emoji reaksi tidak didukung")
    row = get_message(db, project_id, message_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")

    existing = db.scalar(
        select(ProjectDiscussionReaction).where(
            ProjectDiscussionReaction.message_id == message_id,
            ProjectDiscussionReaction.user_id == user.id,
            ProjectDiscussionReaction.emoji == emoji,
        )
    )
    if existing:
        db.delete(existing)
    else:
        db.add(
            ProjectDiscussionReaction(
                message_id=message_id,
                user_id=user.id,
                emoji=emoji,
            )
        )
    db.commit()
    loaded = get_message(db, project_id, message_id)
    assert loaded is not None
    return message_to_out(loaded, current_user_id=user.id)


def resolve_attachment_path(att: ProjectDiscussionAttachment, project_id: int) -> Path:
    return resolve_under(discussion_dir(project_id), att.stored_name)
