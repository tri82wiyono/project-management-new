from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import SecuritySetting

DEFAULT_MAX_FAILED_LOGINS = 6
DEFAULT_LOCKOUT_MINUTES = 30
DEFAULT_SESSION_TIMEOUT_MINUTES = 480  # 8 jam

# Avoid hitting DB on every authenticated request (AuthGuard hot path).
_CACHE: dict[str, object] = {"timeout": None, "expires_at": 0.0}


def invalidate_security_settings_cache() -> None:
    _CACHE["timeout"] = None
    _CACHE["expires_at"] = 0.0


def get_or_create_security_settings(db: Session) -> SecuritySetting:
    row = db.scalar(select(SecuritySetting).order_by(SecuritySetting.id.asc()).limit(1))
    if row:
        return row
    cfg = get_settings()
    row = SecuritySetting(
        max_failed_logins=int(getattr(cfg, "max_failed_logins", None) or DEFAULT_MAX_FAILED_LOGINS),
        lockout_minutes=int(getattr(cfg, "lockout_minutes", None) or DEFAULT_LOCKOUT_MINUTES),
        session_timeout_minutes=max(
            5,
            int((getattr(cfg, "session_max_age", 0) or 0) / 60) or DEFAULT_SESSION_TIMEOUT_MINUTES,
        ),
        device_detection_enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_security_settings_cache()
    return row


def get_cached_session_timeout_minutes(db: Session | None = None) -> int:
    """Fast path for login stamping / rare lookups. Cached ~60s."""
    now = time.monotonic()
    cached = _CACHE.get("timeout")
    expires_at = float(_CACHE.get("expires_at") or 0.0)
    if cached is not None and now < expires_at:
        return int(cached)

    if db is None:
        from app.database import SessionLocal

        session = SessionLocal()
        try:
            row = get_or_create_security_settings(session)
            value = max(5, int(row.session_timeout_minutes or DEFAULT_SESSION_TIMEOUT_MINUTES))
        finally:
            session.close()
    else:
        row = get_or_create_security_settings(db)
        value = max(5, int(row.session_timeout_minutes or DEFAULT_SESSION_TIMEOUT_MINUTES))

    _CACHE["timeout"] = value
    _CACHE["expires_at"] = now + 60.0
    return value


def is_device_detection_enabled(db: Session) -> bool:
    """Admin toggle: when False, login skips new-device/browser email confirmation."""
    row = get_or_create_security_settings(db)
    return bool(getattr(row, "device_detection_enabled", True))


def security_to_dict(row: SecuritySetting) -> dict:
    return {
        "id": row.id,
        "max_failed_logins": int(row.max_failed_logins),
        "lockout_minutes": int(row.lockout_minutes),
        "session_timeout_minutes": int(row.session_timeout_minutes),
        "device_detection_enabled": bool(getattr(row, "device_detection_enabled", True)),
        "updated_at": row.updated_at,
    }


def parse_session_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def session_expires_at(authenticated_at: str | None, timeout_minutes: int) -> datetime | None:
    started = parse_session_timestamp(authenticated_at)
    if not started:
        return None
    minutes = max(5, int(timeout_minutes or DEFAULT_SESSION_TIMEOUT_MINUTES))
    return started + timedelta(minutes=minutes)


def is_session_expired(authenticated_at: str | None, timeout_minutes: int) -> bool:
    expires = session_expires_at(authenticated_at, timeout_minutes)
    if not expires:
        # Legacy session without timestamp — force re-login once
        return True
    return datetime.now(timezone.utc) >= expires
