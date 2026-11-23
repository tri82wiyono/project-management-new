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
    """Return (token, answer, svg). Answer is only for image rendering."""
    settings = get_settings()
    length = 5
    answer = "".join(secrets.choice(_CAPTCHA_ALPHABET) for _ in range(length))
    nonce = secrets.token_hex(16)
    exp = int(time.time()) + settings.captcha_ttl_seconds
    token = _sign({"n": nonce, "e": exp, "h": _answer_digest(nonce, answer)})
    svg = render_captcha_svg(answer)
    return token, answer, svg


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


def render_captcha_svg(answer: str) -> str:
    width, height = 180, 56
    # Random-ish but deterministic-looking noise from secrets
    lines = []
    for _ in range(5):
        x1, y1 = secrets.randbelow(width), secrets.randbelow(height)
        x2, y2 = secrets.randbelow(width), secrets.randbelow(height)
        color = secrets.choice(["#c5cce0", "#b7c0d9", "#d7dde9", "#aab4cf"])
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.4"/>'
        )

    chars = []
    start_x = 18
    for i, ch in enumerate(answer):
        x = start_x + i * 30 + secrets.randbelow(4)
        y = 34 + secrets.randbelow(8) - 3
        rot = secrets.randbelow(25) - 12
        fill = secrets.choice(["#322a62", "#453a82", "#1a2332", "#3b4b75"])
        chars.append(
            f'<text x="{x}" y="{y}" fill="{fill}" font-size="26" font-family="Arial, Helvetica, sans-serif" '
            f'font-weight="700" transform="rotate({rot} {x} {y})">{ch}</text>'
        )

    dots = []
    for _ in range(28):
        cx, cy = secrets.randbelow(width), secrets.randbelow(height)
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="1.2" fill="#9aa6c1" opacity="0.55"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Captcha">'
        f'<rect width="100%" height="100%" rx="10" fill="#eef1f7"/>'
        f'{"".join(lines)}{"".join(dots)}{"".join(chars)}'
        f"</svg>"
    )


def default_avatar(name: str) -> str:
    seed = _b64encode(name.encode("utf-8"))[:12]
    return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=453a82,4f7cff"
