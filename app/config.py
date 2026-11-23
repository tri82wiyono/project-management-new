from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Project Management System"
    app_url: str = "http://localhost:8891"
    # development | production — production-like also inferred from COOKIE_SECURE=true
    app_env: str = "development"
    database_url: str = "postgresql+psycopg2://pm_user:pm_secret_2025@localhost:5438/project_mgmt"
    seed_data: bool = True
    # Dev default only — rejected by config_safety in production-like mode
    secret_key: str = "pm-dev-secret-change-me-banksumut-2025"
    # Cookie ceiling; real session length comes from SecuritySetting.session_timeout_minutes
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days cookie max
    captcha_ttl_seconds: int = 300
    max_failed_logins: int = 6
    lockout_minutes: int = 30
    default_admin_email: str = "admin@banksumut.co.id"
    # Dev default only — rejected by config_safety in production-like mode
    default_admin_password: str = "Admin@12345"
    default_admin_name: str = "System Admin"
    # true = Secure cookies + redirect HTTP→APP_URL HTTPS (production)
    # false = allow plain HTTP (local/dev only)
    cookie_secure: bool = False
    # Private storage (outside StaticFiles). Serve only via authenticated download routes.
    upload_dir: str = "/app/data/uploads"
    max_project_documents: int = 3
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB per file
    # Phase 4 — organizational Project/Task scope. Default off for safe legacy rollout.
    # Enable only after classifying legacy projects. Does not auto-disable in production.
    org_scope_enforcement: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
