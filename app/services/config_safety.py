"""Production configuration fail-safes (Phase 0 / SEC-03).

Does not print secret values. Development keeps documented insecure defaults;
production-like modes refuse known-weak placeholders.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

# Exact default / placeholder values shipped in source or .env.example guidance.
# Comparison is exact (or normalized) — values are never logged.
_INSECURE_SECRET_KEYS = frozenset(
    {
        "pm-dev-secret-change-me-banksumut-2025",
        "changeme",
        "change-me",
        "secret",
        "secret_key",
        "dev-secret",
        "ganti_dengan_string_acak_panjang_minimal_32_karakter",
        "change_me_to_a_long_random_secret_at_least_32_chars",
    }
)

_INSECURE_ADMIN_PASSWORDS = frozenset(
    {
        "Admin@12345",
        "admin",
        "password",
        "Password1",
        "ganti_password_admin",
        "change_me_strong_admin_password",
    }
)

_MIN_SECRET_LEN = 32
_MIN_ADMIN_PASSWORD_LEN = 12


def is_production_like(settings: Settings) -> bool:
    """
    Production-like when APP_ENV is production/prod, or COOKIE_SECURE is enabled.

    APP_ENV=development|dev|local|test forces non-production even if cookie_secure
    is true (useful for local HTTPS experiments).
    """
    env = (getattr(settings, "app_env", None) or "").strip().lower()
    if env in {"development", "dev", "local", "test"}:
        return False
    if env in {"production", "prod"}:
        return True
    # HTTPS cookie mode is the historical production signal in this codebase.
    return bool(getattr(settings, "cookie_secure", False))


def _is_insecure_secret(secret: str) -> bool:
    value = (secret or "").strip()
    if len(value) < _MIN_SECRET_LEN:
        return True
    lowered = value.lower()
    if value in _INSECURE_SECRET_KEYS or lowered in _INSECURE_SECRET_KEYS:
        return True
    if "change-me" in lowered or "change_me" in lowered:
        return True
    if lowered.startswith("ganti_"):
        return True
    return False


def _is_insecure_admin_password(password: str) -> bool:
    value = password or ""
    if len(value) < _MIN_ADMIN_PASSWORD_LEN:
        return True
    if value in _INSECURE_ADMIN_PASSWORDS:
        return True
    lowered = value.lower()
    if lowered.startswith("ganti_") or lowered.startswith("change_me") or "change-me" in lowered:
        return True
    return False


def validate_runtime_settings(settings: Settings) -> None:
    """
    Raise RuntimeError if production-like settings use insecure placeholders.

    Error messages must not include secret or password material.
    """
    if not is_production_like(settings):
        return

    if _is_insecure_secret(settings.secret_key):
        raise RuntimeError(
            "Insecure SECRET_KEY for production-like configuration. "
            "Set SECRET_KEY to a strong random value (minimum 32 characters) "
            "or set APP_ENV=development for local use."
        )

    if _is_insecure_admin_password(settings.default_admin_password):
        raise RuntimeError(
            "Insecure DEFAULT_ADMIN_PASSWORD for production-like configuration. "
            "Set a strong DEFAULT_ADMIN_PASSWORD (minimum 12 characters) "
            "or set APP_ENV=development for local use."
        )
