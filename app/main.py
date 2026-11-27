from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.db_migrate import ensure_schema
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import dashboard, projects, roles as roles_router
from app.routers import chat as chat_router
from app.routers import notifications as notifications_router
from app.routers import organization as organization_router
from app.routers import reports as reports_router
from app.routers import settings as settings_router, tasks, team, timeline as timeline_router
from app.routers import sprints as sprints_router
from app.routers import tickets as tickets_router
from app.routers import users as users_router
from app.seed import seed_database
from app.services.auth import ensure_default_admin, get_optional_user
from app.services.config_safety import validate_runtime_settings
from app.services.csrf_guard import CsrfOriginMiddleware
from app.services.email import ensure_smtp_profiles
from app.services.identity import get_or_create_app_identity
from app.services.roles import (
    ensure_default_roles,
    get_role_permissions,
    known_permission_keys,
    user_has_permission,
)
from app.services.security_headers import SecurityHeadersMiddleware
from app.services.security_settings import (
    DEFAULT_SESSION_TIMEOUT_MINUTES,
    get_or_create_security_settings,
    is_session_expired,
)
from app.templating import build_page_context

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PUBLIC_PATHS = {
    "/login",
    "/logout",
    "/setup-password",
    "/favicon.ico",
    "/api/auth/login",
    "/api/auth/captcha",
    "/api/auth/mfa/verify-login",
    "/api/auth/device/confirm",
    "/api/auth/device/resend",
    "/api/auth/setup-password",
    "/api/health",
}

FORBIDDEN_PAGE_HTML = (
    "<!DOCTYPE html><html lang='id'><head><meta charset='utf-8'/>"
    "<title>Akses ditolak</title></head><body style='font-family:system-ui;padding:2rem'>"
    "<h1>403 — Akses ditolak</h1>"
    "<p>Anda tidak memiliki izin untuk membuka halaman ini.</p>"
    "<p><a href='/'>Kembali ke beranda</a></p>"
    "</body></html>"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast on insecure production-like configuration (SEC-03).
    validate_runtime_settings(settings)
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        ensure_smtp_profiles(db)
        get_or_create_app_identity(db)
        get_or_create_security_settings(db)
        ensure_default_roles(db)
        ensure_default_admin(db)
        # KKS-PM-06: keep device confirmation aligned with production security posture.
        if (settings.app_env or "").strip().lower() in {"production", "prod"} or settings.cookie_secure:
            policy = get_or_create_security_settings(db)
            if not bool(getattr(policy, "device_detection_enabled", True)):
                policy.device_detection_enabled = True
                db.commit()
        if settings.seed_data:
            seed_database(db)
        # Derive project pipeline status from task progress on boot.
        from app.services.project_progress import reconcile_all_project_progress

        reconcile_all_project_progress(db)
    finally:
        db.close()
    yield


def _forwarded_proto(request: Request) -> str:
    raw = (
        request.headers.get("x-forwarded-proto")
        or request.url.scheme
        or "http"
    )
    return raw.split(",")[0].strip().lower()


class ForceHttpsMiddleware(BaseHTTPMiddleware):
    """When COOKIE_SECURE is on, bounce plain HTTP (e.g. http://IP:8891) to APP_URL HTTPS."""

    async def dispatch(self, request: Request, call_next):
        if not settings.cookie_secure:
            return await call_next(request)

        app_url = (settings.app_url or "").rstrip("/")
        if not app_url.lower().startswith("https://"):
            return await call_next(request)

        # Already HTTPS at the edge (WAF/nginx sets X-Forwarded-Proto).
        if _forwarded_proto(request) == "https":
            return await call_next(request)

        path = request.url.path
        if path == "/api/health":
            return await call_next(request)

        target = f"{app_url}{path}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(url=target, status_code=308)


def _looks_like_asset_path(path: str) -> bool:
    """Browser probes (favicon.ico, *.map, …) must not become login?next=…"""
    name = path.rsplit("/", 1)[-1]
    if not name or name.startswith("."):
        return False
    if "." not in name:
        return False
    # KKS-PM-02: never treat API schema as a public asset probe.
    lowered = name.lower()
    if lowered in {"openapi.json", "swagger.json"}:
        return False
    if lowered.endswith((".json", ".yaml", ".yml")) and "openapi" in lowered:
        return False
    # Allow extension-less app routes only; anything with a file suffix is an asset probe.
    return True


def _reject_inactive_or_missing_session(request: Request, path: str):
    request.session.clear()
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return RedirectResponse(url="/login?next=/", status_code=303)


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static/") or path in PUBLIC_PATHS:
            return await call_next(request)

        user_id = request.session.get("user_id")
        if not user_id:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            # Don't bounce favicon/asset probes through login — that sets next=/favicon.ico
            # and after login the user lands on FastAPI's JSON {"detail":"Not Found"}.
            if _looks_like_asset_path(path):
                return await call_next(request)
            next_url = path if path != "/login" else "/"
            return RedirectResponse(url=f"/login?next={next_url}", status_code=303)

        # Idle timeout: clock starts from last activity (falls back to login stamp).
        timeout = request.session.get("session_timeout_minutes") or DEFAULT_SESSION_TIMEOUT_MINUTES
        try:
            timeout_mins = int(timeout)
        except (TypeError, ValueError):
            timeout_mins = DEFAULT_SESSION_TIMEOUT_MINUTES
        activity_stamp = request.session.get("last_activity_at") or request.session.get(
            "authenticated_at"
        )
        if is_session_expired(activity_stamp, timeout_mins):
            request.session.clear()
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Sesi berakhir karena tidak ada aktivitas. Silakan login ulang.", "session_expired": True},
                    status_code=401,
                )
            return RedirectResponse(url="/login?next=/&session=expired", status_code=303)

        # SEC-09: reject deactivated accounts even if the session cookie remains.
        db = SessionLocal()
        try:
            from app.models.models import User

            try:
                uid = int(user_id)
            except (TypeError, ValueError):
                return _reject_inactive_or_missing_session(request, path)
            user = db.get(User, uid)
            if not user or not user.is_active:
                return _reject_inactive_or_missing_session(request, path)
        finally:
            db.close()

        return await call_next(request)


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """Long-cache fingerprinted static assets (?v=…) for lighter repeat visits."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            # Query-string cache busting is used across templates (js/css?v=N).
            response.headers.setdefault(
                "Cache-Control",
                "public, max-age=604800, immutable",
            )
        elif path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


_docs_enabled = (settings.app_env or "").strip().lower() in {"development", "dev", "local"}
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    # KKS-PM-02: hide OpenAPI surface in non-dev environments.
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
# Order matters: last added runs first.
# GZip → SecurityHeaders → StaticCache → ForceHttps → CSRF → Session → AuthGuard.
app.add_middleware(AuthGuardMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="pm_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=bool(settings.cookie_secure),
)
app.add_middleware(CsrfOriginMiddleware)
app.add_middleware(ForceHttpsMiddleware)
app.add_middleware(StaticCacheMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(tickets_router.router)
app.include_router(tasks.router)
app.include_router(sprints_router.router)
app.include_router(team.router)
app.include_router(settings_router.router)
app.include_router(users_router.router)
app.include_router(roles_router.router)
app.include_router(organization_router.router)
app.include_router(timeline_router.router)
app.include_router(audit_router.router)
app.include_router(notifications_router.router)
app.include_router(chat_router.router)
app.include_router(reports_router.router)


def _user_context(request: Request, db: Session) -> dict:
    user = get_optional_user(request, db)
    if not user:
        return {
            "name": "Guest",
            "avatar_url": "https://api.dicebear.com/7.x/initials/svg?seed=Guest&backgroundColor=1f5fd6",
            "role": "Guest",
            "email": "",
        }
    return {
        "id": user.id,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "email": user.email,
    }


def _allowed_permissions(db: Session, user) -> set[str]:
    """Resolve permission keys once per request (Admin bypass + role cache)."""
    if not user:
        return set()
    if user.role == "Admin":
        return known_permission_keys()
    return get_role_permissions(db, user.role)


def _page_context(
    request: Request,
    db: Session,
    *,
    active_page: str,
    page_title: str,
    page_subtitle: str,
    extra: dict | None = None,
) -> dict:
    user = get_optional_user(request, db)
    current = _user_context(request, db)
    perms = _allowed_permissions(db, user)
    return build_page_context(
        active_page=active_page,
        page_title=page_title,
        page_subtitle=page_subtitle,
        current_user=current,
        extra=extra,
        allowed_permissions=perms,
    )


def _require_page_permission(request: Request, db: Session, *permissions: str):
    """Backend gate for HTML pages (SEC-07). Hiding nav alone is not enough."""
    user = get_optional_user(request, db)
    if not user:
        next_url = request.url.path if request.url.path != "/login" else "/"
        return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
    if permissions and not any(user_has_permission(db, user, perm) for perm in permissions):
        return HTMLResponse(FORBIDDEN_PAGE_HTML, status_code=403)
    return None


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.connection()
    return {"status": "ok", "service": settings.app_name}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url="/static/favicon.svg", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    context = build_page_context(active_page="login", page_title="Login", allowed_permissions=set())
    return templates.TemplateResponse(request, "pages/login.html", context)


@app.get("/setup-password", response_class=HTMLResponse)
def setup_password_page(request: Request, db: Session = Depends(get_db)):
    """Public first-login / reset password page opened from welcome email."""
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    token = (request.query_params.get("token") or "").strip()
    context = build_page_context(
        active_page="login",
        page_title="Atur Password",
        allowed_permissions=set(),
        extra={"setup_token": token},
    )
    return templates.TemplateResponse(request, "pages/setup_password.html", context)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "dashboard.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="dashboard",
        page_title="Good day!",
        page_subtitle="Plan, track, and deliver projects with your team.",
    )
    return templates.TemplateResponse(request, "pages/dashboard.html", context)


@app.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "projects.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="projects",
        page_title="Projects",
        page_subtitle="Manage and monitor all projects in one place.",
        extra={"search_placeholder": "Search projects, tasks, people..."},
    )
    return templates.TemplateResponse(request, "pages/projects.html", context)


@app.get("/projects/new", response_class=HTMLResponse)
def project_new_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(
        request, db, "projects.create", "projects.manage", "projects.update"
    )
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="projects",
        page_title="New Project",
        page_subtitle="Lengkapi detail project pada halaman khusus.",
        extra={
            "form_mode": "create",
            "project_id": None,
        },
    )
    return templates.TemplateResponse(request, "pages/project_form.html", context)


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "projects.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="chat",
        page_title="Chat",
        page_subtitle="Daftar percakapan project yang dapat Anda akses.",
        extra={"search_placeholder": "Cari chat project…"},
    )
    return templates.TemplateResponse(request, "pages/chat.html", context)


@app.get("/tickets", response_class=HTMLResponse)
def tickets_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "tickets.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="tickets",
        page_title="Daftar Tiket & Evaluasi",
        page_subtitle="Kelola daftar tiket kendala/bug dan catatan evaluasi proyek secara terpusat.",
        extra={"search_placeholder": "Cari tiket..."},
    )
    return templates.TemplateResponse(request, "pages/tickets.html", context)


@app.get("/projects/{project_id}/edit", response_class=HTMLResponse)
def project_edit_page(
    project_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    denied = _require_page_permission(
        request, db, "projects.update", "projects.manage", "projects.create"
    )
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="projects",
        page_title="Edit Project",
        page_subtitle="Perbarui detail project pada halaman khusus.",
        extra={
            "form_mode": "edit",
            "project_id": project_id,
        },
    )
    return templates.TemplateResponse(request, "pages/project_form.html", context)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(
    project_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    denied = _require_page_permission(request, db, "projects.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="projects",
        page_title="Project Detail",
        page_subtitle="Ringkasan project, PIC, progress, dan task terkait.",
        extra={"project_id": project_id},
    )
    return templates.TemplateResponse(request, "pages/project_detail.html", context)


@app.get("/timeline", response_class=HTMLResponse)
def timeline_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "projects.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="timeline",
        page_title="Project Timeline",
        page_subtitle="Track project schedules and upcoming milestones.",
    )
    return templates.TemplateResponse(request, "pages/timeline.html", context)


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "projects.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="reports",
        page_title="Reports",
        page_subtitle="Export project dan task ke Excel sesuai cakupan role Anda.",
    )
    return templates.TemplateResponse(request, "pages/reports.html", context)


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "dashboard.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="calendar",
        page_title="Calendar",
        page_subtitle="Lihat deadline task per tanggal dan jadwal mendatang.",
    )
    return templates.TemplateResponse(request, "pages/calendar.html", context)


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "tasks.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="tasks",
        page_title="Tasks",
        page_subtitle="Track work across projects",
    )
    return templates.TemplateResponse(request, "pages/tasks.html", context)


@app.get("/sprints", response_class=HTMLResponse)
def sprints_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "sprints.view", "tasks.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="sprints",
        page_title="Sprints",
        page_subtitle="Prioritaskan modul dalam jangka waktu (SLA)",
    )
    return templates.TemplateResponse(request, "pages/sprints.html", context)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "users.view", "users.manage")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="users",
        page_title="User Management",
        page_subtitle="Kelola akun pengguna dan akses sistem.",
    )
    return templates.TemplateResponse(request, "pages/users.html", context)


@app.get("/organization", response_class=HTMLResponse)
def organization_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "organization.view", "organization.manage")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="organization",
        page_title="Organization Management",
        page_subtitle="Kelola Divisi, Bidang, dan struktur organisasi.",
    )
    return templates.TemplateResponse(request, "pages/organization.html", context)


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "audit.view")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="audit",
        page_title="Log Audit",
        page_subtitle="Pantau login dan pengiriman email password.",
    )
    return templates.TemplateResponse(request, "pages/audit.html", context)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db, "settings.manage")
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="settings",
        page_title="Settings",
        page_subtitle="Configure notifications and system preferences.",
    )
    return templates.TemplateResponse(request, "pages/settings.html", context)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    # Any authenticated active user may open their profile.
    denied = _require_page_permission(request, db)
    if denied:
        return denied
    context = _page_context(
        request,
        db,
        active_page="account",
        page_title="Profil",
        page_subtitle="Update nama dan foto profil.",
    )
    return templates.TemplateResponse(request, "pages/account.html", context)


@app.get("/account/security", response_class=HTMLResponse)
def account_security_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    denied = _require_page_permission(request, db)
    if denied:
        return denied
    user = get_optional_user(request, db)
    context = _page_context(
        request,
        db,
        active_page="account",
        page_title="Keamanan",
        page_subtitle="Password, MFA, dan perangkat tepercaya.",
    )
    context["mfa_enabled"] = bool(user.mfa_enabled) if user else False
    context["mfa_backup_codes_remaining"] = (
        len(user.mfa_backup_codes or []) if user and user.mfa_enabled else 0
    )
    return templates.TemplateResponse(request, "pages/account_security.html", context)
