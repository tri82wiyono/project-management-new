from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import SmtpSetting
from app.services.email_templates import (
    EmailContent,
    new_device_confirmation_email,
    reset_password_email,
    welcome_user_email,
)

SMTP_PROVIDERS = ("zimbra", "gmail")

DEFAULT_SMTP_PROFILES: dict[str, dict] = {
    "zimbra": {
        "provider": "zimbra",
        "label": "Zimbra",
        "is_active": True,
        "enabled": True,
        "host": "mail.banksumut.co.id",
        "port": 587,
        "encryption": "starttls",
        "username": "notification@banksumut.co.id",
        "password": "",
        "from_email": "notification@banksumut.co.id",
        "from_name": "Project Management System",
    },
    "gmail": {
        "provider": "gmail",
        "label": "Gmail",
        "is_active": False,
        "enabled": True,
        "host": "smtp.gmail.com",
        "port": 587,
        "encryption": "starttls",
        "username": "tri82.wiyono@gmail.com",
        "password": "",
        "from_email": "tri82.wiyono@gmail.com",
        "from_name": "PulseDesk",
    },
}


def ensure_smtp_profiles(db: Session) -> list[SmtpSetting]:
    """Pastikan profil Zimbra + Gmail ada; row lama tidak ditimpa isinya."""
    rows = list(db.scalars(select(SmtpSetting).order_by(SmtpSetting.id.asc())).all())
    by_provider: dict[str, SmtpSetting] = {}
    dirty = False

    for row in rows:
        provider = (row.provider or "").strip().lower()
        if not provider:
            host = (row.host or "").lower()
            provider = "gmail" if "gmail" in host else "zimbra"
            row.provider = provider
            row.label = row.label or ("Gmail" if provider == "gmail" else "Zimbra")
            dirty = True
        if provider in by_provider:
            # Duplikat provider — biarkan yang pertama, nonaktifkan sisanya
            if row.is_active:
                row.is_active = False
                dirty = True
            continue
        by_provider[provider] = row

    for key, defaults in DEFAULT_SMTP_PROFILES.items():
        if key in by_provider:
            continue
        row = SmtpSetting(**defaults)
        # Jika sudah ada profil lain yang aktif, jangan aktifkan default baru
        if by_provider and any(r.is_active for r in by_provider.values()):
            row.is_active = False
        db.add(row)
        by_provider[key] = row
        dirty = True

    if by_provider and not any(r.is_active for r in by_provider.values()):
        preferred = by_provider.get("zimbra") or next(iter(by_provider.values()))
        preferred.is_active = True
        dirty = True

    if dirty:
        db.commit()
        for row in by_provider.values():
            db.refresh(row)

    return [by_provider[k] for k in SMTP_PROVIDERS if k in by_provider]


def get_or_create_smtp_settings(db: Session) -> SmtpSetting:
    """Profil SMTP yang sedang aktif (dipakai pengiriman email)."""
    ensure_smtp_profiles(db)
    active = db.scalar(select(SmtpSetting).where(SmtpSetting.is_active.is_(True)).limit(1))
    if active:
        return active
    profiles = ensure_smtp_profiles(db)
    return profiles[0]


def get_smtp_profile(db: Session, provider: str) -> SmtpSetting | None:
    key = (provider or "").strip().lower()
    ensure_smtp_profiles(db)
    return db.scalar(select(SmtpSetting).where(SmtpSetting.provider == key).limit(1))


def activate_smtp_provider(db: Session, provider: str) -> SmtpSetting:
    key = (provider or "").strip().lower()
    if key not in SMTP_PROVIDERS:
        raise ValueError("provider must be zimbra or gmail")
    ensure_smtp_profiles(db)
    rows = list(db.scalars(select(SmtpSetting)).all())
    target = None
    for row in rows:
        if row.provider == key:
            row.is_active = True
            target = row
        else:
            row.is_active = False
    if not target:
        raise ValueError(f"SMTP profile '{key}' not found")
    db.commit()
    db.refresh(target)
    return target


def smtp_to_public_dict(row: SmtpSetting) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "label": row.label,
        "is_active": bool(row.is_active),
        "enabled": row.enabled,
        "host": row.host,
        "port": row.port,
        "encryption": row.encryption,
        "username": row.username,
        "password_set": bool(row.password),
        "from_email": row.from_email,
        "from_name": row.from_name,
        "updated_at": row.updated_at,
    }


def smtp_profiles_payload(db: Session) -> dict:
    profiles = ensure_smtp_profiles(db)
    active = next((p for p in profiles if p.is_active), profiles[0] if profiles else None)
    return {
        "active_provider": active.provider if active else None,
        "profiles": [smtp_to_public_dict(p) for p in profiles],
    }


def send_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict:
    cfg = get_or_create_smtp_settings(db)
    if not cfg.enabled:
        raise RuntimeError("SMTP notifications are disabled")
    if not cfg.host or not cfg.from_email:
        raise RuntimeError("SMTP host/from email is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{cfg.from_name} <{cfg.from_email}>"
    message["To"] = to_email
    message["MIME-Version"] = "1.0"
    # Prefer HTML for clients that support it; plain text remains as fallback.
    if html_body:
        message.set_content(body)
        message.add_alternative(html_body, subtype="html")
    else:
        message.set_content(body)

    encryption = (cfg.encryption or "starttls").lower()
    timeout = 20

    def _maybe_login(server: smtplib.SMTP) -> None:
        # Password may be intentionally blank (Zimbra relay / internal auth).
        if cfg.username and cfg.password:
            server.login(cfg.username, cfg.password)

    if encryption == "ssl":
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=timeout) as server:
            _maybe_login(server)
            server.send_message(message)
    else:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=timeout) as server:
            server.ehlo()
            if encryption == "starttls":
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
            _maybe_login(server)
            server.send_message(message)

    return {"ok": True, "to": to_email, "provider": cfg.provider}


def send_templated_email(db: Session, *, to_email: str, content: EmailContent) -> dict:
    return send_email(
        db,
        to_email=to_email,
        subject=content.subject,
        body=content.text,
        html_body=content.html,
    )


def send_welcome_user_email(
    db: Session,
    *,
    to_email: str,
    name: str,
    temporary_password: str,
    login_url: str | None = None,
) -> dict:
    content = welcome_user_email(
        name=name,
        email=to_email,
        temporary_password=temporary_password,
        login_url=login_url,
    )
    return send_templated_email(db, to_email=to_email, content=content)


def send_reset_password_email(
    db: Session,
    *,
    to_email: str,
    name: str,
    reset_url: str | None = None,
    reset_token: str | None = None,
    expires_minutes: int = 60,
) -> dict:
    content = reset_password_email(
        name=name,
        email=to_email,
        reset_url=reset_url,
        reset_token=reset_token,
        expires_minutes=expires_minutes,
    )
    return send_templated_email(db, to_email=to_email, content=content)


def send_new_device_confirmation_email(
    db: Session,
    *,
    to_email: str,
    name: str,
    device_label: str,
    browser_name: str,
    os_name: str,
    ip_address: str | None,
    confirm_url: str,
    expires_minutes: int = 30,
) -> dict:
    content = new_device_confirmation_email(
        name=name,
        email=to_email,
        device_label=device_label,
        browser_name=browser_name,
        os_name=os_name,
        ip_address=ip_address,
        confirm_url=confirm_url,
        expires_minutes=expires_minutes,
    )
    return send_templated_email(db, to_email=to_email, content=content)
