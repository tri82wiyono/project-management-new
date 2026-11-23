# Dynamic Role & Permission Management (Phase 3)

## Architecture

`User.role` (role code) → `roles.permissions` (JSON list) → effective permissions (legacy expansion) → backend checks.

Organizational placement (`users.primary_bidang_id`) and unit leadership are **not** authorization grants.

Organizational data scope for Projects/Tasks is **Phase 4**.

## Legacy compatibility

Stored broad keys remain valid. At check time they imply granular keys:

| Legacy key | Implies |
|------------|---------|
| `users.manage` | `users.view`, `users.create`, `users.update`, `users.deactivate`, `users.assign_role`, `users.assign_organization` |
| `roles.manage` | `roles.view` |
| `projects.manage` | `projects.view`, `projects.create`, `projects.update`, `projects.assign` (**not** `projects.delete`) |
| `tasks.manage` | `tasks.view`, `tasks.create`, `tasks.update`, `tasks.assign`, `tasks.complete`, `tasks.delete` |
| `tickets.manage` | `tickets.view` |
| `organization.manage` | `organization.view` |

Existing Admin / Manager / Member / custom roles are **not** auto-migrated to new business codes.

## Reserved permissions

- `projects.delete` — reserved; project delete remains Admin-role hard check (SEC-05).
- `projects.approve` — reserved; no approval workflow yet.

## Default business role templates

Seeded once (`create_only`); later Admin edits are preserved:

| Code | Conservative Phase 3 permissions |
|------|-----------------------------------|
| `PemimpinDivisi` | dashboard/org/projects/tasks/tickets **view** |
| `PemimpinBidang` | same view-oriented set |
| `Staff` | dashboard + projects/tasks/tickets **view** |

Broader project/task manage keys for leadership/staff are listed as `phase4_pending_permissions` until scope enforcement exists.

## Administrator protection

- Role `Admin` cannot be deactivated or deleted.
- Last active Administrator cannot be demoted or deactivated.
- Self demotion of sole Admin blocked.
- Admin role always retains `users.manage` + `roles.manage` when permissions are edited.
- `user_has_permission`: Admin role code bypass retained (SEC-06 recovery).

## Seed behavior

`ensure_default_roles()`:

- **Admin**: sync assignable catalog keys (recovery).
- **Manager/Member**: additive legacy keys only; never wipe customizations.
- **Business templates**: create if missing; never overwrite.

## No schema migration

Uses existing `roles` JSON permissions column. No production schema change required for Phase 3.
