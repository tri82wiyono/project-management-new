from __future__ import annotations

import io
import secrets
import string

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage

from app.services.security import hash_password, verify_password

BACKUP_CODE_COUNT = 8
BACKUP_CODE_LENGTH = 10


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def build_otpauth_uri(secret: str, email: str, issuer: str = "PulseDesk") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def qr_svg_for_uri(otpauth_uri: str) -> str:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode("utf-8")


def verify_totp(secret: str | None, code: str, valid_window: int = 1) -> bool:
    if not secret:
        return False
    clean = "".join((code or "").split())
    if not clean.isdigit() or len(clean) != 6:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(clean, valid_window=valid_window))


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    alphabet = string.ascii_uppercase + string.digits
    codes: list[str] = []
    while len(codes) < count:
        raw = "".join(secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        formatted = f"{raw[:5]}-{raw[5:]}"
        if formatted not in codes:
            codes.append(formatted)
    return codes


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [hash_password(code.replace("-", "").upper()) for code in codes]


def normalize_backup_code(code: str) -> str:
    return "".join((code or "").upper().split()).replace("-", "")


def consume_backup_code(stored_hashes: list | None, code: str) -> list[str] | None:
    """Return updated hash list if code matched, else None."""
    if not stored_hashes:
        return None
    normalized = normalize_backup_code(code)
    if len(normalized) < 8:
        return None
    remaining: list[str] = []
    matched = False
    for item in stored_hashes:
        if not matched and verify_password(normalized, item):
            matched = True
            continue
        remaining.append(item)
    return remaining if matched else None


def backup_codes_remaining(stored_hashes: list | None) -> int:
    return len(stored_hashes or [])


def format_secret_for_display(secret: str) -> str:
    clean = (secret or "").replace(" ", "")
    return " ".join(clean[i : i + 4] for i in range(0, len(clean), 4))
