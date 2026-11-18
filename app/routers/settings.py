from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.email import (
    get_or_create_smtp_settings,
    send_email,
    send_reset_password_email,
    send_welcome_user_email,
    smtp_to_public_dict,
)
from app.services.email_templates import reset_password_email, welcome_user_email
from app.services.identity import get_or_create_app_identity, identity_to_dict

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AppIdentityUpdate(BaseModel):
    app_name: str = Field(min_length=1, max_length=160)
    brand_name: str = Field(min_length=1, max_length=80)
    brand_mark: str = Field(min_length=1, max_length=8)
    brand_tagline: str = Field(default="Project OS", max_length=120)
    workspace_label: str = Field(default="Workspace", max_length=80)
    workspace_name: str = Field(default="Fintech Delivery", max_length=120)
    organization_name: str = Field(default="Bank Sumut", max_length=160)
    app_url: str = Field(min_length=1, max_length=255)
    footer_note: str = Field(default="Built with FastAPI · PostgreSQL", max_length=255)
    support_email: str = Field(default="", max_length=180)


class SmtpSettingsUpdate(BaseModel):
    enabled: bool = True
    host: str = Field(min_length=1, max_length=180)
    port: int = Field(default=587, ge=1, le=65535)
    encryption: str = Field(default="starttls")
    username: str = Field(default="", max_length=180)
    password: str | None = None  # None = keep existing; "" = clear
    from_email: str = Field(min_length=1, max_length=180)
    from_name: str = Field(default="Project Management System", max_length=120)


class SmtpTestRequest(BaseModel):
    to_email: str = Field(min_length=3, max_length=180)
    template: str = Field(default="welcome")  # welcome | reset_password | plain
    name: str = Field(default="Pengguna Uji")


@router.get("/identity")
def get_identity_settings(db: Session = Depends(get_db)) -> dict:
    row = get_or_create_app_identity(db)
    return identity_to_dict(row)


@router.put("/identity")
def update_identity_settings(payload: AppIdentityUpdate, db: Session = Depends(get_db)) -> dict:
    row = get_or_create_app_identity(db)
    row.app_name = payload.app_name.strip()
    row.brand_name = payload.brand_name.strip()
    row.brand_mark = payload.brand_mark.strip()[:8]
    row.brand_tagline = payload.brand_tagline.strip() or "Project OS"
    row.workspace_label = payload.workspace_label.strip() or "Workspace"
    row.workspace_name = payload.workspace_name.strip() or "Fintech Delivery"
    row.organization_name = payload.organization_name.strip() or "Bank Sumut"
    row.app_url = payload.app_url.strip().rstrip("/")
    row.footer_note = payload.footer_note.strip() or "Built with FastAPI · PostgreSQL"
    row.support_email = payload.support_email.strip()
    db.commit()
    db.refresh(row)
    return identity_to_dict(row)


@router.get("/smtp")
def get_smtp_settings(db: Session = Depends(get_db)) -> dict:
    row = get_or_create_smtp_settings(db)
    return smtp_to_public_dict(row)


@router.put("/smtp")
def update_smtp_settings(payload: SmtpSettingsUpdate, db: Session = Depends(get_db)) -> dict:
    encryption = payload.encryption.lower().strip()
    if encryption not in {"none", "starttls", "ssl"}:
        raise HTTPException(status_code=400, detail="encryption must be none, starttls, or ssl")

    row = get_or_create_smtp_settings(db)
    row.enabled = payload.enabled
    row.host = payload.host.strip()
    row.port = payload.port
    row.encryption = encryption
    row.username = payload.username.strip()
    row.from_email = payload.from_email.strip()
    row.from_name = payload.from_name.strip() or "Project Management System"

    # password: None means keep; empty string clears (as requested by user)
    if payload.password is not None:
        row.password = payload.password

    db.commit()
    db.refresh(row)
    return smtp_to_public_dict(row)


@router.get("/email-templates/{template_key}", response_class=HTMLResponse)
def preview_email_template(template_key: str) -> HTMLResponse:
    if template_key == "welcome":
        content = welcome_user_email(
            name="Budi Santoso",
            email="budi.santoso@banksumut.co.id",
            temporary_password="Temp@12345",
        )
    elif template_key == "reset_password":
        content = reset_password_email(
            name="Budi Santoso",
            email="budi.santoso@banksumut.co.id",
            reset_token="preview-token-demo",
        )
    else:
        raise HTTPException(status_code=404, detail="Unknown template")
    return HTMLResponse(content.html)


@router.post("/smtp/test")
def test_smtp_settings(payload: SmtpTestRequest, db: Session = Depends(get_db)) -> dict:
    to_email = payload.to_email.strip()
    name = payload.name.strip() or "Pengguna Uji"
    template = payload.template.lower().strip()

    try:
        if template == "welcome":
            send_welcome_user_email(
                db,
                to_email=to_email,
                name=name,
                temporary_password="Temp@12345",
            )
            label = "Welcome (create user)"
        elif template == "reset_password":
            send_reset_password_email(
                db,
                to_email=to_email,
                name=name,
                reset_token="test-reset-token",
            )
            label = "Reset password"
        elif template == "plain":
            send_email(
                db,
                to_email=to_email,
                subject="PulseDesk SMTP Test",
                body=(
                    "Ini adalah email uji konfigurasi SMTP dari Project Management System.\n\n"
                    "Jika Anda menerima pesan ini, pengaturan SMTP sudah berfungsi."
                ),
            )
            label = "Plain test"
        else:
            raise HTTPException(status_code=400, detail="template must be welcome, reset_password, or plain")

        return {"ok": True, "message": f"{label} email sent to {to_email}"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
