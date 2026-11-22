"""Test Group C — inactive user session enforcement helpers (SEC-09)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.main import _reject_inactive_or_missing_session
from app.services.auth import get_optional_user


class InactiveSessionHelperTests(unittest.TestCase):
    def test_reject_api_clears_and_returns_401(self):
        request = MagicMock(spec=Request)
        request.session = {"user_id": 7}
        response = _reject_inactive_or_missing_session(request, "/api/projects")
        self.assertEqual(request.session, {})
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 401)

    def test_reject_html_redirects_to_login(self):
        request = MagicMock(spec=Request)
        request.session = {"user_id": 7}
        response = _reject_inactive_or_missing_session(request, "/projects")
        self.assertEqual(request.session, {})
        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.headers.get("location", ""))


class GetOptionalUserInactiveTests(unittest.TestCase):
    def test_inactive_user_clears_session(self):
        request = MagicMock(spec=Request)
        request.session = {"user_id": 3}
        inactive = MagicMock()
        inactive.is_active = False
        db = MagicMock()
        db.get.return_value = inactive

        user = get_optional_user(request, db)
        self.assertIsNone(user)
        self.assertEqual(request.session, {})

    def test_active_user_retained(self):
        request = MagicMock(spec=Request)
        request.session = {"user_id": 3}
        active = MagicMock()
        active.is_active = True
        db = MagicMock()
        db.get.return_value = active

        user = get_optional_user(request, db)
        self.assertIs(user, active)
        self.assertEqual(request.session.get("user_id"), 3)


class AuthGuardInactiveIntegrationTests(unittest.TestCase):
    """Exercise AuthGuardMiddleware dispatch with mocked SessionLocal."""

    def test_inactive_user_blocked_on_api(self):
        from app.main import AuthGuardMiddleware

        inactive = MagicMock()
        inactive.is_active = False

        request = MagicMock(spec=Request)
        request.url.path = "/api/projects"
        request.session = {
            "user_id": 5,
            "authenticated_at": "2099-01-01T00:00:00+00:00",
            "session_timeout_minutes": 480,
        }

        call_next = MagicMock()

        db = MagicMock()
        db.get.return_value = inactive
        db_cm = MagicMock()
        db_cm.close = MagicMock()

        with patch("app.main.SessionLocal", return_value=db):
            with patch("app.main.is_session_expired", return_value=False):
                middleware = AuthGuardMiddleware(app=MagicMock())
                import asyncio

                response = asyncio.run(middleware.dispatch(request, call_next))

        self.assertEqual(response.status_code, 401)
        call_next.assert_not_called()
        self.assertEqual(request.session, {})

    def test_active_user_passes(self):
        from app.main import AuthGuardMiddleware

        active = MagicMock()
        active.is_active = True

        request = MagicMock(spec=Request)
        request.url.path = "/api/projects"
        request.session = {
            "user_id": 5,
            "authenticated_at": "2099-01-01T00:00:00+00:00",
            "session_timeout_minutes": 480,
        }

        expected = MagicMock(name="ok")

        async def call_next(_request):
            return expected

        db = MagicMock()
        db.get.return_value = active

        with patch("app.main.SessionLocal", return_value=db):
            with patch("app.main.is_session_expired", return_value=False):
                middleware = AuthGuardMiddleware(app=MagicMock())
                import asyncio

                response = asyncio.run(middleware.dispatch(request, call_next))

        self.assertIs(response, expected)
        self.assertEqual(request.session.get("user_id"), 5)


if __name__ == "__main__":
    unittest.main()
