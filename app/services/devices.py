from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import User, UserDevice

DEVICE_COOKIE = "pm_device_token"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
CONFIRM_TTL_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


def parse_user_agent(ua: str) -> tuple[str, str, str]:
    raw = (ua or "").strip()
    browser = "Browser"
    os_name = "Unknown OS"

    if "Edg/" in raw:
        browser = "Microsoft Edge"
    elif "Chrome/" in raw and "Chromium" not in raw:
        browser = "Chrome"
    elif "Firefox/" in raw:
        browser = "Firefox"
    elif "Safari/" in raw and "Chrome/" not in raw:
        browser = "Safari"
    elif "Opera" in raw or "OPR/" in raw:
        browser = "Opera"

    if "Windows" in raw:
        os_name = "Windows"
    elif "Android" in raw:
        os_name = "Android"
    elif "iPhone" in raw or "iPad" in raw:
        os_name = "iOS"
    elif "Mac OS X" in raw or "Macintosh" in raw:
        os_name = "macOS"
    elif "Linux" in raw:
        os_name = "Linux"

    label = f"{browser} di {os_name}"
    return browser, os_name, label


def get_device_cookie(request: Request) -> str | None:
    value = request.cookies.get(DEVICE_COOKIE)
    return value.strip() if value else None


def _request_is_https(request: Request | None = None) -> bool:
    from app.config import get_settings

    if request is not None:
        proto = (
            request.headers.get("x-forwarded-proto")
            or request.url.scheme
            or ""
        )
        proto = proto.split(",")[0].strip().lower()
        if proto in {"http", "https"}:
            return proto == "https"
    # Fall back to env intent (HTTPS production URL).
    return bool(get_settings().cookie_secure) or str(
        get_settings().app_url or ""
    ).lower().startswith("https://")


def set_device_cookie(
    response: Response,
    raw_token: str,
    request: Request | None = None,
) -> None:
    response.set_cookie(
        key=DEVICE_COOKIE,
        value=raw_token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        # Never mark Secure on plain HTTP — mobile IP access would drop the cookie.
        secure=_request_is_https(request),
        path="/",
    )


def clear_device_cookie(response: Response) -> None:
    response.delete_cookie(DEVICE_COOKIE, path="/")


def find_trusted_device(db: Session, user: User, raw_token: str | None) -> UserDevice | None:
    if not raw_token:
        return None
    token_hash = hash_token(raw_token)
    return db.scalar(
        select(UserDevice).where(
            UserDevice.user_id == user.id,
            UserDevice.device_token_hash == token_hash,
            UserDevice.is_trusted.is_(True),
        )
    )


def count_trusted_devices(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(UserDevice)
            .where(UserDevice.user_id == user.id, UserDevice.is_trusted.is_(True))
        )
        or 0
    )


def touch_device(db: Session, device: UserDevice, request: Request) -> None:
    device.last_seen_at = _now()
    device.ip_address = client_ip(request)
    ua = (request.headers.get("user-agent") or "")[:500]
    if ua:
        browser, os_name, label = parse_user_agent(ua)
        device.user_agent = ua
        device.browser_name = browser
        device.os_name = os_name
        device.device_label = label
    db.commit()


def create_pending_device(db: Session, user: User, request: Request) -> tuple[UserDevice, str, str]:
    """Create pending device. Returns (device, raw_device_token, raw_confirm_token)."""
    ua = (request.headers.get("user-agent") or "")[:500]
    browser, os_name, label = parse_user_agent(ua)
    raw_device = new_token()
    raw_confirm = new_token()

    # Invalidate older pending confirmations for this user
    pending = db.scalars(
        select(UserDevice).where(
            UserDevice.user_id == user.id,
            UserDevice.is_trusted.is_(False),
        )
    ).all()
    for row in pending:
        row.confirm_token_hash = None
        row.confirm_expires_at = None

    device = UserDevice(
        user_id=user.id,
        device_token_hash=hash_token(raw_device),
        device_label=label,
        user_agent=ua,
        browser_name=browser,
        os_name=os_name,
        ip_address=client_ip(request),
        is_trusted=False,
        confirm_token_hash=hash_token(raw_confirm),
        confirm_expires_at=_now() + timedelta(minutes=CONFIRM_TTL_MINUTES),
        last_seen_at=_now(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, raw_device, raw_confirm


def trust_device_now(db: Session, user: User, request: Request) -> tuple[UserDevice, str]:
    """Bootstrap / trust current browser immediately. Returns (device, raw_token)."""
    ua = (request.headers.get("user-agent") or "")[:500]
    browser, os_name, label = parse_user_agent(ua)
    raw_device = new_token()
    device = UserDevice(
        user_id=user.id,
        device_token_hash=hash_token(raw_device),
        device_label=label,
        user_agent=ua,
        browser_name=browser,
        os_name=os_name,
        ip_address=client_ip(request),
        is_trusted=True,
        confirm_token_hash=None,
        confirm_expires_at=None,
        last_seen_at=_now(),
        trusted_at=_now(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, raw_device


def confirm_device_by_token(
    db: Session,
    raw_confirm: str,
    raw_device_cookie: str | None = None,
) -> UserDevice | None:
    """Mark pending device as trusted only when email token matches this browser cookie."""
    if not raw_confirm or not raw_device_cookie:
        return None
    token_hash = hash_token(raw_confirm)
    device = db.scalar(
        select(UserDevice).where(UserDevice.confirm_token_hash == token_hash).limit(1)
    )
    if not device:
        return None
    if not device.confirm_expires_at or device.confirm_expires_at < _now():
        return None
    # Bind confirmation to the browser that started the login (prevents email-link takeover).
    if device.device_token_hash != hash_token(raw_device_cookie):
        return None

    device.is_trusted = True
    device.trusted_at = _now()
    device.last_seen_at = _now()
    device.confirm_token_hash = None
    device.confirm_expires_at = None
    db.commit()
    db.refresh(device)
    return device


def list_trusted_devices(db: Session, user: User) -> list[UserDevice]:
    return list(
        db.scalars(
            select(UserDevice)
            .where(UserDevice.user_id == user.id, UserDevice.is_trusted.is_(True))
            .order_by(UserDevice.last_seen_at.desc().nullslast(), UserDevice.id.desc())
        ).all()
    )


def revoke_device(db: Session, user: User, device_id: int) -> bool:
    device = db.get(UserDevice, device_id)
    if not device or device.user_id != user.id:
        return False
    db.delete(device)
    db.commit()
    return True


def mask_email(email: str) -> str:
    value = (email or "").strip()
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def summarize_device(device: UserDevice) -> dict:
    return {
        "id": device.id,
        "label": device.device_label,
        "browser": device.browser_name,
        "os": device.os_name,
        "ip_address": device.ip_address,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "trusted_at": device.trusted_at.isoformat() if device.trusted_at else None,
        "is_current": False,
    }
