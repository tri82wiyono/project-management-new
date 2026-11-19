from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import TicketAttachment, User
from app.schemas.schemas import TicketAttachmentOut
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
    ".txt",
    ".csv",
    ".zip",
}

MAX_ATTACHMENTS = 5
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\s()]+")


def uploads_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ticket_dir(ticket_id: int) -> Path:
    path = uploads_root() / "tickets" / str(ticket_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_original_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "attachment").strip()) or "attachment"
    return cleaned[:200]


def _extension(name: str) -> str:
    return Path(name or "").suffix.lower()


def attachment_to_out(row: TicketAttachment) -> TicketAttachmentOut:
    return TicketAttachmentOut(
        id=row.id,
        ticket_id=row.ticket_id,
        original_name=row.original_name,
        content_type=row.content_type or "application/octet-stream",
        size_bytes=int(row.size_bytes or 0),
        created_at=row.created_at,
        download_url=f"/api/tickets/{row.ticket_id}/attachments/{row.id}/download",
    )


def count_attachments(db: Session, ticket_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket_id)
        )
        or 0
    )


def _ensure_capacity(db: Session, ticket_id: int, adding: int) -> None:
    existing = count_attachments(db, ticket_id)
    if existing + adding > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Maksimal {MAX_ATTACHMENTS} lampiran per ticket (sudah {existing})",
        )


async def save_uploads(
    db: Session,
    *,
    ticket_id: int,
    files: list[UploadFile],
    user: User | None,
) -> list[TicketAttachmentOut]:
    settings = get_settings()
    max_bytes = int(settings.max_upload_bytes)

    incoming = [f for f in (files or []) if f and f.filename]
    if not incoming:
        raise HTTPException(status_code=400, detail="Tidak ada file yang diunggah")

    _ensure_capacity(db, ticket_id, len(incoming))

    saved: list[TicketAttachment] = []
    dest_dir = ticket_dir(ticket_id)

    for upload in incoming:
        original = _safe_original_name(upload.filename or "attachment")
        ext = _extension(original)
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tipe file tidak diizinkan: {original}. "
                    f"Izinkan: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
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
        path = dest_dir / stored
        path.write_bytes(data)

        row = TicketAttachment(
            ticket_id=ticket_id,
            original_name=original,
            stored_name=stored,
            content_type=content_type[:120],
            size_bytes=size,
            uploaded_by_id=user.id if user else None,
        )
        db.add(row)
        saved.append(row)

    db.commit()
    for row in saved:
        db.refresh(row)
    return [attachment_to_out(row) for row in saved]


def resolve_file_path(row: TicketAttachment) -> Path:
    return resolve_under(ticket_dir(row.ticket_id), row.stored_name)


def delete_attachment(db: Session, row: TicketAttachment) -> None:
    stored = row.stored_name
    ticket_id = row.ticket_id
    db.delete(row)
    db.commit()
    if stored:
        try:
            path = resolve_under(ticket_dir(ticket_id), stored)
            path.unlink()
        except (HTTPException, OSError):
            pass


def delete_ticket_files(ticket_id: int) -> None:
    folder = uploads_root() / "tickets" / str(ticket_id)
    if not folder.exists():
        return
    for child in folder.iterdir():
        try:
            if child.is_file():
                child.unlink()
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        pass
