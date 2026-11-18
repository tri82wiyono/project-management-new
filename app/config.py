from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Project Management System"
    app_url: str = "http://localhost:8891"
    database_url: str = "postgresql+psycopg2://pm_user:pm_secret_2025@localhost:5438/project_mgmt"
    seed_data: bool = True
    secret_key: str = "pm-dev-secret-change-me-banksumut-2025"
    session_max_age: int = 60 * 60 * 8  # 8 hours
    captcha_ttl_seconds: int = 300
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    default_admin_email: str = "admin@banksumut.co.id"
    default_admin_password: str = "Admin@12345"
    default_admin_name: str = "System Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
