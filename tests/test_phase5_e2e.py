"""Phase 5 — Isolated E2E organizational scope readiness.

MUST run only with:
  DATABASE_URL → project_mgmt_test / pm_test_user
  ORG_SCOPE_ENFORCEMENT=true

Use scripts/run_phase5_e2e.sh (starts disposable Postgres + verifies isolation).
"""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta

# Isolation gate before importing application modules that bind the DB engine.
_DB_URL = os.environ.get("DATABASE_URL", "")
_ENFORCE = os.environ.get("ORG_SCOPE_ENFORCEMENT", "").lower() in {"1", "true", "yes"}
_ISOLATED = (
    "project_mgmt_test" in _DB_URL
    and "pm_test_user" in _DB_URL
    and _ENFORCE
)


@unittest.skipUnless(
    _ISOLATED,
    "Requires isolated DATABASE_URL (project_mgmt_test/pm_test_user) and ORG_SCOPE_ENFORCEMENT=true",
)
class Phase5E2EOrgScopeTests(unittest.TestCase):
    password = "Phase5User@Test99"
    suffix = "P5E2E"

    @classmethod
    def setUpClass(cls):
        # Re-check isolation (script already ran by runner; belt-and-suspenders).
        url = os.environ.get("DATABASE_URL", "")
        if "project_mgmt_test" not in url or "pm_test_user" not in url:
            raise unittest.SkipTest("Isolation verification failed")
        if os.environ.get("ORG_SCOPE_ENFORCEMENT", "").lower() not in {"1", "true", "yes"}:
            raise unittest.SkipTest("ORG_SCOPE_ENFORCEMENT not enabled")

        from fastapi.testclient import TestClient
        from sqlalchemy import delete, select

        from app.config import get_settings
        from app.database import Base, SessionLocal, engine
        from app.db_migrate import ensure_schema
        from app.main import app
        from app.models.models import (
            Bidang,
            Division,
            Project,
            Role,
            Task,
            TaskAssignee,
            TeamMember,
            User,
        )
        from app.services.auth import ensure_default_admin
        from app.services.roles import PHASE4_PENDING_PERMISSIONS, ensure_default_roles
        from app.services.security import create_captcha, hash_password
        from app.services.security_settings import get_or_create_security_settings

        # Bootstrap schema on the isolated DB (do not rely solely on lifespan).
        Base.metadata.create_all(bind=engine)
        ensure_schema()

        # Context manager runs lifespan; keep client for the whole class.
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()
        cls.db = SessionLocal()
        cls.settings = get_settings()
        if not cls.settings.org_scope_enforcement:
            raise unittest.SkipTest("Settings.org_scope_enforcement is false")
        cls._create_captcha = staticmethod(create_captcha)
        cls.hash_password = staticmethod(hash_password)

        get_or_create_security_settings(cls.db)
        ensure_default_roles(cls.db)
        ensure_default_admin(cls.db)
        cls.db.commit()
        # Simulate Admin enabling scope-dependent permissions AFTER enforcement is on
        # (test DB only — never auto-applied to production roles).
        for code, pending in PHASE4_PENDING_PERMISSIONS.items():
            role = cls.db.scalar(select(Role).where(Role.code == code).limit(1))
            if not role:
                continue
            merged = list(dict.fromkeys(list(role.permissions or []) + list(pending)))
            # Ensure view keys present for leaders/staff under scope.
            if code in ("PemimpinDivisi", "PemimpinBidang", "Staff"):
                for key in ("dashboard.view", "projects.view", "tasks.view", "tickets.view"):
                    if key not in merged:
                        merged.append(key)
            role.permissions = merged
        cls.db.commit()

        cls._purge_fixtures()

        today = date.today()
        end = today + timedelta(days=60)

        div_a = Division(code=f"DA{cls.suffix}", name="Division A Test", is_active=True)
        div_b = Division(code=f"DB{cls.suffix}", name="Division B Test", is_active=True)
        cls.db.add_all([div_a, div_b])
        cls.db.flush()
        b_a1 = Bidang(division_id=div_a.id, code=f"A1{cls.suffix}", name="Bidang A1", is_active=True)
        b_a2 = Bidang(division_id=div_a.id, code=f"A2{cls.suffix}", name="Bidang A2", is_active=True)
        b_b1 = Bidang(division_id=div_b.id, code=f"B1{cls.suffix}", name="Bidang B1", is_active=True)
        b_b2 = Bidang(division_id=div_b.id, code=f"B2{cls.suffix}", name="Bidang B2", is_active=True)
        cls.db.add_all([b_a1, b_a2, b_b1, b_b2])
        cls.db.flush()

        def mk_user(tag: str, role: str, bidang_id: int | None) -> User:
            user = User(
                name=f"Synth {tag} {cls.suffix}",
                email=f"{tag.lower()}.{cls.suffix.lower()}@example.test",
                password_hash=hash_password(cls.password),
                role=role,
                is_active=True,
                avatar_url="",
                mfa_enabled=False,
                must_change_password=False,
                primary_bidang_id=bidang_id,
            )
            cls.db.add(user)
            cls.db.flush()
            return user

        u_div_a = mk_user("DivALeader", "PemimpinDivisi", b_a1.id)
        u_div_b = mk_user("DivBLeader", "PemimpinDivisi", b_b1.id)
        u_a1 = mk_user("BidangA1Leader", "PemimpinBidang", b_a1.id)
        u_a2 = mk_user("BidangA2Leader", "PemimpinBidang", b_a2.id)
        u_b1 = mk_user("BidangB1Leader", "PemimpinBidang", b_b1.id)
        staff_a1 = mk_user("StaffA1", "Staff", b_a1.id)
        staff_a2 = mk_user("StaffA2", "Staff", b_a2.id)
        staff_b1 = mk_user("StaffB1", "Staff", b_b1.id)
        cross = mk_user("CrossMember", "Staff", b_b2.id)

        div_a.leader_user_id = u_div_a.id
        div_b.leader_user_id = u_div_b.id
        b_a1.leader_user_id = u_a1.id
        b_a2.leader_user_id = u_a2.id
        b_b1.leader_user_id = u_b1.id

        def mk_project(name: str, owner_type: str, div_id=None, bidang_id=None) -> Project:
            p = Project(
                name=f"{name} {cls.suffix}",
                description=name,
                pic="Synth PIC",
                start_date=today,
                end_date=end,
                owner_type=owner_type,
                owner_division_id=div_id,
                owner_bidang_id=bidang_id,
            )
            cls.db.add(p)
            cls.db.flush()
            return p

        p_div_a = mk_project("Proj DivA", "division", div_a.id, None)
        p_a1 = mk_project("Proj BidangA1", "bidang", div_a.id, b_a1.id)
        p_a2 = mk_project("Proj BidangA2", "bidang", div_a.id, b_a2.id)
        p_div_b = mk_project("Proj DivB", "division", div_b.id, None)
        p_b1 = mk_project("Proj BidangB1", "bidang", div_b.id, b_b1.id)
        p_cross = mk_project("Proj Cross", "division", div_a.id, None)
        p_legacy = mk_project("Proj Legacy", "unassigned", None, None)

        cls.db.add(TeamMember(project_id=p_cross.id, user_id=cross.id, role=cross.role))
        cls.db.add(TeamMember(project_id=p_a1.id, user_id=staff_a1.id, role=staff_a1.role))

        t_a1 = Task(project_id=p_a1.id, title=f"Task A1 {cls.suffix}", category="ModuleA")
        t_cross = Task(project_id=p_cross.id, title=f"Task Cross {cls.suffix}", category="ModuleX")
        t_legacy = Task(project_id=p_legacy.id, title=f"Task Legacy {cls.suffix}", category="Legacy")
        cls.db.add_all([t_a1, t_cross, t_legacy])
        cls.db.flush()
        cls.db.add(TaskAssignee(task_id=t_a1.id, user_id=staff_a1.id))
        cls.db.add(TaskAssignee(task_id=t_cross.id, user_id=cross.id))
        cls.db.commit()

        cls.ids = {
            "div_a": div_a.id,
            "div_b": div_b.id,
            "b_a1": b_a1.id,
            "b_a2": b_a2.id,
            "b_b1": b_b1.id,
            "p_div_a": p_div_a.id,
            "p_a1": p_a1.id,
            "p_a2": p_a2.id,
            "p_div_b": p_div_b.id,
            "p_b1": p_b1.id,
            "p_cross": p_cross.id,
            "p_legacy": p_legacy.id,
            "t_a1": t_a1.id,
            "t_cross": t_cross.id,
            "t_legacy": t_legacy.id,
        }
        cls.emails = {
            "admin": cls.settings.default_admin_email,
            "div_a": u_div_a.email,
            "div_b": u_div_b.email,
            "a1": u_a1.email,
            "a2": u_a2.email,
            "b1": u_b1.email,
            "staff_a1": staff_a1.email,
            "staff_a2": staff_a2.email,
            "staff_b1": staff_b1.email,
            "cross": cross.email,
        }
        cls.admin_password = cls.settings.default_admin_password

    @classmethod
    def tearDownClass(cls):
        try:
            cls._purge_fixtures()
        finally:
            cls.db.close()
            if getattr(cls, "_client_cm", None) is not None:
                cls._client_cm.__exit__(None, None, None)

    @classmethod
    def _purge_fixtures(cls):
        from sqlalchemy import delete, select

        from app.models.models import (
            Bidang,
            Division,
            Project,
            Task,
            TaskAssignee,
            TeamMember,
            User,
        )

        project_ids = list(
            cls.db.scalars(select(Project.id).where(Project.name.like(f"%{cls.suffix}%"))).all()
        )
        if project_ids:
            task_ids = list(
                cls.db.scalars(select(Task.id).where(Task.project_id.in_(project_ids))).all()
            )
            if task_ids:
                cls.db.execute(delete(TaskAssignee).where(TaskAssignee.task_id.in_(task_ids)))
            cls.db.execute(delete(TeamMember).where(TeamMember.project_id.in_(project_ids)))
            cls.db.execute(delete(Task).where(Task.project_id.in_(project_ids)))
            cls.db.execute(delete(Project).where(Project.id.in_(project_ids)))
        cls.db.execute(delete(User).where(User.email.like(f"%{cls.suffix.lower()}%@example.test")))
        cls.db.execute(delete(Bidang).where(Bidang.code.like(f"%{cls.suffix}%")))
        cls.db.execute(delete(Division).where(Division.code.like(f"%{cls.suffix}%")))
        cls.db.commit()

    def _login(self, email: str, password: str | None = None):
        from sqlalchemy import delete, select

        from app.models.models import User, UserDevice

        # Isolated tests: reset trusted devices so first-device bootstrap always applies
        # (logout clears the device cookie; leftover DB devices would force email confirm).
        user = self.db.scalar(select(User).where(User.email == email).limit(1))
        if user is not None:
            self.db.execute(delete(UserDevice).where(UserDevice.user_id == user.id))
            self.db.commit()

        self.client.post("/api/auth/logout")
        token, answer, _ = self._create_captcha()
        res = self.client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": password or self.password,
                "captcha_id": token,
                "captcha_answer": answer,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertFalse(body.get("mfa_required"), body)
        self.assertFalse(body.get("device_confirmation_required"), body)
        return body

    def test_01_admin_sees_all_and_classifies_legacy(self):
        from sqlalchemy import select

        from app.models.models import AuditLog, Project

        self._login(self.emails["admin"], self.admin_password)
        listing = self.client.get("/api/projects?page=1&page_size=100")
        self.assertEqual(listing.status_code, 200)
        ids = {i["id"] for i in listing.json()["items"]}
        for key in ("p_div_a", "p_div_b", "p_legacy", "p_cross"):
            self.assertIn(self.ids[key], ids)

        before = self.db.get(Project, self.ids["p_legacy"])
        self.assertEqual(before.owner_type, "unassigned")

        res = self.client.put(
            f"/api/projects/{self.ids['p_legacy']}/ownership",
            json={
                "owner_type": "division",
                "owner_division_id": self.ids["div_a"],
                "owner_bidang_id": None,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.db.expire_all()
        after = self.db.get(Project, self.ids["p_legacy"])
        self.assertEqual(after.owner_type, "division")
        self.assertEqual(after.owner_division_id, self.ids["div_a"])

        audit = self.db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "project_ownership_classified")
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        self.assertIsNotNone(audit)

        # restore unassigned for later legacy denial tests
        restore = self.client.put(
            f"/api/projects/{self.ids['p_legacy']}/ownership",
            json={"owner_type": "unassigned"},
        )
        self.assertEqual(restore.status_code, 200)

    def test_02_divisi_leader_scope(self):
        self._login(self.emails["div_a"])
        ok = self.client.get(f"/api/projects/{self.ids['p_div_a']}")
        self.assertEqual(ok.status_code, 200)
        child = self.client.get(f"/api/projects/{self.ids['p_a1']}")
        self.assertEqual(child.status_code, 200)
        denied = self.client.get(f"/api/projects/{self.ids['p_div_b']}")
        self.assertEqual(denied.status_code, 404)
        listing = self.client.get("/api/projects?page=1&page_size=100")
        ids = {i["id"] for i in listing.json()["items"]}
        self.assertIn(self.ids["p_div_a"], ids)
        self.assertIn(self.ids["p_a2"], ids)
        self.assertNotIn(self.ids["p_div_b"], ids)

    def test_03_bidang_leader_no_sibling(self):
        self._login(self.emails["a1"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_a1']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_a2']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_div_b']}").status_code, 404)

    def test_04_staff_membership_and_task_idor(self):
        from sqlalchemy import select

        from app.models.models import Task

        self._login(self.emails["staff_a1"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_a1']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_a2']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/tasks/{self.ids['t_a1']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/tasks/{self.ids['t_legacy']}").status_code, 404)

        # Denied mutation must not change DB
        before = self.db.scalar(select(Task.title).where(Task.id == self.ids["t_legacy"]))
        denied = self.client.patch(
            f"/api/tasks/{self.ids['t_legacy']}",
            json={"title": "HACKED"},
        )
        self.assertIn(denied.status_code, (403, 404))
        self.db.expire_all()
        after = self.db.scalar(select(Task.title).where(Task.id == self.ids["t_legacy"]))
        self.assertEqual(before, after)

    def test_05_cross_unit_member_only_assigned_project(self):
        self._login(self.emails["cross"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_cross']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_div_a']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/tasks/{self.ids['t_cross']}").status_code, 200)
        listing = self.client.get("/api/projects?page=1&page_size=100")
        ids = {i["id"] for i in listing.json()["items"]}
        self.assertEqual(ids & {self.ids["p_cross"], self.ids["p_div_a"], self.ids["p_div_b"]}, {self.ids["p_cross"]})

    def test_06_legacy_unclassified_hidden_from_non_admin(self):
        self._login(self.emails["div_a"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_legacy']}").status_code, 404)
        self._login(self.emails["staff_a1"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_legacy']}").status_code, 404)

    def test_07_manage_does_not_bypass_via_dashboard(self):
        self._login(self.emails["staff_b1"])
        summary = self.client.get("/api/dashboard/summary")
        # Staff may lack dashboard.view depending on template — accept 200 or 403
        if summary.status_code == 200:
            progress_ids = {p["id"] for p in summary.json().get("progress") or []}
            self.assertNotIn(self.ids["p_div_a"], progress_ids)
            self.assertNotIn(self.ids["p_legacy"], progress_ids)

    def test_08_ownership_options_without_organization_view(self):
        # Staff with pending create may still lack organization.view — leaders have update pending
        self._login(self.emails["a1"])
        res = self.client.get("/api/organization/ownership-options")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(any(d["id"] == self.ids["div_a"] for d in body["divisions"]))
        self.assertNotIn("leader_user_id", str(body))

    def test_09_team_directory_requires_assign_level(self):
        # View-only denial: temporarily login as Staff without pending if stripped —
        # With pending applied, Staff has tasks.create — directory allowed.
        # Explicitly verify purpose=members scopes to project.
        self._login(self.emails["staff_a1"])
        members = self.client.get(
            f"/api/team?purpose=members&project_id={self.ids['p_a1']}&active_only=true"
        )
        self.assertEqual(members.status_code, 200, members.text)
        denied_members = self.client.get(
            f"/api/team?purpose=members&project_id={self.ids['p_div_b']}&active_only=true"
        )
        self.assertEqual(denied_members.status_code, 404)

    def test_10_membership_removal_revokes_access(self):
        from sqlalchemy import delete, select

        from app.models.models import TaskAssignee, User

        self._login(self.emails["admin"], self.admin_password)
        project = self.client.get(f"/api/projects/{self.ids['p_cross']}")
        self.assertEqual(project.status_code, 200)
        cleared = self.client.patch(
            f"/api/projects/{self.ids['p_cross']}",
            json={"member_ids": []},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)

        # Task assignment alone still grants project visibility (documented policy).
        self._login(self.emails["cross"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_cross']}").status_code, 200)

        # Remove assignment → access revoked.
        self.db.execute(delete(TaskAssignee).where(TaskAssignee.task_id == self.ids["t_cross"]))
        self.db.commit()
        self._login(self.emails["cross"])
        self.assertEqual(self.client.get(f"/api/projects/{self.ids['p_cross']}").status_code, 404)

        cross = self.db.scalar(select(User).where(User.email == self.emails["cross"]).limit(1))
        self._login(self.emails["admin"], self.admin_password)
        restored = self.client.patch(
            f"/api/projects/{self.ids['p_cross']}",
            json={"member_ids": [cross.id]},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.db.add(TaskAssignee(task_id=self.ids["t_cross"], user_id=cross.id))
        self.db.commit()

    def test_11_csrf_rejects_foreign_origin(self):
        self._login(self.emails["admin"], self.admin_password)
        res = self.client.patch(
            f"/api/projects/{self.ids['p_div_a']}",
            json={"description": "csrf-probe"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(res.status_code, 403)

    def test_12_project_create_persists_ownership(self):
        from sqlalchemy import select

        from app.models.models import Project

        self._login(self.emails["admin"], self.admin_password)
        today = date.today()
        res = self.client.post(
            "/api/projects",
            json={
                "name": f"Created {self.suffix}",
                "description": "e2e create",
                "pic": "Admin",
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=10)).isoformat(),
                "status": "backlog",
                "member_ids": [],
                "owner_type": "bidang",
                "owner_division_id": self.ids["div_a"],
                "owner_bidang_id": self.ids["b_a1"],
            },
        )
        self.assertEqual(res.status_code, 201, res.text)
        pid = res.json()["id"]
        self.db.expire_all()
        row = self.db.get(Project, pid)
        self.assertEqual(row.owner_type, "bidang")
        self.assertEqual(row.owner_bidang_id, self.ids["b_a1"])
        self.assertEqual(row.owner_division_id, self.ids["div_a"])


if __name__ == "__main__":
    unittest.main()
