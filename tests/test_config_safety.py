"""Test Group B — production configuration safety (SEC-03)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.config_safety import (
    is_production_like,
    validate_runtime_settings,
)


def _settings(**overrides):
    base = {
        "app_env": "development",
        "cookie_secure": False,
        "secret_key": "pm-dev-secret-change-me-banksumut-2025",
        "default_admin_password": "Admin@12345",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class ConfigSafetyTests(unittest.TestCase):
    def test_development_allows_defaults(self):
        settings = _settings(app_env="development", cookie_secure=False)
        self.assertFalse(is_production_like(settings))
        validate_runtime_settings(settings)  # must not raise

    def test_app_env_development_overrides_cookie_secure(self):
        settings = _settings(app_env="development", cookie_secure=True)
        self.assertFalse(is_production_like(settings))
        validate_runtime_settings(settings)

    def test_production_rejects_default_secret(self):
        settings = _settings(
            app_env="production",
            secret_key="pm-dev-secret-change-me-banksumut-2025",
            default_admin_password="Str0ng-Admin-Pass!",
        )
        with self.assertRaises(RuntimeError) as ctx:
            validate_runtime_settings(settings)
        message = str(ctx.exception)
        self.assertIn("SECRET_KEY", message)
        self.assertNotIn("pm-dev-secret", message)

    def test_production_rejects_short_secret(self):
        settings = _settings(
            app_env="production",
            secret_key="short-secret-value",
            default_admin_password="Str0ng-Admin-Pass!",
        )
        with self.assertRaises(RuntimeError) as ctx:
            validate_runtime_settings(settings)
        self.assertNotIn("short-secret-value", str(ctx.exception))

    def test_production_rejects_insecure_admin_password(self):
        settings = _settings(
            app_env="production",
            secret_key="a" * 40,
            default_admin_password="Admin@12345",
        )
        with self.assertRaises(RuntimeError) as ctx:
            validate_runtime_settings(settings)
        message = str(ctx.exception)
        self.assertIn("DEFAULT_ADMIN_PASSWORD", message)
        self.assertNotIn("Admin@12345", message)

    def test_cookie_secure_enables_production_like_validation(self):
        settings = _settings(
            app_env="",  # ambiguous env
            cookie_secure=True,
            secret_key="pm-dev-secret-change-me-banksumut-2025",
            default_admin_password="Str0ng-Admin-Pass!",
        )
        self.assertTrue(is_production_like(settings))
        with self.assertRaises(RuntimeError):
            validate_runtime_settings(settings)

    def test_valid_production_configuration(self):
        settings = _settings(
            app_env="production",
            cookie_secure=True,
            secret_key="x" * 40,
            default_admin_password="Str0ng-Admin-Pass!",
        )
        validate_runtime_settings(settings)


if __name__ == "__main__":
    unittest.main()
