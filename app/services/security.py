from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
import time
from threading import Lock

import bcrypt

from app.config import get_settings

# Ambiguous characters removed for captcha readability
_CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_USED_NONCES: dict[str, float] = {}
_USED_LOCK = Lock()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def generate_temp_password(length: int = 12) -> str:
    # Alphanumeric only — avoids email-client / HTML copy issues with !@#$%&
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(max(12, length)))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


SETUP_PASSWORD_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def password_fingerprint(password_hash: str | None) -> str:
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def create_setup_password_token(
    *,
    user_id: int,
    email: str,
    password_hash: str | None,
    ttl_seconds: int = SETUP_PASSWORD_TTL_SECONDS,
    project_id: int | None = None,
    purpose: str = "setup_password",
) -> str:
    """Signed link token for first-login / reset / project-invite setup page."""
    exp = int(time.time()) + max(300, int(ttl_seconds))
    purpose_key = (purpose or "setup_password").strip() or "setup_password"
    if purpose_key not in {"setup_password", "project_invite"}:
        purpose_key = "setup_password"
    data = {
        "p": purpose_key,
        "uid": int(user_id),
        "em": (email or "").strip().lower(),
        "fp": password_fingerprint(password_hash),
        "e": exp,
    }
    if project_id:
        data["pid"] = int(project_id)
    return _sign(data)


def verify_setup_password_token(token: str) -> dict | None:
    payload = _unsign(token or "")
    if not payload:
        return None
    purpose = str(payload.get("p") or "")
    if purpose not in {"setup_password", "project_invite"}:
        return None
    now = time.time()
    if int(payload.get("e", 0) or 0) < now:
        return None
    try:
        uid = int(payload.get("uid"))
    except (TypeError, ValueError):
        return None
    email = str(payload.get("em") or "").strip().lower()
    fp = str(payload.get("fp") or "")
    if not uid or not email or not fp:
        return None
    project_id = None
    if payload.get("pid") is not None:
        try:
            project_id = int(payload.get("pid"))
        except (TypeError, ValueError):
            project_id = None
    return {
        "user_id": uid,
        "email": email,
        "fingerprint": fp,
        "expires_at": int(payload.get("e") or 0),
        "purpose": purpose,
        "project_id": project_id,
    }


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign(payload: dict) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _unsign(token: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    secret = get_settings().secret_key.encode("utf-8")
    expected = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(_b64decode(body))
    except (json.JSONDecodeError, ValueError):
        return None


def _answer_digest(nonce: str, answer: str) -> str:
    secret = get_settings().secret_key
    normalized = "".join(answer.upper().split())
    return hashlib.sha256(f"{nonce}:{normalized}:{secret}".encode("utf-8")).hexdigest()


def _purge_used_nonces(now: float) -> None:
    expired = [key for key, exp in _USED_NONCES.items() if exp <= now]
    for key in expired:
        _USED_NONCES.pop(key, None)


def create_captcha() -> tuple[str, str, str]:
    """Return (token, answer, png_data_url). Answer never leaves the server as text."""
    settings = get_settings()
    length = 5
    answer = "".join(secrets.choice(_CAPTCHA_ALPHABET) for _ in range(length))
    nonce = secrets.token_hex(16)
    exp = int(time.time()) + settings.captcha_ttl_seconds
    token = _sign({"n": nonce, "e": exp, "h": _answer_digest(nonce, answer)})
    png_data_url = render_captcha_png_data_url(answer)
    return token, answer, png_data_url


def verify_captcha(token: str, answer: str) -> bool:
    payload = _unsign(token or "")
    if not payload:
        return False
    now = time.time()
    if int(payload.get("e", 0)) < now:
        return False
    nonce = str(payload.get("n", ""))
    expected = str(payload.get("h", ""))
    if not nonce or not expected:
        return False
    with _USED_LOCK:
        _purge_used_nonces(now)
        if nonce in _USED_NONCES:
            return False
        if not hmac.compare_digest(expected, _answer_digest(nonce, answer or "")):
            return False
        _USED_NONCES[nonce] = float(payload["e"])
    return True


def render_captcha_png_data_url(answer: str) -> str:
    """Raster captcha — glyphs are pixels only (no extractable SVG text)."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    width, height = 200, 64
    img = Image.new("RGB", (width, height), "#eef1f7")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        except OSError:
            font = ImageFont.load_default()

    for _ in range(5):
        x1, y1 = secrets.randbelow(width), secrets.randbelow(height)
        x2, y2 = secrets.randbelow(width), secrets.randbelow(height)
        color = secrets.choice(["#c5cce0", "#b7c0d9", "#d7dde9", "#aab4cf"])
        draw.line((x1, y1, x2, y2), fill=color, width=2)

    for _ in range(36):
        cx, cy = secrets.randbelow(width), secrets.randbelow(height)
        draw.ellipse((cx, cy, cx + 2, cy + 2), fill="#9aa6c1")

    # Keep glyphs fully inside the canvas (rotation expands the box).
    slot = width // max(len(answer), 1)
    for i, ch in enumerate(answer):
        fill = secrets.choice(["#322a62", "#453a82", "#1a2332", "#3b4b75"])
        glyph = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glyph)
        gdraw.text((10, 6), ch, font=font, fill=fill)
        angle = secrets.randbelow(17) - 8
        rotated = glyph.rotate(angle, expand=True, resample=Image.BICUBIC)
        rw, rh = rotated.size
        x = max(2, min(width - rw - 2, i * slot + (slot - rw) // 2))
        y = max(2, (height - rh) // 2)
        img.paste(rotated, (x, y), rotated)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def render_captcha_svg(answer: str) -> str:
    """Deprecated — kept for compatibility; prefer render_captcha_png_data_url."""
    return render_captcha_png_data_url(answer)


def default_avatar(name: str) -> str:
    # Use the real name as seed so DiceBear initials match the person (e.g. "Tri Wiyono" → TW).
    # Avoid base64 seeds — those produce unrelated letters (e.g. VU).
    from urllib.parse import quote

    seed = quote((name or "User").strip() or "User", safe="")
    return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=453a82,4f7cff"
