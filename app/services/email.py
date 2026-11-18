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


DEFAULT_SMTP = {
    "enabled": True,
    "host": "mail.banksumut.co.id",
    "port": 587,
    "encryption": "starttls",
    "username": "notification@banksumut.co.id",
    "password": "",
    "from_email": "notification@banksumut.co.id",
    "from_name": "Project Management System",
}


def get_or_create_smtp_settings(db: Session) -> SmtpSetting:
    row = db.scalar(select(SmtpSetting).order_by(SmtpSetting.id.asc()).limit(1))
    if row:
        return row
    row = SmtpSetting(**DEFAULT_SMTP)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def smtp_to_public_dict(row: SmtpSetting) -> dict:
    return {
        "id": row.id,
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

    return {"ok": True, "to": to_email}


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
