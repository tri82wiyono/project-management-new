from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.db_migrate import ensure_schema
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import dashboard, projects, roles as roles_router
from app.routers import settings as settings_router, tasks, team, timeline as timeline_router
from app.routers import tickets as tickets_router
from app.routers import users as users_router
from app.seed import seed_database
from app.services.auth import ensure_default_admin, get_optional_user
from app.services.email import ensure_smtp_profiles
from app.services.identity import get_or_create_app_identity
from app.services.roles import ensure_default_roles
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
    "/favicon.ico",
    "/api/auth/login",
    "/api/auth/captcha",
    "/api/auth/mfa/verify-login",
    "/api/auth/device/confirm",
    "/api/auth/device/resend",
    "/api/health",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        ensure_smtp_profiles(db)
        get_or_create_app_identity(db)
        get_or_create_security_settings(db)
        ensure_default_roles(db)
        ensure_default_admin(db)
        if settings.seed_data:
            seed_database(db)
        # Keep Release aligned with task progress (demote Release if < 100%).
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
    # Allow extension-less app routes only; anything with a file suffix is an asset probe.
    return True


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

        # Enforce session timeout from values stamped at login (no DB per request).
        timeout = request.session.get("session_timeout_minutes") or DEFAULT_SESSION_TIMEOUT_MINUTES
        try:
            timeout_mins = int(timeout)
        except (TypeError, ValueError):
            timeout_mins = DEFAULT_SESSION_TIMEOUT_MINUTES
        if is_session_expired(request.session.get("authenticated_at"), timeout_mins):
            request.session.clear()
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Sesi berakhir. Silakan login ulang.", "session_expired": True},
                    status_code=401,
                )
            return RedirectResponse(url="/login?next=/&session=expired", status_code=303)

        return await call_next(request)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
# Order matters: last added runs first.
# ForceHttps → Session → AuthGuard (outermost first).
app.add_middleware(AuthGuardMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="pm_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=bool(settings.cookie_secure),
)
app.add_middleware(ForceHttpsMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(tickets_router.router)
app.include_router(tasks.router)
app.include_router(team.router)
app.include_router(settings_router.router)
app.include_router(users_router.router)
app.include_router(roles_router.router)
app.include_router(timeline_router.router)
app.include_router(audit_router.router)


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
    context = build_page_context(active_page="login", page_title="Login")
    return templates.TemplateResponse(request, "pages/login.html", context)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="dashboard",
        page_title="Good day!",
        page_subtitle="Plan, track, and deliver projects with your team.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/dashboard.html", context)


@app.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="projects",
        page_title="Projects",
        page_subtitle="Manage and monitor all projects in one place.",
        current_user=_user_context(request, db),
        extra={"search_placeholder": "Search projects, tasks, people..."},
    )
    return templates.TemplateResponse(request, "pages/projects.html", context)


@app.get("/tickets", response_class=HTMLResponse)
def tickets_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="tickets",
        page_title="Daftar Tiket & Evaluasi",
        page_subtitle="Kelola daftar tiket kendala/bug dan catatan evaluasi proyek secara terpusat.",
        current_user=_user_context(request, db),
        extra={"search_placeholder": "Cari tiket..."},
    )
    return templates.TemplateResponse(request, "pages/tickets.html", context)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(
    project_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    context = build_page_context(
        active_page="projects",
        page_title="Project Detail",
        page_subtitle="Ringkasan project, PIC, progress, dan task terkait.",
        current_user=_user_context(request, db),
        extra={"project_id": project_id},
    )
    return templates.TemplateResponse(request, "pages/project_detail.html", context)


@app.get("/timeline", response_class=HTMLResponse)
def timeline_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="timeline",
        page_title="Project Timeline",
        page_subtitle="Track project schedules and upcoming milestones.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/timeline.html", context)


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="calendar",
        page_title="Calendar",
        page_subtitle="Lihat deadline task per tanggal dan jadwal mendatang.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/calendar.html", context)


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="tasks",
        page_title="Tasks",
        page_subtitle="Track work across projects",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/tasks.html", context)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="users",
        page_title="User Management",
        page_subtitle="Kelola akun pengguna dan akses sistem.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/users.html", context)


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="audit",
        page_title="Log Audit",
        page_subtitle="Pantau login dan pengiriman email password.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/audit.html", context)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="settings",
        page_title="Settings",
        page_subtitle="Configure notifications and system preferences.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/settings.html", context)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = build_page_context(
        active_page="account",
        page_title="Profil",
        page_subtitle="Update nama dan foto profil.",
        current_user=_user_context(request, db),
    )
    return templates.TemplateResponse(request, "pages/account.html", context)


@app.get("/account/security", response_class=HTMLResponse)
def account_security_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    user = get_optional_user(request, db)
    context = build_page_context(
        active_page="account",
        page_title="Keamanan",
        page_subtitle="Password, MFA, dan perangkat tepercaya.",
        current_user=_user_context(request, db),
    )
    context["mfa_enabled"] = bool(user.mfa_enabled) if user else False
    context["mfa_backup_codes_remaining"] = (
        len(user.mfa_backup_codes or []) if user and user.mfa_enabled else 0
    )
    return templates.TemplateResponse(request, "pages/account_security.html", context)
