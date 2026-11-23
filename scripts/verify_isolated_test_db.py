#!/usr/bin/env python3
"""Refuse to proceed unless DATABASE_URL is the Phase 5 isolated test database."""

from __future__ import annotations

import os
import sys


REQUIRED_MARKERS = (
    "project_mgmt_test",
    "pm_test_user",
)


FORBIDDEN_MARKERS = (
    "project_mgmt@",  # default app DB name without _test
    "@db:5432/project_mgmt",
    "pm_user:",
)


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("BLOCKED: DATABASE_URL is empty", file=sys.stderr)
        return 2
    lowered = url.lower()
    for bad in FORBIDDEN_MARKERS:
        # Allow project_mgmt_test; block bare project_mgmt path endings
        if bad == "project_mgmt@" and "project_mgmt_test" in lowered:
            continue
        if bad in lowered and "project_mgmt_test" not in lowered:
            print(f"BLOCKED: DATABASE_URL looks like app/prod DB ({bad})", file=sys.stderr)
            return 2
    for marker in REQUIRED_MARKERS:
        if marker not in lowered:
            print(f"BLOCKED: DATABASE_URL missing required marker {marker!r}", file=sys.stderr)
            return 2
    if os.environ.get("ORG_SCOPE_ENFORCEMENT", "").lower() not in {"1", "true", "yes"}:
        print("BLOCKED: ORG_SCOPE_ENFORCEMENT must be true for Phase 5 E2E", file=sys.stderr)
        return 2
    print("OK: isolated test database identity verified")
    print(f"DATABASE_URL host markers present; ORG_SCOPE_ENFORCEMENT=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
