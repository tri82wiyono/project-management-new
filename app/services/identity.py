from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import AppIdentity


def _is_local_url(url: str) -> bool:
    lower = (url or "").strip().lower()
    return (
        not lower
        or "localhost" in lower
        or "127.0.0.1" in lower
        or lower.startswith("http://0.0.0.0")
    )


def resolve_public_app_url(*candidates: str | None) -> str:
    """Pick a public app URL; skip localhost so email CTA tidak mengarah ke laptop."""
    cfg = get_settings()
    ordered = [*(candidates or ()), cfg.app_url, "https://pm.banksumut.co.id"]
    non_local: list[str] = []
    for raw in ordered:
        url = (raw or "").strip().rstrip("/")
        if not url:
            continue
        if not _is_local_url(url):
            return url
        non_local.append(url)
    return non_local[0] if non_local else "https://pm.banksumut.co.id"


def _defaults() -> dict:
    cfg = get_settings()
    return {
        "app_name": cfg.app_name,
        "brand_name": "PulseDesk",
        "brand_mark": "PM",
        "brand_tagline": "Project OS",
        "workspace_label": "Workspace",
        "workspace_name": "Fintech Delivery",
        "organization_name": "Bank Sumut",
        "app_url": resolve_public_app_url(cfg.app_url),
        "footer_note": "Built with FastAPI · PostgreSQL",
        "support_email": "notification@banksumut.co.id",
    }


def get_or_create_app_identity(db: Session) -> AppIdentity:
    row = db.scalar(select(AppIdentity).order_by(AppIdentity.id.asc()).limit(1))
    if row:
        return row
    row = AppIdentity(**_defaults())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def identity_to_dict(row: AppIdentity) -> dict:
    return {
        "id": row.id,
        "app_name": row.app_name,
        "brand_name": row.brand_name,
        "brand_mark": row.brand_mark,
        "brand_tagline": row.brand_tagline,
        "workspace_label": row.workspace_label,
        "workspace_name": row.workspace_name,
        "organization_name": row.organization_name,
        "app_url": resolve_public_app_url(row.app_url),
        "footer_note": row.footer_note,
        "support_email": row.support_email,
        "updated_at": row.updated_at,
    }


def get_identity_dict(db: Session | None = None) -> dict:
    """Return identity as dict; opens a short session when db is not provided."""
    if db is not None:
        return identity_to_dict(get_or_create_app_identity(db))

    from app.database import SessionLocal

    session = SessionLocal()
    try:
        return identity_to_dict(get_or_create_app_identity(session))
    except Exception:
        return _defaults()
    finally:
        session.close()
