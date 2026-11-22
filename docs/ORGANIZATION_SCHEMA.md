# Organization Schema (Phase 1)

## Design

- `divisions` — organizational Divisions (units), not roles.
- `bidangs` — Bidang under a Division (`division_id` FK, `ON DELETE RESTRICT`).
- Leadership uses nullable `leader_user_id` → `users.id` (`ON DELETE SET NULL`).
- One active leader per unit is enforced by a single FK column (not a multi-row assignment table).
- Bidang `code` is unique **within** its parent Division (`uq_bidangs_division_code`).
- Division `code` is globally unique.
- A Division may exist with zero Bidang (draft/setup-friendly).
- Leadership assignment does **not** change RBAC permissions (Phase 4 will add data scope).

## Migration mechanism

Additive SQL in `app/db_migrate.py` → `ensure_schema()` (`CREATE TABLE IF NOT EXISTS`).

Also registered via SQLAlchemy models so `Base.metadata.create_all()` creates tables on empty databases.

### Apply (local)

Restart the app container so lifespan runs `ensure_schema()`:

```bash
docker compose -f docker-compose.yml up -d app
```

### Recovery

1. Restore DB dump from `backups/` if needed.
2. Re-run app startup (`ensure_schema` is idempotent).
3. Do **not** drop `users`, `projects`, or `tasks`.

### Rollback (optional, destructive to org master only)

```sql
DROP TABLE IF EXISTS bidangs;
DROP TABLE IF EXISTS divisions;
```

This does not remove users/projects/tasks.
