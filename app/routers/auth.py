from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth import (
    authenticate_user,
    clear_session,
    get_optional_user,
    get_pending_device_user,
    get_pending_mfa_user,
    register_failed_login,
    register_successful_login,
    require_user,
    set_pending_device,
    set_pending_mfa,
    set_session_user,
)
from app.services.devices import (
    CONFIRM_TTL_MINUTES,
    confirm_device_by_token,
    count_trusted_devices,
    create_pending_device,
    find_trusted_device,
    get_device_cookie,
    list_trusted_devices,
    mask_email,
    revoke_device,
    set_device_cookie,
    summarize_device,
    touch_device,
    trust_device_now,
)
from app.services.audit import write_audit_log
from app.services.email import send_new_device_confirmation_email
from app.services.identity import get_identity_dict
from app.services.mfa import (
    backup_codes_remaining,
    build_otpauth_uri,
    consume_backup_code,
    format_secret_for_display,
    generate_backup_codes,
    generate_mfa_secret,
    hash_backup_codes,
    qr_svg_for_uri,
    verify_totp,
)
from app.services.security import create_captcha, default_avatar, hash_password, verify_captcha, verify_password

router = APIRouter(tags=["auth"])

AVATAR_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "avatars"
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=1, max_length=128)
    captcha_id: str = Field(min_length=10)
    captcha_answer: str = Field(min_length=1, max_length=16)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=24)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=4, max_length=24)


class MfaBackupRegenRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=4, max_length=24)


class MfaLoginVerifyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=24)


def _issuer_name(db: Session) -> str:
    identity = get_identity_dict(db)
    return (identity.get("brand_name") or identity.get("app_name") or "PulseDesk")[:32]


def _app_url(db: Session) -> str:
    from app.services.identity import resolve_public_app_url

    identity = get_identity_dict(db)
    return resolve_public_app_url(identity.get("app_url"))


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
    }


def _require_device_confirmation(request: Request, db: Session, user) -> JSONResponse:
    device, raw_device, raw_confirm = create_pending_device(db, user, request)
    confirm_url = f"{_app_url(db)}/api/auth/device/confirm?token={raw_confirm}"
    email_error = None
    try:
        send_new_device_confirmation_email(
            db,
            to_email=user.email,
            name=user.name,
            device_label=device.device_label,
            browser_name=device.browser_name,
            os_name=device.os_name,
            ip_address=device.ip_address,
            confirm_url=confirm_url,
            expires_minutes=CONFIRM_TTL_MINUTES,
        )
    except Exception as exc:  # noqa: BLE001 - surface mail failure to client
        email_error = str(exc)

    set_pending_device(request, user)
    payload = {
        "ok": True,
        "device_confirmation_required": True,
        "mfa_required": False,
        "email_masked": mask_email(user.email),
        "device_label": device.device_label,
        "expires_minutes": CONFIRM_TTL_MINUTES,
        "message": (
            "Perangkat tidak dikenal. Login dari perangkat baru memerlukan konfirmasi email. "
            f"Kami mengirim tautan ke {mask_email(user.email)}. "
            "Buka tautan di browser yang sama dengan yang sedang login."
        ),
    }
    if email_error:
        payload["email_sent"] = False
        payload["email_error"] = email_error
        payload["message"] = (
            "Perangkat tidak dikenal. Pengiriman email konfirmasi gagal. "
            "Periksa konfigurasi SMTP atau coba kirim ulang."
        )
    else:
        payload["email_sent"] = True
    # Cookie must be set on this JSONResponse (not a separate Response dep).
    resp = JSONResponse(payload)
    set_device_cookie(resp, raw_device, request)
    return resp


def _is_administrator(user, db: Session | None = None) -> bool:
    role = (getattr(user, "role", None) or "").strip().lower()
    if role in {"admin", "administrator"}:
        return True
    if db is not None:
        from app.services.roles import user_has_permission

        return user_has_permission(db, user, "users.manage")
    return False


def _audit_login_success(db: Session, request: Request, user, *, note: str = "") -> None:
    write_audit_log(
        db,
        action="login_success",
        success=True,
        actor=user,
        target=user,
        message=note or f"Login berhasil: {user.email}",
        request=request,
    )


def _finalize_login(request: Request, response: Response, db: Session, user) -> dict | JSONResponse:
    """After password (+ MFA), enforce trusted-device binding."""
    cookie = get_device_cookie(request)
    trusted = find_trusted_device(db, user, cookie)
    if trusted:
        touch_device(db, trusted, request)
        register_successful_login(db, user)
        set_session_user(request, user, db)
        set_device_cookie(response, cookie, request)
        _audit_login_success(db, request, user, note=f"Login berhasil (perangkat terpercaya): {user.email}")
        return {
            "ok": True,
            "mfa_required": False,
            "device_confirmation_required": False,
            "must_change_password": user.must_change_password,
            "user": _user_payload(user),
        }

    # Administrator: skip email device confirmation on new/cleared devices
    if _is_administrator(user, db):
        device, raw_token = trust_device_now(db, user, request)
        register_successful_login(db, user)
        set_session_user(request, user, db)
        set_device_cookie(response, raw_token, request)
        _audit_login_success(db, request, user, note=f"Login berhasil (admin bypass device): {user.email}")
        return {
            "ok": True,
            "mfa_required": False,
            "device_confirmation_required": False,
            "device_registered": True,
            "device_bypass": "admin",
            "device_label": device.device_label,
            "must_change_password": user.must_change_password,
            "user": _user_payload(user),
        }

    # First trusted device for this account: bootstrap without email friction
    if count_trusted_devices(db, user) == 0:
        device, raw_token = trust_device_now(db, user, request)
        register_successful_login(db, user)
        set_session_user(request, user, db)
        set_device_cookie(response, raw_token, request)
        _audit_login_success(db, request, user, note=f"Login berhasil (perangkat pertama): {user.email}")
        return {
            "ok": True,
            "mfa_required": False,
            "device_confirmation_required": False,
            "device_registered": True,
            "device_label": device.device_label,
            "must_change_password": user.must_change_password,
            "user": _user_payload(user),
        }

    return _require_device_confirmation(request, db, user)


@router.get("/api/auth/captcha")
def get_captcha() -> dict:
    token, _, svg = create_captcha()
    return {
        "captcha_id": token,
        "image_svg": svg,
        "expires_in": 300,
    }


@router.get("/api/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)) -> dict:
    from app.services.security_settings import get_or_create_security_settings, session_expires_at

    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    policy = get_or_create_security_settings(db)
    authenticated_at = request.session.get("authenticated_at")
    last_activity_at = request.session.get("last_activity_at") or authenticated_at
    expires = session_expires_at(last_activity_at, policy.session_timeout_minutes)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "must_change_password": user.must_change_password,
        "mfa_enabled": bool(user.mfa_enabled),
        "mfa_backup_codes_remaining": backup_codes_remaining(user.mfa_backup_codes),
        "session_timeout_minutes": int(policy.session_timeout_minutes),
        "authenticated_at": authenticated_at,
        "last_activity_at": last_activity_at,
        "session_expires_at": expires.isoformat() if expires else None,
        "session_mode": "idle",
    }


class HeartbeatRequest(BaseModel):
    extend_session: bool = False


@router.post("/api/auth/heartbeat")
def auth_heartbeat(
    request: Request,
    db: Session = Depends(get_db),
    payload: HeartbeatRequest | None = None,
) -> dict:
    """Presence ping; set extend_session=true to slide the idle timeout clock."""
    from datetime import datetime, timezone

    from app.services.security_settings import get_or_create_security_settings, session_expires_at

    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    extend_session = bool(payload.extend_session) if payload else False
    now = datetime.now(timezone.utc)
    user.last_active_at = now
    db.add(user)
    db.commit()

    if extend_session:
        request.session["last_activity_at"] = now.isoformat()

    policy = get_or_create_security_settings(db)
    activity_stamp = request.session.get("last_activity_at") or request.session.get(
        "authenticated_at"
    )
    expires = session_expires_at(activity_stamp, policy.session_timeout_minutes)
    return {
        "ok": True,
        "last_active_at": user.last_active_at.isoformat(),
        "last_activity_at": activity_stamp,
        "session_expires_at": expires.isoformat() if expires else None,
        "session_timeout_minutes": int(policy.session_timeout_minutes),
        "extended": extend_session,
    }


@router.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    if not verify_captcha(payload.captcha_id, payload.captcha_answer):
        write_audit_log(
            db,
            action="login_failed",
            success=False,
            target_email=payload.email.strip().lower(),
            message="Login gagal: captcha salah atau kedaluwarsa",
            request=request,
        )
        raise HTTPException(status_code=400, detail="Captcha salah atau sudah kedaluwarsa")

    try:
        user = authenticate_user(db, payload.email, payload.password, complete_login=False)
    except HTTPException as exc:
        write_audit_log(
            db,
            action="login_failed",
            success=False,
            target_email=payload.email.strip().lower(),
            message=f"Login gagal: {exc.detail}",
            request=request,
            meta={"status_code": exc.status_code},
        )
        raise

    if user.mfa_enabled and user.mfa_secret:
        set_pending_mfa(request, user)
        return {
            "ok": True,
            "mfa_required": True,
            "device_confirmation_required": False,
            "message": "Masukkan kode MFA dari aplikasi autentikator atau backup code.",
        }

    return _finalize_login(request, response, db, user)


@router.post("/api/auth/mfa/verify-login")
def verify_mfa_login(
    payload: MfaLoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = get_pending_mfa_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sesi MFA tidak valid. Login ulang.")

    code = payload.code.strip()
    ok = verify_totp(user.mfa_secret, code)
    if not ok:
        remaining = consume_backup_code(user.mfa_backup_codes, code)
        if remaining is None:
            register_failed_login(db, user)
            write_audit_log(
                db,
                action="login_failed",
                success=False,
                actor=user,
                target=user,
                message=f"Login gagal: kode MFA/backup salah ({user.email})",
                request=request,
            )
            raise HTTPException(status_code=400, detail="Kode MFA atau backup code salah")
        user.mfa_backup_codes = remaining
        db.commit()

    return _finalize_login(request, response, db, user)


@router.post("/api/auth/device/resend")
def resend_device_confirmation(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    user = get_pending_device_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sesi konfirmasi perangkat tidak valid. Login ulang.")

    device, raw_device, raw_confirm = create_pending_device(db, user, request)
    set_device_cookie(response, raw_device, request)
    confirm_url = f"{_app_url(db)}/api/auth/device/confirm?token={raw_confirm}"
    try:
        send_new_device_confirmation_email(
            db,
            to_email=user.email,
            name=user.name,
            device_label=device.device_label,
            browser_name=device.browser_name,
            os_name=device.os_name,
            ip_address=device.ip_address,
            confirm_url=confirm_url,
            expires_minutes=CONFIRM_TTL_MINUTES,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Gagal mengirim email: {exc}") from exc

    set_pending_device(request, user)
    return {
        "ok": True,
        "email_masked": mask_email(user.email),
        "message": f"Email konfirmasi dikirim ulang ke {mask_email(user.email)}.",
    }


@router.get("/api/auth/device/confirm")
def confirm_device(token: str, request: Request, db: Session = Depends(get_db)):
    device = confirm_device_by_token(
        db,
        (token or "").strip(),
        raw_device_cookie=get_device_cookie(request),
    )
    if not device:
        return RedirectResponse(url="/login?device=invalid", status_code=303)
    return RedirectResponse(url="/login?device=confirmed", status_code=303)


@router.get("/api/auth/devices")
def get_devices(request: Request, db: Session = Depends(get_db), user=Depends(require_user)) -> dict:
    cookie = get_device_cookie(request)
    current = find_trusted_device(db, user, cookie)
    devices = []
    for row in list_trusted_devices(db, user):
        item = summarize_device(row)
        item["is_current"] = bool(current and current.id == row.id)
        devices.append(item)
    return {"items": devices}


@router.delete("/api/auth/devices/{device_id}")
def delete_device(device_id: int, user=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    if not revoke_device(db, user, device_id):
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")
    return {"ok": True, "message": "Perangkat dihapus dari daftar tepercaya"}


@router.get("/api/auth/mfa/status")
def mfa_status(user=Depends(require_user)) -> dict:
    return {
        "enabled": bool(user.mfa_enabled),
        "backup_codes_remaining": backup_codes_remaining(user.mfa_backup_codes) if user.mfa_enabled else 0,
    }


@router.post("/api/auth/mfa/setup")
def mfa_setup(request: Request, db: Session = Depends(get_db), user=Depends(require_user)) -> dict:
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA sudah aktif")

    secret = generate_mfa_secret()
    request.session["mfa_setup_secret"] = secret
    issuer = _issuer_name(db)
    otpauth = build_otpauth_uri(secret, user.email, issuer=issuer)
    return {
        "ok": True,
        "secret": secret,
        "secret_display": format_secret_for_display(secret),
        "otpauth_url": otpauth,
        "qr_svg": qr_svg_for_uri(otpauth),
        "issuer": issuer,
        "account": user.email,
    }


@router.post("/api/auth/mfa/enable")
def mfa_enable(
    payload: MfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
) -> dict:
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA sudah aktif")

    secret = request.session.get("mfa_setup_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="Mulai setup MFA terlebih dahulu")

    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Kode MFA tidak valid. Coba lagi.")

    plain_codes = generate_backup_codes()
    user.mfa_secret = secret
    user.mfa_enabled = True
    user.mfa_backup_codes = hash_backup_codes(plain_codes)
    db.commit()
    request.session.pop("mfa_setup_secret", None)

    return {
        "ok": True,
        "message": "MFA berhasil diaktifkan",
        "backup_codes": plain_codes,
        "backup_codes_remaining": len(plain_codes),
    }


@router.post("/api/auth/mfa/disable")
def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
) -> dict:
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA belum aktif")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password salah")

    code = payload.code.strip()
    valid = verify_totp(user.mfa_secret, code)
    if not valid:
        remaining = consume_backup_code(user.mfa_backup_codes, code)
        if remaining is None:
            raise HTTPException(status_code=400, detail="Kode MFA atau backup code salah")
        user.mfa_backup_codes = remaining

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    db.commit()
    request.session.pop("mfa_setup_secret", None)
    return {"ok": True, "message": "MFA dinonaktifkan"}


@router.post("/api/auth/mfa/regenerate-backup-codes")
def mfa_regenerate_backup_codes(
    payload: MfaBackupRegenRequest,
    db: Session = Depends(get_db),
    user=Depends(require_user),
) -> dict:
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA belum aktif")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password salah")
    if not verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Kode MFA tidak valid")

    plain_codes = generate_backup_codes()
    user.mfa_backup_codes = hash_backup_codes(plain_codes)
    db.commit()
    return {
        "ok": True,
        "message": "Backup code baru dibuat. Simpan di tempat aman.",
        "backup_codes": plain_codes,
        "backup_codes_remaining": len(plain_codes),
    }


@router.post("/api/auth/logout")
def logout(request: Request) -> dict:
    clear_session(request)
    return {"ok": True}


@router.post("/api/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password saat ini salah")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password baru minimal 8 karakter")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    set_session_user(request, user, db)
    return {"ok": True, "message": "Password berhasil diubah"}


@router.patch("/api/auth/profile")
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
    name: str = Form(...),
    photo: UploadFile | None = File(default=None),
) -> dict:
    clean_name = (name or "").strip()
    if len(clean_name) < 2:
        raise HTTPException(status_code=400, detail="Nama minimal 2 karakter")
    if len(clean_name) > 120:
        raise HTTPException(status_code=400, detail="Nama terlalu panjang")

    user.name = clean_name

    if photo is not None and photo.filename:
        content_type = (photo.content_type or "").lower()
        ext = AVATAR_TYPES.get(content_type)
        if not ext:
            raise HTTPException(status_code=400, detail="Foto harus JPG, PNG, atau WEBP")

        data = await photo.read()
        if not data:
            raise HTTPException(status_code=400, detail="File foto kosong")
        if len(data) > AVATAR_MAX_BYTES:
            raise HTTPException(status_code=400, detail="Ukuran foto maksimal 2 MB")

        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATAR_DIR.glob(f"user_{user.id}.*"):
            try:
                old.unlink()
            except OSError:
                pass

        filename = f"user_{user.id}{ext}"
        target = AVATAR_DIR / filename
        target.write_bytes(data)
        user.avatar_url = f"/static/uploads/avatars/{filename}?v={int(target.stat().st_mtime)}"
    elif not user.avatar_url or "dicebear.com" in user.avatar_url:
        user.avatar_url = default_avatar(clean_name)

    db.commit()
    db.refresh(user)
    set_session_user(request, user, db)
    return {
        "ok": True,
        "message": "Profil berhasil diperbarui",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "avatar_url": user.avatar_url,
        },
    }


@router.get("/logout")
def logout_page(request: Request):
    clear_session(request)
    return RedirectResponse(url="/login", status_code=303)
