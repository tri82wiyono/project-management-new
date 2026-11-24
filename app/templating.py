from __future__ import annotations

from typing import Any

from app.services.identity import get_identity_dict


NAV_ITEMS = [
    {"key": "dashboard", "label": "Dashboard", "icon": "▦", "href": "/", "permissions": ["dashboard.view"]},
    {"key": "projects", "label": "Projects", "icon": "▣", "href": "/projects", "permissions": ["projects.view"]},
    {"key": "chat", "label": "Chat", "icon": "◌", "href": "/chat", "permissions": ["projects.view"]},
    {
        "key": "tickets",
        "label": "Ticket Management",
        "icon": "◫",
        "href": "/tickets",
        "permissions": ["tickets.view"],
    },
    {"key": "tasks", "label": "Tasks", "icon": "☰", "href": "/tasks", "permissions": ["tasks.view"]},
    {
        "key": "users",
        "label": "Users",
        "icon": "◎",
        "href": "/users",
        "permissions": ["users.view", "users.manage"],
    },
    {
        "key": "organization",
        "label": "Organisasi",
        "icon": "⬡",
        "href": "/organization",
        "permissions": ["organization.view", "organization.manage"],
    },
    {"key": "audit", "label": "Log Audit", "icon": "▥", "href": "/audit", "permissions": ["audit.view"]},
    {"key": "timeline", "label": "Timeline", "icon": "▤", "href": "/timeline", "permissions": ["projects.view"]},
    {"key": "team", "label": "Team", "icon": "◎", "href": "/#team", "permissions": ["dashboard.view"]},
    {"key": "reports", "label": "Reports", "icon": "◔", "href": "/#reports", "permissions": ["dashboard.view"]},
    {"key": "calendar", "label": "Calendar", "icon": "◔", "href": "/calendar", "permissions": ["dashboard.view"]},
    {
        "key": "settings",
        "label": "Settings",
        "icon": "⚙",
        "href": "/settings",
        "permissions": ["settings.manage"],
    },
]

MOBILE_NAV_ITEMS = [
    {"key": "dashboard", "label": "Home", "icon": "⌂", "href": "/", "permissions": ["dashboard.view"]},
    {"key": "projects", "label": "Project", "icon": "▣", "href": "/projects", "permissions": ["projects.view"]},
    {"key": "chat", "label": "Chat", "icon": "◌", "href": "/chat", "permissions": ["projects.view"]},
    {"key": "tasks", "label": "Task", "icon": "☰", "href": "/tasks", "permissions": ["tasks.view"]},
    # Account is available to any authenticated user (no module permission).
    {"key": "account", "label": "Account", "icon": "◎", "href": "/account", "permissions": []},
]


def filter_nav_items(
    items: list[dict[str, Any]],
    *,
    allowed_permissions: set[str] | None,
    authenticated: bool,
) -> list[dict[str, Any]]:
    """Return nav entries the user may see. Empty permissions = authenticated only."""
    if not authenticated:
        return []
    if allowed_permissions is None:
        # Unknown permission set — show nothing privileged (fail closed for module links).
        return [item for item in items if not item.get("permissions")]

    filtered: list[dict[str, Any]] = []
    for item in items:
        required = list(item.get("permissions") or [])
        if not required:
            filtered.append(item)
            continue
        if any(perm in allowed_permissions for perm in required):
            filtered.append(item)
    return filtered


def build_page_context(
    *,
    active_page: str = "dashboard",
    page_title: str = "Good day!",
    page_subtitle: str = "Plan, track, and deliver projects with your team.",
    current_user: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    allowed_permissions: set[str] | None = None,
) -> dict[str, Any]:
    identity = get_identity_dict()
    user = current_user or {
        "name": "Guest",
        "avatar_url": "https://api.dicebear.com/7.x/initials/svg?seed=Guest&backgroundColor=1f5fd6",
        "role": "Guest",
        "email": "",
    }
    authenticated = bool(user.get("id")) and (user.get("role") or "") != "Guest"
    # Admin bypass is enforced in user_has_permission; callers should pass the resolved set.
    perms = allowed_permissions if authenticated else set()
    context: dict[str, Any] = {
        "app_name": identity.get("app_name") or "Project Management System",
        "active_page": active_page,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "search_placeholder": "Search projects, tasks, people...",
        "footer_note": identity.get("footer_note") or "Built with FastAPI · PostgreSQL",
        "brand": {
            "mark": identity.get("brand_mark") or "PM",
            "name": identity.get("brand_name") or "PulseDesk",
            "tagline": identity.get("brand_tagline") or "Project OS",
        },
        "workspace": {
            "label": identity.get("workspace_label") or "Workspace",
            "name": identity.get("workspace_name") or "Fintech Delivery",
        },
        "organization_name": identity.get("organization_name") or "Bank Sumut",
        "current_user": user,
        "nav_items": filter_nav_items(NAV_ITEMS, allowed_permissions=perms, authenticated=authenticated),
        "mobile_nav_items": filter_nav_items(
            MOBILE_NAV_ITEMS, allowed_permissions=perms, authenticated=authenticated
        ),
    }
    if extra:
        context.update(extra)
    return context
