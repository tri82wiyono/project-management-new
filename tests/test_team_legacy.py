"""Test Group A — legacy /api/team mutation hardening (SEC-01 / SEC-02)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import team as team_router
from app.routers.team import LEGACY_MUTATION_DISABLED_DETAIL


class LegacyTeamMutationUnitTests(unittest.TestCase):
    def test_create_member_disabled_raises_410(self):
        with self.assertRaises(HTTPException) as ctx:
            team_router.create_member_disabled()
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertEqual(ctx.exception.detail, LEGACY_MUTATION_DISABLED_DETAIL)

    def test_update_member_disabled_raises_410(self):
        with self.assertRaises(HTTPException) as ctx:
            team_router.update_member_disabled(user_id=1)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("/api/users", str(ctx.exception.detail))


class LegacyTeamHttpTests(unittest.TestCase):
    """HTTP-level checks without touching a shared database."""

    def setUp(self):
        app = FastAPI()
        app.include_router(team_router.router)

        async def _fake_user():
            user = MagicMock()
            user.id = 99
            user.role = "Member"
            user.is_active = True
            return user

        # Bypass auth dependencies for mutation endpoints (they no longer use them).
        app.dependency_overrides = {}
        self.client = TestClient(app)

    def test_post_team_returns_410_unauthenticated(self):
        response = self.client.post("/api/team", json={"name": "X", "email": "x@example.com"})
        self.assertEqual(response.status_code, 410)
        self.assertIn("disabled", response.json()["detail"].lower())

    def test_patch_team_returns_410_with_role_escalation_payload(self):
        response = self.client.patch(
            "/api/team/1",
            json={"role": "Admin", "is_active": True, "password_hash": "nope"},
        )
        self.assertEqual(response.status_code, 410)
        body = response.json()["detail"]
        self.assertIn("/api/users", body)

    def test_post_does_not_echo_sensitive_fields(self):
        response = self.client.post(
            "/api/team",
            json={
                "name": "Attacker",
                "email": "attacker@example.com",
                "role": "Admin",
                "temporary_password": "should-not-appear",
            },
        )
        self.assertEqual(response.status_code, 410)
        raw = response.text
        self.assertNotIn("should-not-appear", raw)
        self.assertNotIn("password_hash", raw)


if __name__ == "__main__":
    unittest.main()
