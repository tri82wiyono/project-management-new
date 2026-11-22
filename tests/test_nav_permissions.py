"""Test Group D — permission-aware navigation filtering (SEC-07)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.roles import DEFAULT_ROLES, PERMISSION_CATALOG
from app.templating import MOBILE_NAV_ITEMS, NAV_ITEMS, build_page_context, filter_nav_items


def _role_perms(code: str) -> set[str]:
    for role in DEFAULT_ROLES:
        if role["code"] == code:
            return set(role["permissions"])
    raise AssertionError(f"missing role {code}")


class NavFilterTests(unittest.TestCase):
    def test_member_hides_users_settings_audit(self):
        perms = _role_perms("Member")
        keys = {item["key"] for item in filter_nav_items(NAV_ITEMS, allowed_permissions=perms, authenticated=True)}
        self.assertIn("dashboard", keys)
        self.assertIn("projects", keys)
        self.assertIn("tasks", keys)
        self.assertIn("tickets", keys)
        self.assertNotIn("users", keys)
        self.assertNotIn("settings", keys)
        self.assertNotIn("audit", keys)

    def test_manager_sees_users_not_settings_or_audit(self):
        perms = _role_perms("Manager")
        keys = {item["key"] for item in filter_nav_items(NAV_ITEMS, allowed_permissions=perms, authenticated=True)}
        self.assertIn("users", keys)  # users.view
        self.assertNotIn("settings", keys)
        self.assertNotIn("audit", keys)

    def test_admin_catalog_sees_all_module_links(self):
        perms = {item["key"] for item in PERMISSION_CATALOG}
        keys = {item["key"] for item in filter_nav_items(NAV_ITEMS, allowed_permissions=perms, authenticated=True)}
        for expected in ("dashboard", "projects", "tickets", "tasks", "users", "audit", "settings", "timeline", "calendar"):
            self.assertIn(expected, keys)

    def test_unauthenticated_sees_no_nav(self):
        items = filter_nav_items(NAV_ITEMS, allowed_permissions=set(), authenticated=False)
        self.assertEqual(items, [])

    def test_mobile_account_visible_without_module_permission(self):
        items = filter_nav_items(MOBILE_NAV_ITEMS, allowed_permissions=set(), authenticated=True)
        keys = {item["key"] for item in items}
        self.assertIn("account", keys)
        self.assertNotIn("projects", keys)

    @patch("app.templating.get_identity_dict", return_value={})
    def test_build_page_context_filters_nav(self, _mock_identity):
        ctx = build_page_context(
            current_user={"id": 1, "name": "Mem", "role": "Member", "email": "m@x", "avatar_url": "/a"},
            allowed_permissions=_role_perms("Member"),
        )
        keys = {item["key"] for item in ctx["nav_items"]}
        self.assertNotIn("settings", keys)
        self.assertIn("tasks", keys)


class PagePermissionMapTests(unittest.TestCase):
    """Documented mapping sanity checks used by HTML route gates."""

    EXPECTED = {
        "/": ["dashboard.view"],
        "/projects": ["projects.view"],
        "/tasks": ["tasks.view"],
        "/tickets": ["tickets.view"],
        "/users": ["users.view", "users.manage"],
        "/settings": ["settings.manage"],
        "/audit": ["audit.view"],
        "/timeline": ["projects.view"],
        "/calendar": ["dashboard.view"],
    }

    def test_nav_permissions_align_with_page_map(self):
        by_href = {item["href"]: item.get("permissions") or [] for item in NAV_ITEMS}
        for path, perms in self.EXPECTED.items():
            if path in by_href:
                for perm in perms:
                    # page may accept any-of; nav lists the same family
                    self.assertTrue(
                        perm in by_href[path] or any(p.split(".")[0] == perm.split(".")[0] for p in by_href[path]),
                        msg=f"{path} nav perms {by_href[path]} vs page {perms}",
                    )


if __name__ == "__main__":
    unittest.main()
