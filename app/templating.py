from __future__ import annotations

from typing import Any

from app.services.identity import get_identity_dict


NAV_ITEMS = [
    {"key": "dashboard", "label": "Dashboard", "icon": "▦", "href": "/"},
    {"key": "projects", "label": "Projects", "icon": "▣", "href": "/projects"},
    {"key": "tickets", "label": "Ticket Management", "icon": "◫", "href": "/tickets"},
    {"key": "tasks", "label": "Tasks", "icon": "☰", "href": "/tasks"},
    {"key": "users", "label": "Users", "icon": "◎", "href": "/users"},
    {"key": "audit", "label": "Log Audit", "icon": "▥", "href": "/audit"},
    {"key": "timeline", "label": "Timeline", "icon": "▤", "href": "/timeline"},
    {"key": "team", "label": "Team", "icon": "◎", "href": "/#team"},
    {"key": "reports", "label": "Reports", "icon": "◔", "href": "/#reports"},
    {"key": "calendar", "label": "Calendar", "icon": "◔", "href": "/calendar"},
    {"key": "settings", "label": "Settings", "icon": "⚙", "href": "/settings"},
]

MOBILE_NAV_ITEMS = [
    {"key": "dashboard", "label": "Home", "icon": "⌂", "href": "/"},
    {"key": "projects", "label": "Project", "icon": "▣", "href": "/projects"},
    {"key": "tasks", "label": "Task", "icon": "☰", "href": "/tasks"},
    {"key": "account", "label": "Account", "icon": "◎", "href": "/account"},
]


def build_page_context(
    *,
    active_page: str = "dashboard",
    page_title: str = "Good day!",
    page_subtitle: str = "Plan, track, and deliver projects with your team.",
    current_user: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = get_identity_dict()
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
        "current_user": current_user
        or {
            "name": "Guest",
            "avatar_url": "https://api.dicebear.com/7.x/initials/svg?seed=Guest&backgroundColor=453a82",
            "role": "Guest",
            "email": "",
        },
        "nav_items": NAV_ITEMS,
        "mobile_nav_items": MOBILE_NAV_ITEMS,
    }
    if extra:
        context.update(extra)
    return context
