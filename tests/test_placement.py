"""Phase 2 — User organizational placement tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

from sqlalchemy import delete, func, select, text

from app.services import placement as placement_svc
from app.services.placement import PlacementConflictError, PlacementVersionError


class PlacementUnitTests(unittest.TestCase):
    def test_unit_snapshot_empty(self):
        snap = placement_svc._unit_snapshot(None)
        self.assertIsNone(snap["bidang_id"])
        self.assertEqual(snap["bidang_code"], "")

    def test_placement_summary_unassigned(self):
        user = MagicMock()
        user.primary_bidang = None
        user.placement_version = 0
        user.placement_updated_at = None
        summary = placement_svc.placement_summary(user)
        self.assertFalse(summary["is_assigned"])
        self.assertIsNone(summary["bidang_id"])
        self.assertIsNone(summary["division_id"])

    def test_placement_conflict_error_carries_conflicts(self):
        err = PlacementConflictError("conflict", [{"unit_type": "division", "unit_id": 1}])
        self.assertEqual(len(err.conflicts), 1)

    def test_placement_version_error_carries_version(self):
        err = PlacementVersionError("stale", current_version=4)
        self.assertEqual(err.current_version, 4)


@unittest.skipUnless(
    os.environ.get("PM_ORG_INTEGRATION") == "1",
    "Set PM_ORG_INTEGRATION=1 to run against local app DB",
)
class PlacementIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.config import get_settings
        from app.database import SessionLocal
        from app.main import app
        from app.models.models import User
        from app.services.security import create_captcha

        cls.client = TestClient(app)
        cls._create_captcha = staticmethod(create_captcha)
        settings = get_settings()
        cls.admin_email = settings.default_admin_email
        cls.admin_password = settings.default_admin_password
        cls.db = SessionLocal()
        cls.suffix = "P2T"
        cls._cleanup()
        cls.subject = cls.db.scalar(
            select(User)
            .where(User.email != cls.admin_email, User.is_active.is_(True))
            .order_by(User.id.asc())
            .limit(1)
        )
        if cls.subject is None:
            cls.subject = cls.db.scalar(select(User).where(User.email == cls.admin_email).limit(1))
        assert cls.subject is not None
        cls.subject_id = cls.subject.id
        cls.subject_role = cls.subject.role

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()
        cls.db.close()

    @classmethod
    def _cleanup(cls):
        from app.models.models import Bidang, Division, UserPlacementHistory

        bidang_ids = list(
            cls.db.scalars(select(Bidang.id).where(Bidang.code.like(f"%{cls.suffix}%"))).all()
        )
        if bidang_ids:
            cls.db.execute(
                text(
                    "UPDATE users SET primary_bidang_id = NULL, placement_updated_at = NULL "
                    "WHERE primary_bidang_id = ANY(:ids)"
                ),
                {"ids": bidang_ids},
            )
            cls.db.execute(
                delete(UserPlacementHistory).where(
                    UserPlacementHistory.to_bidang_id.in_(bidang_ids)
                    | UserPlacementHistory.from_bidang_id.in_(bidang_ids)
                )
            )
        cls.db.execute(
            delete(UserPlacementHistory).where(
                UserPlacementHistory.to_bidang_code.like(f"%{cls.suffix}%")
                | UserPlacementHistory.from_bidang_code.like(f"%{cls.suffix}%")
            )
        )
        cls.db.execute(delete(Bidang).where(Bidang.code.like(f"%{cls.suffix}%")))
        cls.db.execute(delete(Division).where(Division.code.like(f"%{cls.suffix}%")))
        # Reset any leftover test placement versions on active subjects.
        cls.db.execute(
            text(
                "UPDATE users SET primary_bidang_id = NULL, placement_version = 0, "
                "placement_updated_at = NULL "
                "WHERE primary_bidang_id IS NULL AND placement_version <> 0"
            )
        )
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

    def _seed_units(self):
        self._login_admin()
        d1 = self.client.post(
            "/api/divisions",
            json={"code": f"D1{self.suffix}", "name": "Divisi Placement 1", "is_active": True},
        )
        self.assertEqual(d1.status_code, 201, d1.text)
        d2 = self.client.post(
            "/api/divisions",
            json={"code": f"D2{self.suffix}", "name": "Divisi Placement 2", "is_active": True},
        )
        self.assertEqual(d2.status_code, 201, d2.text)
        b1 = self.client.post(
            "/api/bidang",
            json={
                "division_id": d1.json()["id"],
                "code": f"B1{self.suffix}",
                "name": "Bidang Satu",
                "is_active": True,
            },
        )
        self.assertEqual(b1.status_code, 201, b1.text)
        b2 = self.client.post(
            "/api/bidang",
            json={
                "division_id": d1.json()["id"],
                "code": f"B2{self.suffix}",
                "name": "Bidang Dua",
                "is_active": True,
            },
        )
        self.assertEqual(b2.status_code, 201, b2.text)
        b3 = self.client.post(
            "/api/bidang",
            json={
                "division_id": d2.json()["id"],
                "code": f"B3{self.suffix}",
                "name": "Bidang Lain Divisi",
                "is_active": True,
            },
        )
        self.assertEqual(b3.status_code, 201, b3.text)
        return d1.json(), d2.json(), b1.json(), b2.json(), b3.json()

    def test_unauthenticated_placement_rejected(self):
        self._logout()
        res = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": 1},
        )
        self.assertIn(res.status_code, {401, 303})

    def test_placement_assign_transfer_clear_and_filters(self):
        from app.models.models import Project, Task, User

        before_users = self.db.scalar(select(func.count()).select_from(User))
        before_projects = self.db.scalar(select(func.count()).select_from(Project))
        before_tasks = self.db.scalar(select(func.count()).select_from(Task))

        d1, d2, b1, b2, b3 = self._seed_units()

        current = self.client.get(f"/api/users/{self.subject_id}")
        self.assertEqual(current.status_code, 200, current.text)
        version = int(current.json()["placement"]["placement_version"] or 0)

        assign = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={
                "bidang_id": b1["id"],
                "reason": "penempatan awal",
                "expected_version": version,
            },
        )
        self.assertEqual(assign.status_code, 200, assign.text)
        body = assign.json()
        self.assertTrue(body["placement"]["is_assigned"])
        self.assertEqual(body["placement"]["bidang_id"], b1["id"])
        self.assertEqual(body["placement"]["division_id"], d1["id"])
        self.assertEqual(body["role"], self.subject_role)
        version = body["placement"]["placement_version"]

        dup = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": b1["id"], "expected_version": version},
        )
        self.assertEqual(dup.status_code, 200, dup.text)
        self.assertTrue(dup.json().get("unchanged"))

        bad = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": 999999, "expected_version": version},
        )
        self.assertEqual(bad.status_code, 400)

        self.client.patch(f"/api/bidang/{b2['id']}", json={"is_active": False})
        inactive = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": b2["id"], "expected_version": version},
        )
        self.assertEqual(inactive.status_code, 400)
        self.client.patch(f"/api/bidang/{b2['id']}", json={"is_active": True})

        transfer = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": b2["id"], "reason": "mutasi internal", "expected_version": version},
        )
        self.assertEqual(transfer.status_code, 200, transfer.text)
        self.assertEqual(transfer.json()["placement"]["bidang_id"], b2["id"])
        self.assertEqual(transfer.json()["placement"]["division_id"], d1["id"])
        version = transfer.json()["placement"]["placement_version"]

        stale = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": b3["id"], "expected_version": 0},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "placement_version_conflict")

        cross = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={
                "bidang_id": b3["id"],
                "reason": "mutasi lintas divisi",
                "expected_version": version,
            },
        )
        self.assertEqual(cross.status_code, 200, cross.text)
        self.assertEqual(cross.json()["placement"]["division_id"], d2["id"])
        version = cross.json()["placement"]["placement_version"]
        self.assertEqual(cross.json()["role"], self.subject_role)

        by_div = self.client.get(f"/api/users?division_id={d2['id']}")
        self.assertEqual(by_div.status_code, 200)
        self.assertTrue(any(u["id"] == self.subject_id for u in by_div.json()["items"]))

        by_bidang = self.client.get(f"/api/users?bidang_id={b3['id']}")
        self.assertEqual(by_bidang.status_code, 200)
        self.assertTrue(any(u["id"] == self.subject_id for u in by_bidang.json()["items"]))

        hist = self.client.get(f"/api/users/{self.subject_id}/placement-history")
        self.assertEqual(hist.status_code, 200)
        actions = [row["action"] for row in hist.json()["items"]]
        self.assertIn("assign", actions)
        self.assertIn("transfer", actions)

        lead = self.client.patch(
            f"/api/divisions/{d2['id']}",
            json={"leader_user_id": self.subject_id},
        )
        self.assertEqual(lead.status_code, 200, lead.text)
        conflict = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={"bidang_id": b1["id"], "expected_version": version},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["code"], "leadership_conflict")
        div = self.client.get(f"/api/divisions/{d2['id']}")
        self.assertEqual(div.json()["leader_user_id"], self.subject_id)

        ack = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={
                "bidang_id": b1["id"],
                "expected_version": version,
                "acknowledge_leadership_conflict": True,
                "reason": "mutasi dengan kepemimpinan tetap",
            },
        )
        self.assertEqual(ack.status_code, 200, ack.text)
        version = ack.json()["placement"]["placement_version"]
        div_after = self.client.get(f"/api/divisions/{d2['id']}")
        self.assertEqual(div_after.json()["leader_user_id"], self.subject_id)

        cleared = self.client.put(
            f"/api/users/{self.subject_id}/placement",
            json={
                "clear": True,
                "expected_version": version,
                "acknowledge_leadership_conflict": True,
            },
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertFalse(cleared.json()["placement"]["is_assigned"])

        unassigned = self.client.get("/api/users?unassigned=true")
        self.assertEqual(unassigned.status_code, 200)
        self.assertTrue(any(u["id"] == self.subject_id for u in unassigned.json()["items"]))

        members = self.client.get(f"/api/bidang/{b1['id']}/members")
        self.assertEqual(members.status_code, 200)

        tree = self.client.get("/api/organization/tree")
        self.assertEqual(tree.status_code, 200)
        self.assertIn("unassigned_count", tree.json())

        after_users = self.db.scalar(select(func.count()).select_from(User))
        after_projects = self.db.scalar(select(func.count()).select_from(Project))
        after_tasks = self.db.scalar(select(func.count()).select_from(Task))
        self.assertEqual(after_users, before_users)
        self.assertEqual(after_projects, before_projects)
        self.assertEqual(after_tasks, before_tasks)

        self.db.expire_all()
        refreshed = self.db.get(User, self.subject_id)
        self.assertEqual(refreshed.role, self.subject_role)

        self._logout()


if __name__ == "__main__":
    unittest.main()
