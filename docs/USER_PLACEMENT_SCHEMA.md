# User Placement Schema (Phase 2)

## Design

- **Single source of truth:** `users.primary_bidang_id` → `bidangs.id` (`ON DELETE SET NULL`).
- **Division is derived** from `bidangs.division_id`. Do not store a separate `division_id` on users.
- **Unassigned** users have `primary_bidang_id IS NULL` (allowed during migration).
- **Leadership ≠ placement.** `divisions.leader_user_id` / `bidangs.leader_user_id` remain independent metadata and do **not** grant RBAC permissions.
- Division leaders may hold organizational responsibility without a Bidang placement.
- Placement mutations **never** change `users.role`, permissions, project memberships, or task assignments.
- Placement mutations **never** silently clear leadership FKs. Transfers that conflict with active leadership require `acknowledge_leadership_conflict=true`.

## Concurrency

- `users.placement_version` increments on every real placement change.
- Clients may send `expected_version`; mismatch returns HTTP 409 (`placement_version_conflict`).
- Mutations use `SELECT … FOR UPDATE` on the user row inside a transaction with history insert.

## History

Table `user_placement_history` stores immutable assign / transfer / clear events with:

- previous and new Bidang/Division IDs
- name/code snapshots (readable after unit rename)
- actor, reason, timestamp, version
- whether leadership conflict was acknowledged

Identical re-assignments are idempotent (no new history row).

## Migration mechanism

Additive SQL in `app/db_migrate.py` → `ensure_schema()`:

- `ALTER TABLE users ADD COLUMN IF NOT EXISTS …`
- `CREATE TABLE IF NOT EXISTS user_placement_history …`

Existing users remain unassigned until an administrator places them.

### Apply (local)

```bash
docker compose -f docker-compose.yml up -d app
```

### Rollback (optional, destructive to placement only)

```sql
ALTER TABLE users DROP COLUMN IF EXISTS primary_bidang_id;
ALTER TABLE users DROP COLUMN IF EXISTS placement_version;
ALTER TABLE users DROP COLUMN IF EXISTS placement_updated_at;
DROP TABLE IF EXISTS user_placement_history;
```

This does not remove users, roles, projects, tasks, divisions, or bidangs.
