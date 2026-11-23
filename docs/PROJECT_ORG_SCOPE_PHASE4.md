# Project & Task Organizational Authorization (Phase 4)

## Objective

Enforce Project/Task access using:

1. Action permission (Phase 3 RBAC)
2. Organizational ownership (Division XOR Bidang)
3. Project membership (`team_members`)
4. Task assignment (`task_assignees` / legacy `assignee_id`)
5. Leadership metadata (`divisions.leader_user_id`, `bidangs.leader_user_id`)

Role **names** are never proof of organizational ownership.

## Schema (additive)

| Column | Purpose |
|--------|---------|
| `projects.owner_type` | `unassigned` \| `division` \| `bidang` |
| `projects.owner_division_id` | FK divisions (nullable) |
| `projects.owner_bidang_id` | FK bidangs (nullable) |
| `projects.ownership_classified_at` | when ownership last set |
| `projects.ownership_classified_by_id` | actor user id |

Invariant (application-enforced for new assignments):

- `unassigned` → both FKs null
- `division` → division set, bidang null
- `bidang` → bidang set; parent division stored for Divisi-leader queries

Legacy rows remain `unassigned`. No automatic ownership inference from PIC text.

## Feature flag

`ORG_SCOPE_ENFORCEMENT` / `Settings.org_scope_enforcement` (default **false**).

| State | Behavior |
|-------|----------|
| Off | Phase 3 permission-only global visibility (safe rollout) |
| On | List filters + object checks; unclassified projects visible only to Admin and explicit members/assignees |

The flag does **not** auto-disable in production. Enable only after classifying legacy projects and verifying placement/leadership readiness.

## Backend service

`app/services/org_scope.py` — reusable helpers:

- `load_user_org_context`
- `can_view_project` / `can_manage_project` / `can_view_task` / `can_manage_task`
- `project_visibility_filter` / `task_visibility_filter`
- `validate_and_normalize_ownership` / `apply_project_ownership`
- `scope_status`

Wired into: projects, tasks, dashboard, timeline, ticket project validation / modules.

## Legacy transition

1. Preserve all Projects / Tasks / memberships.
2. Admin lists unclassified via `GET /api/projects/unassigned` and UI banner/filter.
3. Classify via create/update ownership fields or `PUT /api/projects/{id}/ownership`.
4. Verify placement + leadership FKs.
5. Set `ORG_SCOPE_ENFORCEMENT=true` and restart app.
6. Confirm Staff without membership cannot see unclassified / out-of-scope projects.

## Rollback

1. Set `ORG_SCOPE_ENFORCEMENT=false` and restart (restores Phase 3 global visibility for permitted users).
2. Optional destructive column drop only after backup (not recommended while data is live):

```sql
ALTER TABLE projects DROP COLUMN IF EXISTS ownership_classified_by_id;
ALTER TABLE projects DROP COLUMN IF EXISTS ownership_classified_at;
ALTER TABLE projects DROP COLUMN IF EXISTS owner_bidang_id;
ALTER TABLE projects DROP COLUMN IF EXISTS owner_division_id;
ALTER TABLE projects DROP COLUMN IF EXISTS owner_type;
```

## Migration

Applied by `ensure_schema()` on app startup (`app/db_migrate.py`). Additive `ALTER TABLE … IF NOT EXISTS` only.
