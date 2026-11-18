from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Project Management System"
    app_url: str = "http://localhost:8891"
    database_url: str = "postgresql+psycopg2://pm_user:pm_secret_2025@localhost:5438/project_mgmt"
    seed_data: bool = True
    secret_key: str = "pm-dev-secret-change-me-banksumut-2025"
    # Cookie ceiling; real session length comes from SecuritySetting.session_timeout_minutes
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days cookie max
    captcha_ttl_seconds: int = 300
    max_failed_logins: int = 6
    lockout_minutes: int = 30
    default_admin_email: str = "admin@banksumut.co.id"
    default_admin_password: str = "Admin@12345"
    default_admin_name: str = "System Admin"
    # true = Secure cookies + redirect HTTP→APP_URL HTTPS (production)
    # false = allow plain HTTP (local/dev only)
    cookie_secure: bool = False
    upload_dir: str = "/app/app/static/uploads"
    max_project_documents: int = 3
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB per file


@lru_cache
def get_settings() -> Settings:
    return Settings()
