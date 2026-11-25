"""Narrow CSRF mitigation for cookie-authenticated mutating API requests.

Session cookies use SameSite=Lax (see main.py). This guard adds an Origin/Referer
host check for browser fetch/XHR mutations as defense in depth.

No per-form CSRF tokens — compatible with existing SPA JSON APIs.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw or raw.lower() == "null":
        return None
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    return host or None


def allowed_csrf_hosts() -> set[str]:
    settings = get_settings()
    hosts: set[str] = {"localhost", "127.0.0.1", "testserver"}
    app_host = _host_from_url(getattr(settings, "app_url", None))
    if app_host:
        hosts.add(app_host)
    return hosts


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)
        path = request.url.path or ""
        if not path.startswith("/api/"):
            return await call_next(request)
        # Establishing authentication: captcha + credentials remain required.
        if (
            path.startswith("/api/auth/login")
            or path.startswith("/api/auth/captcha")
            or path.startswith("/api/auth/setup-password")
        ):
            return await call_next(request)

        origin = _host_from_url(request.headers.get("origin"))
        referer = _host_from_url(request.headers.get("referer"))
        check = origin or referer
        # Non-browser / TestClient often omit Origin+Referer; SameSite still applies
        # for real browsers. Only reject when a foreign host is explicitly present.
        if check is None:
            return await call_next(request)
        if check not in allowed_csrf_hosts():
            return JSONResponse(
                status_code=403,
                content={"detail": "Origin tidak diizinkan untuk permintaan perubahan status"},
            )
        return await call_next(request)
