"""Browser security headers for defense in depth.

Applied to every response. CSP is intentionally pragmatic: the app still uses a
few inline boot scripts (sidebar collapse / nav order) plus Google Fonts and
Chart.js CDN on the dashboard.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

def _build_csp(*, https_mode: bool) -> str:
    # Keep in sync with external assets used by templates.
    parts = [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'self'",
        "form-action 'self'",
        "img-src 'self' data: blob: https://api.dicebear.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        # Quill snow CSS (project form) + Chart.js assets are served from jsDelivr.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "connect-src 'self'",
        "worker-src 'self' blob:",
    ]
    # Only force HTTPS upgrades when the deployment is HTTPS-backed.
    if https_mode:
        parts.append("upgrade-insecure-requests")
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        path = request.url.path or ""
        settings = get_settings()
        https_mode = bool(getattr(settings, "cookie_secure", False))

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Content-Security-Policy", _build_csp(https_mode=https_mode))

        if https_mode:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        content_type = (headers.get("content-type") or "").lower()
        if path.startswith("/api/"):
            headers.setdefault("Cache-Control", "no-store")
        elif "text/html" in content_type:
            # HTML must not linger in shared caches.
            headers["Cache-Control"] = "no-store"

        return response
