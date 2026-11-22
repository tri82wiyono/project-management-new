"""Additional SEC-07 checks for HTML page permission helper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from starlette.responses import HTMLResponse, RedirectResponse

from app.main import _require_page_permission


class PagePermissionGateTests(unittest.TestCase):
    def test_unauthenticated_redirects_to_login(self):
        request = MagicMock()
        request.url.path = "/settings"
        db = MagicMock()
        with patch("app.main.get_optional_user", return_value=None):
            response = _require_page_permission(request, db, "settings.manage")
        self.assertIsInstance(response, RedirectResponse)
        self.assertIn("/login", response.headers.get("location", ""))

    def test_member_denied_settings(self):
        request = MagicMock()
        request.url.path = "/settings"
        user = MagicMock()
        db = MagicMock()
        with patch("app.main.get_optional_user", return_value=user):
            with patch("app.main.user_has_permission", return_value=False):
                response = _require_page_permission(request, db, "settings.manage")
        self.assertIsInstance(response, HTMLResponse)
        self.assertEqual(response.status_code, 403)

    def test_admin_allowed_settings(self):
        request = MagicMock()
        request.url.path = "/settings"
        user = MagicMock()
        db = MagicMock()
        with patch("app.main.get_optional_user", return_value=user):
            with patch("app.main.user_has_permission", return_value=True):
                response = _require_page_permission(request, db, "settings.manage")
        self.assertIsNone(response)

    def test_users_page_allows_either_view_or_manage(self):
        request = MagicMock()
        request.url.path = "/users"
        user = MagicMock()
        db = MagicMock()

        def _has(_db, _user, perm):
            return perm == "users.view"

        with patch("app.main.get_optional_user", return_value=user):
            with patch("app.main.user_has_permission", side_effect=_has):
                response = _require_page_permission(request, db, "users.view", "users.manage")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
