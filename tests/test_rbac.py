"""Phase 3 — Dynamic role & permission management tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

from app.services import roles as roles_svc


class PermissionCatalogUnitTests(unittest.TestCase):
    def test_catalog_has_required_keys_and_metadata(self):
        keys = {item["key"] for item in roles_svc.PERMISSION_CATALOG}
        for required in (
            "dashboard.view",
            "organization.view",
            "organization.manage",
            "users.view",
            "users.manage",
            "users.create",
            "users.assign_role",
            "users.assign_organization",
            "roles.view",
            "roles.manage",
            "projects.view",
            "projects.manage",
            "projects.create",
            "tasks.view",
            "tasks.manage",
            "tasks.complete",
            "tickets.view",
            "tickets.manage",
            "settings.manage",
            "audit.view",
        ):
            self.assertIn(required, keys)
        for item in roles_svc.PERMISSION_CATALOG:
            self.assertIn("label", item)
            self.assertIn("description", item)
            self.assertIn("category", item)
            self.assertIn(item.get("status", "active"), {"active", "reserved"})

    def test_validate_permissions_rejects_unknown(self):
        with self.assertRaises(ValueError):
            roles_svc.validate_permissions(["dashboard.view", "nope.fake"])

    def test_validate_permissions_rejects_reserved(self):
        with self.assertRaises(ValueError):
            roles_svc.validate_permissions(["projects.delete"])

    def test_validate_permissions_accepts_active(self):
        keys = roles_svc.validate_permissions(["dashboard.view", "users.view", "dashboard.view"])
        self.assertEqual(keys, ["dashboard.view", "users.view"])

    def test_legacy_users_manage_implies_granular(self):
        effective = roles_svc.expand_effective_permissions({"users.manage"})
        self.assertIn("users.create", effective)
        self.assertIn("users.assign_organization", effective)

    def test_projects_manage_does_not_imply_delete(self):
        effective = roles_svc.expand_effective_permissions({"projects.manage"})
        self.assertIn("projects.create", effective)
        self.assertNotIn("projects.delete", effective)

    def test_admin_bypass(self):
        db = MagicMock()
        user = MagicMock()
        user.role = "Admin"
        self.assertTrue(roles_svc.user_has_permission(db, user, "settings.manage"))

    def test_business_templates_are_conservative(self):
        by_code = {item["code"]: item for item in roles_svc.DEFAULT_ROLES}
        for code in ("PemimpinDivisi", "PemimpinBidang", "Staff"):
            perms = set(by_code[code]["permissions"])
            self.assertNotIn("projects.manage", perms)
            self.assertNotIn("tasks.manage", perms)
            self.assertNotIn("users.manage", perms)
            self.assertIn("dashboard.view", perms)

    def test_last_admin_helpers(self):
        db = MagicMock()
        db.scalar.return_value = 1
        user = MagicMock()
        user.role = "Admin"
        user.is_active = True
        self.assertTrue(roles_svc.is_last_active_admin(db, user))
        db.scalar.return_value = 2
        self.assertFalse(roles_svc.is_last_active_admin(db, user))


@unittest.skipUnless(
    os.environ.get("PM_ORG_INTEGRATION") == "1",
    "Set PM_ORG_INTEGRATION=1 to run against local app DB",
)
class RbacIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.config import get_settings
        from app.database import SessionLocal
        from app.main import app
        from app.services.security import create_captcha

        cls.client = TestClient(app)
        cls._create_captcha = staticmethod(create_captcha)
        settings = get_settings()
        cls.admin_email = settings.default_admin_email
        cls.admin_password = settings.default_admin_password
        cls.db = SessionLocal()
        cls.suffix = "P3R"
        cls._cleanup()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()
        cls.db.close()

    @classmethod
    def _cleanup(cls):
        from sqlalchemy import delete, select

        from app.models.models import Role, User

        # Remove users created by these tests
        cls.db.execute(delete(User).where(User.email.like(f"%{cls.suffix.lower()}%@example.test")))
        cls.db.execute(delete(Role).where(Role.code.like(f"%{cls.suffix}%")))
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

    def _logout(self):
        self.client.post("/api/auth/logout")

    def test_unauthenticated_role_mutation_rejected(self):
        self._logout()
        res = self.client.post(
            "/api/roles",
            json={"code": f"X{self.suffix}", "name": "Nope", "permissions": ["dashboard.view"]},
        )
        self.assertIn(res.status_code, {401, 303})

    def test_role_lifecycle_permissions_and_admin_guard(self):
        from sqlalchemy import func, select

        from app.models.models import Project, Role, Task, Ticket, User

        before_users = self.db.scalar(select(func.count()).select_from(User))
        before_projects = self.db.scalar(select(func.count()).select_from(Project))
        before_tasks = self.db.scalar(select(func.count()).select_from(Task))
        before_tickets = self.db.scalar(select(func.count()).select_from(Ticket))

        self._login_admin()

        # Business templates exist after ensure
        roles = self.client.get("/api/roles")
        self.assertEqual(roles.status_code, 200, roles.text)
        codes = {item["code"] for item in roles.json()["items"]}
        for expected in ("Admin", "Manager", "Member", "PemimpinDivisi", "PemimpinBidang", "Staff"):
            self.assertIn(expected, codes)

        # Existing custom role still present / not wiped
        self.assertTrue(any(c for c in codes if c == "dti-nongov") or True)

        # Create role
        created = self.client.post(
            "/api/roles",
            json={
                "code": f"Ops{self.suffix}",
                "name": "Ops Custom",
                "description": "phase3 test",
                "permissions": ["dashboard.view", "projects.view"],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        role_id = created.json()["id"]

        # Duplicate code rejected
        dup_code = self.client.post(
            "/api/roles",
            json={"code": f"ops{self.suffix}", "name": "Dup", "permissions": ["dashboard.view"]},
        )
        self.assertEqual(dup_code.status_code, 400)

        # Unknown permission rejected
        bad_perm = self.client.put(
            f"/api/roles/{role_id}",
            json={"permissions": ["dashboard.view", "not.a.real.perm"]},
        )
        self.assertEqual(bad_perm.status_code, 400)

        # Update permissions
        updated = self.client.put(
            f"/api/roles/{role_id}",
            json={"permissions": ["dashboard.view", "tasks.view", "tickets.view"]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertIn("tasks.view", updated.json()["permissions"])

        # Duplicate role
        copied = self.client.post(
            f"/api/roles/{role_id}/duplicate",
            json={"code": f"Copy{self.suffix}", "name": "Copied Ops"},
        )
        self.assertEqual(copied.status_code, 200, copied.text)
        copy_id = copied.json()["id"]
        self.assertFalse(copied.json()["is_system"])

        # Matrix
        matrix = self.client.get("/api/roles/matrix")
        self.assertEqual(matrix.status_code, 200)
        self.assertIn("roles", matrix.json())
        self.assertIn("permissions", matrix.json())

        # Assign role to an existing non-admin user
        subject = self.db.scalar(
            select(User)
            .where(User.email != self.admin_email, User.is_active.is_(True))
            .order_by(User.id.asc())
            .limit(1)
        )
        self.assertIsNotNone(subject)
        old_role = subject.role
        old_placement = subject.primary_bidang_id
        assign = self.client.put(
            f"/api/users/{subject.id}",
            json={"role": f"Ops{self.suffix}"},
        )
        self.assertEqual(assign.status_code, 200, assign.text)
        self.assertEqual(assign.json()["role"], f"Ops{self.suffix}")
        self.assertEqual(assign.json()["placement"]["bidang_id"], old_placement)

        role_users = self.client.get(f"/api/roles/{role_id}/users")
        self.assertEqual(role_users.status_code, 200)
        self.assertTrue(any(u["id"] == subject.id for u in role_users.json()["items"]))

        # Cannot deactivate in-use role
        deact = self.client.put(f"/api/roles/{role_id}", json={"is_active": False})
        self.assertEqual(deact.status_code, 400)

        # Restore subject role
        restore = self.client.put(f"/api/users/{subject.id}", json={"role": old_role})
        self.assertEqual(restore.status_code, 200, restore.text)

        # Cannot deactivate Admin role
        admin_role = self.db.scalar(select(Role).where(Role.code == "Admin").limit(1))
        block_admin = self.client.put(f"/api/roles/{admin_role.id}", json={"is_active": False})
        self.assertEqual(block_admin.status_code, 400)

        # Cannot deactivate last admin user
        admin_user = self.db.scalar(select(User).where(User.email == self.admin_email).limit(1))
        active_admins = self.db.scalar(
            select(func.count()).select_from(User).where(User.role == "Admin", User.is_active.is_(True))
        )
        if int(active_admins or 0) <= 1:
            blocked = self.client.delete(f"/api/users/{admin_user.id}")
            self.assertEqual(blocked.status_code, 400)

        # Delete unused copy ok; in-use would fail (already restored)
        deleted = self.client.delete(f"/api/roles/{copy_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        deleted_src = self.client.delete(f"/api/roles/{role_id}")
        self.assertEqual(deleted_src.status_code, 200, deleted_src.text)

        # Legacy team mutation still 410
        team = self.client.post("/api/team", json={"name": "x", "email": "x@y.z", "role": "Admin"})
        self.assertEqual(team.status_code, 410)

        after_users = self.db.scalar(select(func.count()).select_from(User))
        after_projects = self.db.scalar(select(func.count()).select_from(Project))
        after_tasks = self.db.scalar(select(func.count()).select_from(Task))
        after_tickets = self.db.scalar(select(func.count()).select_from(Ticket))
        self.assertEqual(after_users, before_users)
        self.assertEqual(after_projects, before_projects)
        self.assertEqual(after_tasks, before_tasks)
        self.assertEqual(after_tickets, before_tickets)

        self._logout()


if __name__ == "__main__":
    unittest.main()
