from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import ProjectDocument, User
from app.schemas.schemas import ProjectDocumentOut
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

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\s()]+")


def uploads_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_dir(project_id: int) -> Path:
    path = uploads_root() / "projects" / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_original_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "document").strip()) or "document"
    return cleaned[:200]


def _extension(name: str) -> str:
    return Path(name or "").suffix.lower()


def _is_blocked_host(host: str) -> bool:
    """Reject loopback / link-local / private destinations (KKS-PM-09)."""
    import ipaddress
    import socket

    hostname = (host or "").strip().lower().rstrip(".")
    if not hostname:
        return True
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return True
    # Strip brackets for IPv6 literals.
    candidate = hostname[1:-1] if hostname.startswith("[") and hostname.endswith("]") else hostname
    try:
        ip = ipaddress.ip_address(candidate)
        return bool(
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass
    # Resolve hostname and reject if any address is non-public.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        # Unresolvable hosts are allowed as bookmarks (no server-side fetch),
        # but still block obvious internal names above.
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def _normalize_http_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL wajib diisi")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="URL harus dimulai dengan http:// atau https:// (mis. Google Drive)",
        )
    if len(url) > 2000:
        raise HTTPException(status_code=400, detail="URL terlalu panjang")
    host = parsed.hostname or ""
    if _is_blocked_host(host):
        raise HTTPException(
            status_code=400,
            detail="URL tujuan tidak diizinkan (localhost/IP privat/link-local ditolak).",
        )
    return url


def _title_from_url(url: str, title: str | None) -> str:
    cleaned = (title or "").strip()
    if cleaned:
        return _safe_original_name(cleaned)
    host = urlparse(url).netloc.replace("www.", "") or "Link"
    return _safe_original_name(f"Link {host}")


def document_to_out(doc: ProjectDocument) -> ProjectDocumentOut:
    kind = (doc.kind or "file").strip().lower() or "file"
    if kind == "url" and doc.external_url:
        open_url = doc.external_url
        download_url = doc.external_url
    else:
        open_url = f"/api/projects/{doc.project_id}/documents/{doc.id}/download"
        download_url = open_url
    return ProjectDocumentOut(
        id=doc.id,
        project_id=doc.project_id,
        kind=kind,
        original_name=doc.original_name,
        content_type=doc.content_type or "application/octet-stream",
        size_bytes=int(doc.size_bytes or 0),
        created_at=doc.created_at,
        external_url=doc.external_url,
        download_url=download_url,
        open_url=open_url,
    )


def list_documents(db: Session, project_id: int) -> list[ProjectDocumentOut]:
    rows = db.scalars(
        select(ProjectDocument)
        .where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.created_at.asc(), ProjectDocument.id.asc())
    ).all()
    return [document_to_out(row) for row in rows]


def count_documents(db: Session, project_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
        )
        or 0
    )


def _ensure_capacity(db: Session, project_id: int, adding: int) -> None:
    max_docs = int(get_settings().max_project_documents)
    existing = count_documents(db, project_id)
    if existing + adding > max_docs:
        raise HTTPException(
            status_code=400,
            detail=f"Maksimal {max_docs} dokumen per project (sudah {existing})",
        )


async def save_uploads(
    db: Session,
    *,
    project_id: int,
    files: list[UploadFile],
    user: User | None,
) -> list[ProjectDocumentOut]:
    settings = get_settings()
    max_bytes = int(settings.max_upload_bytes)

    incoming = [f for f in (files or []) if f and f.filename]
    if not incoming:
        raise HTTPException(status_code=400, detail="Tidak ada file yang diunggah")

    _ensure_capacity(db, project_id, len(incoming))

    saved: list[ProjectDocument] = []
    dest_dir = project_dir(project_id)

    for upload in incoming:
        original = _safe_original_name(upload.filename or "document")
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

        row = ProjectDocument(
            project_id=project_id,
            kind="file",
            original_name=original,
            stored_name=stored,
            external_url=None,
            content_type=content_type[:120],
            size_bytes=size,
            uploaded_by_id=user.id if user else None,
        )
        db.add(row)
        saved.append(row)

    db.commit()
    for row in saved:
        db.refresh(row)
    return [document_to_out(row) for row in saved]


def save_url(
    db: Session,
    *,
    project_id: int,
    url: str,
    title: str | None,
    user: User | None,
) -> ProjectDocumentOut:
    _ensure_capacity(db, project_id, 1)
    normalized = _normalize_http_url(url)
    name = _title_from_url(normalized, title)

    row = ProjectDocument(
        project_id=project_id,
        kind="url",
        original_name=name,
        stored_name=None,
        external_url=normalized,
        content_type="text/uri-list",
        size_bytes=0,
        uploaded_by_id=user.id if user else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return document_to_out(row)


def resolve_file_path(doc: ProjectDocument) -> Path:
    if (doc.kind or "file") == "url" or not doc.stored_name:
        raise HTTPException(status_code=400, detail="Dokumen ini adalah tautan URL, bukan file unggahan")
    return resolve_under(project_dir(doc.project_id), doc.stored_name)


def delete_document(db: Session, doc: ProjectDocument) -> None:
    stored = doc.stored_name
    project_id = doc.project_id
    kind = doc.kind or "file"
    db.delete(doc)
    db.commit()
    if kind == "file" and stored:
        try:
            path = resolve_under(project_dir(project_id), stored)
            path.unlink()
        except (HTTPException, OSError):
            pass


def delete_project_files(project_id: int) -> None:
    folder = uploads_root() / "projects" / str(project_id)
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
