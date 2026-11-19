from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

# Extension → (canonical MIME, magic validators). A file must match at least one validator.
_MIME_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _is_zip(data: bytes) -> bool:
    return len(data) >= 4 and data[:2] == b"PK"


def _is_ole(data: bytes) -> bool:
    return len(data) >= 8 and data[:4] == b"\xd0\xcf\x11\xe0"


def _is_mostly_text(data: bytes) -> bool:
    sample = data[:4096]
    if not sample:
        return False
    # Allow UTF-8 BOM / common text; reject NUL-heavy binaries.
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


_MAGIC_CHECKS: dict[str, list] = {
    ".pdf": [lambda d: d.startswith(b"%PDF")],
    ".png": [lambda d: d.startswith(b"\x89PNG\r\n\x1a\n")],
    ".jpg": [lambda d: d.startswith(b"\xff\xd8\xff")],
    ".jpeg": [lambda d: d.startswith(b"\xff\xd8\xff")],
    ".gif": [lambda d: d.startswith(b"GIF87a") or d.startswith(b"GIF89a")],
    ".txt": [_is_mostly_text],
    ".csv": [_is_mostly_text],
    ".zip": [_is_zip],
    ".docx": [_is_zip],
    ".xlsx": [_is_zip],
    ".pptx": [_is_zip],
    ".doc": [_is_ole],
    ".xls": [_is_ole],
    ".ppt": [_is_ole],
}


def canonical_content_type(ext: str) -> str:
    return _MIME_BY_EXT.get((ext or "").lower(), "application/octet-stream")


def validate_file_content(*, data: bytes, ext: str, original_name: str) -> str:
    """Reject mismatched magic bytes; return canonical Content-Type (ignore client)."""
    key = (ext or "").lower()
    checks = _MAGIC_CHECKS.get(key)
    if not checks:
        raise HTTPException(
            status_code=400,
            detail=f"Tipe file tidak diizinkan: {original_name}",
        )
    if not any(check(data) for check in checks):
        raise HTTPException(
            status_code=400,
            detail=f"Isi file tidak cocok dengan ekstensi: {original_name}",
        )
    return canonical_content_type(key)


def safe_stored_name(stored_name: str | None) -> str:
    """Reject path traversal / nested names in DB-stored filenames."""
    raw = (stored_name or "").strip()
    if not raw or raw != Path(raw).name or "/" in raw or "\\" in raw or ".." in raw:
        raise HTTPException(status_code=400, detail="Nama file storage tidak valid")
    return raw


def resolve_under(base_dir: Path, stored_name: str) -> Path:
    """Resolve a file path and ensure it stays inside base_dir."""
    name = safe_stored_name(stored_name)
    base = base_dir.resolve()
    path = (base / name).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path file tidak valid") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File tidak ditemukan di storage")
    return path
