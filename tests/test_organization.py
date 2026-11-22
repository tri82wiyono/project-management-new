"""Phase 1 — Organization Management tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import organization as org_svc
from app.services.roles import PERMISSION_CATALOG


class OrganizationPermissionCatalogTests(unittest.TestCase):
    def test_catalog_includes_organization_permissions(self):
        keys = {item["key"] for item in PERMISSION_CATALOG}
        self.assertIn("organization.view", keys)
        self.assertIn("organization.manage", keys)


class OrganizationValidationUnitTests(unittest.TestCase):
    def test_norm_code_uppercases(self):
        self.assertEqual(org_svc._norm_code("  div-a "), "DIV-A")

    def test_require_active_leader_rejects_inactive(self):
        db = MagicMock()
        user = MagicMock()
        user.is_active = False
        db.get.return_value = user
        with self.assertRaises(ValueError):
            org_svc.require_active_leader(db, 1)

    def test_require_active_leader_allows_active(self):
        db = MagicMock()
        user = MagicMock()
        user.is_active = True
        user.id = 7
        db.get.return_value = user
        self.assertIs(org_svc.require_active_leader(db, 7), user)

    def test_require_active_leader_none(self):
        db = MagicMock()
        self.assertIsNone(org_svc.require_active_leader(db, None))


@unittest.skipUnless(
    os.environ.get("PM_ORG_INTEGRATION") == "1",
    "Set PM_ORG_INTEGRATION=1 to run against local app DB",
)
class OrganizationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.security import create_captcha
        from app.database import SessionLocal
        from app.models.models import User
        from sqlalchemy import select
        from app.config import get_settings

        cls.client = TestClient(app)
        cls._create_captcha = staticmethod(create_captcha)
        settings = get_settings()
        cls.admin_email = settings.default_admin_email
        cls.admin_password = settings.default_admin_password
        cls.db = SessionLocal()
        cls.suffix = "P1T"
        # cleanup leftovers from prior runs
        cls._cleanup()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()
        cls.db.close()

    @classmethod
    def _cleanup(cls):
        from app.models.models import Bidang, Division
        from sqlalchemy import delete

        cls.db.execute(delete(Bidang).where(Bidang.code.like(f"%{cls.suffix}%")))
        cls.db.execute(delete(Division).where(Division.code.like(f"%{cls.suffix}%")))
        cls.db.commit()

    def _login_admin(self):
        from app.services.security import create_captcha

        token, answer, _ = create_captcha()
        res = self.client.post(
            "/api/auth/login",
            json={
                "email": self.admin_email,
                "password": self.admin_password,
                "captcha_id": token,
                "captcha_answer": answer,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_unauthenticated_mutation_rejected(self):
        res = self.client.post(
            "/api/divisions",
            json={"code": f"X{self.suffix}", "name": "Nope"},
        )
        self.assertIn(res.status_code, {401, 303})

    def test_division_bidang_leadership_flow(self):
        self._login_admin()
        # Create division without bidang
        r = self.client.post(
            "/api/divisions",
            json={"code": f"D1{self.suffix}", "name": "Divisi Test 1", "is_active": True},
        )
        self.assertEqual(r.status_code, 201, r.text)
        div = r.json()
        self.assertEqual(div["bidang_count"], 0)

        # Duplicate code
        r2 = self.client.post(
            "/api/divisions",
            json={"code": f"d1{self.suffix}", "name": "Dup"},
        )
        self.assertEqual(r2.status_code, 400)

        # Create two bidang
        b1 = self.client.post(
            "/api/bidang",
            json={
                "division_id": div["id"],
                "code": f"B1{self.suffix}",
                "name": "Bidang Satu",
                "is_active": True,
            },
        )
        self.assertEqual(b1.status_code, 201, b1.text)
        b2 = self.client.post(
            "/api/bidang",
            json={
                "division_id": div["id"],
                "code": f"B2{self.suffix}",
                "name": "Bidang Dua",
                "is_active": True,
            },
        )
        self.assertEqual(b2.status_code, 201, b2.text)

        # Duplicate bidang code in same division
        dup = self.client.post(
            "/api/bidang",
            json={
                "division_id": div["id"],
                "code": f"b1{self.suffix}",
                "name": "Dup Bidang",
            },
        )
        self.assertEqual(dup.status_code, 400)

        # Invalid parent
        bad = self.client.post(
            "/api/bidang",
            json={"division_id": 999999, "code": f"BX{self.suffix}", "name": "X"},
        )
        self.assertEqual(bad.status_code, 400)

        # Assign leader = admin user
        from app.models.models import User
        from sqlalchemy import select

        admin = self.db.scalar(select(User).where(User.email == self.admin_email).limit(1))
        self.assertIsNotNone(admin)
        lead = self.client.patch(
            f"/api/divisions/{div['id']}",
            json={"leader_user_id": admin.id},
        )
        self.assertEqual(lead.status_code, 200, lead.text)
        self.assertEqual(lead.json()["leader_user_id"], admin.id)

        # Inactive user rejected
        inactive = self.db.scalar(select(User).where(User.is_active.is_(False)).limit(1))
        if inactive:
            bad_lead = self.client.patch(
                f"/api/divisions/{div['id']}",
                json={"leader_user_id": inactive.id},
            )
            self.assertEqual(bad_lead.status_code, 400)

        # Deactivate division — bidang remain
        deact = self.client.patch(f"/api/divisions/{div['id']}", json={"is_active": False})
        self.assertEqual(deact.status_code, 200)
        listed = self.client.get(f"/api/divisions/{div['id']}/bidang")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.json()["total"], 2)

        # Cannot create active bidang under inactive division
        blocked = self.client.post(
            "/api/bidang",
            json={
                "division_id": div["id"],
                "code": f"B3{self.suffix}",
                "name": "Blocked",
                "is_active": True,
            },
        )
        self.assertEqual(blocked.status_code, 400)

        # Tree
        tree = self.client.get("/api/organization/tree")
        self.assertEqual(tree.status_code, 200)
        self.assertIn("organization_name", tree.json())

        # Member cannot mutate (if a member exists)
        # logout then skip if no member credentials — covered by permission dependency unit-style via 403 with non-admin session
        self.client.post("/api/auth/logout")


class OrganizationNavTests(unittest.TestCase):
    def test_nav_includes_organization_item(self):
        from app.templating import NAV_ITEMS

        item = next((i for i in NAV_ITEMS if i["key"] == "organization"), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["href"], "/organization")
        self.assertIn("organization.view", item["permissions"])


if __name__ == "__main__":
    unittest.main()
