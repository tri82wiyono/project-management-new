"""Phase 5 unit tests (no database mutation)."""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.csrf_guard import _host_from_url, allowed_csrf_hosts


class CsrfUnitTests(unittest.TestCase):
    def test_host_parser(self):
        self.assertEqual(_host_from_url("https://pm.banksumut.example/x"), "pm.banksumut.example")
        self.assertIsNone(_host_from_url(None))
        self.assertIsNone(_host_from_url("null"))

    def test_allowed_hosts_include_localhost(self):
        self.assertIn("localhost", allowed_csrf_hosts())


class IsolationScriptTests(unittest.TestCase):
    def _load_verify(self):
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts import verify_isolated_test_db as v

        return importlib.reload(v)

    def test_blocks_application_database_url(self):
        v = self._load_verify()
        old = os.environ.get("DATABASE_URL")
        old_e = os.environ.get("ORG_SCOPE_ENFORCEMENT")
        try:
            os.environ["DATABASE_URL"] = (
                "postgresql+psycopg2://pm_user:secret@localhost:5438/project_mgmt"
            )
            os.environ["ORG_SCOPE_ENFORCEMENT"] = "true"
            v = importlib.reload(v)
            self.assertNotEqual(v.main(), 0)
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old
            if old_e is None:
                os.environ.pop("ORG_SCOPE_ENFORCEMENT", None)
            else:
                os.environ["ORG_SCOPE_ENFORCEMENT"] = old_e

    def test_accepts_test_database_url(self):
        v = self._load_verify()
        old = os.environ.get("DATABASE_URL")
        old_e = os.environ.get("ORG_SCOPE_ENFORCEMENT")
        try:
            os.environ["DATABASE_URL"] = (
                "postgresql+psycopg2://pm_test_user:x@127.0.0.1:5439/project_mgmt_test"
            )
            os.environ["ORG_SCOPE_ENFORCEMENT"] = "true"
            v = importlib.reload(v)
            self.assertEqual(v.main(), 0)
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old
            if old_e is None:
                os.environ.pop("ORG_SCOPE_ENFORCEMENT", None)
            else:
                os.environ["ORG_SCOPE_ENFORCEMENT"] = old_e


class OwnershipOptionsAccessUnitTests(unittest.TestCase):
    @patch("app.routers.organization.user_has_permission")
    def test_projects_create_sufficient(self, perm):
        from app.routers import organization as org_router

        perm.side_effect = lambda db, user, key: key == "projects.create"
        user = MagicMock(role="Staff")
        self.assertIs(org_router._require_ownership_options_access(user, MagicMock()), user)

    @patch("app.routers.organization.user_has_permission", return_value=False)
    def test_view_only_rejected(self, _perm):
        from fastapi import HTTPException

        from app.routers import organization as org_router

        user = MagicMock(role="Staff")
        with self.assertRaises(HTTPException) as ctx:
            org_router._require_ownership_options_access(user, MagicMock())
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
