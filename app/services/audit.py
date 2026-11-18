from __future__ import annotations

from fastapi import Request
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.models import AuditLog, User
from app.services.devices import client_ip

ACTION_LABELS = {
    "login_success": "Login berhasil",
    "login_failed": "Login gagal",
    "password_email_sent": "Email reset password terkirim",
    "password_email_failed": "Email reset password gagal",
    "welcome_email_sent": "Email welcome/password terkirim",
    "welcome_email_failed": "Email welcome/password gagal",
}


def write_audit_log(
    db: Session,
    *,
    action: str,
    success: bool,
    message: str = "",
    actor: User | None = None,
    target: User | None = None,
    target_email: str | None = None,
    target_name: str | None = None,
    request: Request | None = None,
    meta: dict | None = None,
) -> AuditLog:
    ua = ""
    ip = None
    if request is not None:
        ua = (request.headers.get("user-agent") or "")[:500]
        ip = client_ip(request)

    row = AuditLog(
        action=action,
        success=bool(success),
        actor_user_id=actor.id if actor else None,
        actor_name=(actor.name if actor else "")[:120],
        actor_email=(actor.email if actor else "")[:180],
        target_user_id=target.id if target else None,
        target_name=((target.name if target else None) or target_name or "")[:120],
        target_email=((target.email if target else None) or target_email or "")[:180].lower(),
        message=(message or "")[:500],
        ip_address=ip,
        user_agent=ua,
        meta=meta,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def audit_to_dict(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "action_label": ACTION_LABELS.get(row.action, row.action),
        "success": bool(row.success),
        "actor_user_id": row.actor_user_id,
        "actor_name": row.actor_name or "",
        "actor_email": row.actor_email or "",
        "target_user_id": row.target_user_id,
        "target_name": row.target_name or "",
        "target_email": row.target_email or "",
        "message": row.message or "",
        "ip_address": row.ip_address,
        "user_agent": row.user_agent or "",
        "meta": row.meta or {},
        "created_at": row.created_at,
    }


def list_audit_logs(
    db: Session,
    *,
    q: str | None = None,
    action: str | None = None,
    category: str | None = None,
    success: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    page = max(1, page)
    page_size = min(100, max(10, page_size))

    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)

    filters = []
    if action:
        filters.append(AuditLog.action == action.strip())
    if category == "login":
        filters.append(AuditLog.action.in_(("login_success", "login_failed")))
    elif category == "email":
        filters.append(
            AuditLog.action.in_(
                (
                    "password_email_sent",
                    "password_email_failed",
                    "welcome_email_sent",
                    "welcome_email_failed",
                )
            )
        )
    if success is not None:
        filters.append(AuditLog.success.is_(bool(success)))
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                AuditLog.target_email.ilike(like),
                AuditLog.target_name.ilike(like),
                AuditLog.actor_email.ilike(like),
                AuditLog.actor_name.ilike(like),
                AuditLog.message.ilike(like),
                AuditLog.ip_address.ilike(like),
            )
        )

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        stmt.order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [audit_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size) if total else 1,
    }


def audit_summary(db: Session) -> dict:
    def _count(*actions: str, success: bool | None = None) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(actions))
        if success is not None:
            stmt = stmt.where(AuditLog.success.is_(success))
        return int(db.scalar(stmt) or 0)

    return {
        "login_success": _count("login_success", success=True),
        "login_failed": _count("login_failed", success=False),
        "password_email_sent": _count(
            "password_email_sent", "welcome_email_sent", success=True
        ),
        "password_email_failed": _count(
            "password_email_failed", "welcome_email_failed", success=False
        ),
    }
