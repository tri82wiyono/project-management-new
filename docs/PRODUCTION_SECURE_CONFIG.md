# Production Secure Configuration & Deployment Preparation

Phase 5.2 design for Bank Sumut PMS. **Host-side steps require explicit administrator authorization.** This document must not contain real credentials.

## Canonical secret location

| Item | Value |
|------|--------|
| Host env file | `/etc/banksumut-pms/prod.env` |
| Permissions | **`0600` or `0400` only** — never world-/group-readable (`0644`/`0664` forbidden) |
| Ownership | Owner = account that runs deploy Compose (often `root`, or dedicated deploy user) |
| Directory | `/etc/banksumut-pms` mode `0700` |
| Override | `PM_ENV_FILE=/absolute/path` |
| Git worktree | Must **not** track or require `.env` |
| Compose | `docker compose --env-file "$PM_ENV_FILE" -f docker-compose.prod.yml …` |
| Helper | `scripts/compose_prod.sh` / `scripts/validate_prod_env.sh` |

### Least privilege for the deployment account

- Grant the deploy SSH user **read** access by making that user the **file owner** with mode `0600` (or `0400`).
- Do **not** “fix” access by chmod to `0644`/`0755` on `prod.env`.
- Do **not** add the env file to a shared group with broad membership unless that group is only the deploy principal.
- Docker Engine already needs privileges to run Compose; secrets stay host-local and are injected at runtime — they must not enter the image build context.
- Actions must not `chmod` the env file; the workflow only checks presence and validates keys.
- Deploy/`compose_prod.sh` **unset** critical process-env keys before Compose so a polluted SSH shell cannot override `/etc/banksumut-pms/prod.env` (Compose otherwise prefers process env over `--env-file`).

Persistent Docker volumes (`pm_pgdata`, `pm_uploads`, `pm_avatars`) are unchanged.

---

## Why this exists

1. `main` historically tracked `.env` (exposed secrets).
2. Phase 5 removes `.env` from Git.
3. Deploy uses `git reset --hard origin/main`, which **deletes** tracked files removed upstream — including worktree `.env`.
4. Secrets must therefore live **outside** the Git working tree **before** the first deploy of that revision.

---

## VPS administrator preparation runbook (before first untracked-`.env` deploy)

Do **not** stop or restart production until an authorized change window. Steps 1–7 are read-mostly / additive.

### 1. Identify current application configuration

```bash
APP_DIR=/opt/project-management-new
cd "$APP_DIR"
git rev-parse HEAD
git status -sb
# Locate candidates (do not cat secrets to shared logs)
ls -la .env /etc/banksumut-pms/prod.env 2>/dev/null || true
docker inspect pm_app --format '{{.Config.Env}}' >/dev/null  # existence only
```

### 2. Prepare secure configuration outside the Git tree

```bash
sudo mkdir -p /etc/banksumut-pms
sudo chmod 700 /etc/banksumut-pms

# If worktree .env is the current runtime source of truth:
sudo cp -a "$APP_DIR/.env" /etc/banksumut-pms/prod.env

# Or create from template on an admin workstation and install via secure channel:
# scp prod.env root@vps:/etc/banksumut-pms/prod.env
```

Ensure required keys exist (see `.env.example` and `scripts/validate_prod_env.sh`):  
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `APP_URL`, `APP_ENV=production`, `SEED_DATA=false`, `SECRET_KEY`, `COOKIE_SECURE`, `DEFAULT_ADMIN_EMAIL`, `DEFAULT_ADMIN_PASSWORD`, recommended `ORG_SCOPE_ENFORCEMENT=false`.

### 3. Ownership and permissions

```bash
# Replace DEPLOY_USER with the SSH account used by GitHub Actions (often root).
DEPLOY_USER="${DEPLOY_USER:-root}"
sudo chown "${DEPLOY_USER}:${DEPLOY_USER}" /etc/banksumut-pms/prod.env
sudo chmod 600 /etc/banksumut-pms/prod.env
sudo chmod 700 /etc/banksumut-pms
# Verify — expect 600/400 and deploy-user ownership only
sudo ls -la /etc/banksumut-pms/prod.env
```

### 4. Validate required variables (values not printed)

```bash
cd "$APP_DIR"
# After code containing scripts is present locally, or copy scripts first:
sudo PM_ENV_FILE=/etc/banksumut-pms/prod.env bash -c \
  './scripts/validate_prod_env.sh /etc/banksumut-pms/prod.env'
```

### 5. Ensure Docker Compose can consume the configuration

```bash
export PM_ENV_FILE=/etc/banksumut-pms/prod.env
# Discard stdout — interpolated output may contain secrets
docker compose --env-file "$PM_ENV_FILE" -f docker-compose.prod.yml config >/dev/null
echo "compose_config_ok=$?"
```

### 6. Verify readiness without stopping the running application

- Confirm `/etc/banksumut-pms/prod.env` exists and validates.
- Confirm `docker compose … config` succeeds.
- Confirm current containers still healthy: `curl -fsS http://127.0.0.1:8891/api/health`.
- **Do not** run `up --build` or restart until the authorized deploy window.

### 7. Preserve recovery information

```bash
sudo mkdir -p /root/pm-recovery
sudo chmod 700 /root/pm-recovery
# Timestamped copy of env (still secret — never commit / never attach to tickets)
sudo cp -a /etc/banksumut-pms/prod.env \
  "/root/pm-recovery/prod.env.$(date -u +%Y%m%dT%H%M%SZ)"
sudo chmod 600 /root/pm-recovery/prod.env.*
# Record revision and volume names only
{
  echo "app_dir=$APP_DIR"
  echo "git_rev=$(git -C "$APP_DIR" rev-parse HEAD)"
  echo "volumes=pm_pgdata,pm_uploads,pm_avatars"
  echo "env_file=/etc/banksumut-pms/prod.env"
} | sudo tee /root/pm-recovery/preflight-meta.txt >/dev/null
```

**Gate:** Host env file ready + validate OK + compose config OK **before** merging/pushing the revision that drops tracked `.env`.

---

## Credential rotation dependencies (authorized window only)

Distinguish:

| Credential | Role |
|------------|------|
| `DEFAULT_ADMIN_PASSWORD` | **Bootstrap only** — used at startup to create the admin user if missing. Changing it later does **not** change an existing user’s stored password hash. |
| Administrator account password | Stored as `users.password_hash`. Rotate via application password-change / admin reset, or authorized DB update of the hash — **not** by editing bootstrap env alone. |
| `SECRET_KEY` | Session signing. Rotation invalidates existing sessions/cookies. |
| `POSTGRES_PASSWORD` | DB role password. Must update Postgres **and** env file together; `DATABASE_URL` is composed from `POSTGRES_*` in Compose. |

### SECRET_KEY

1. Backup DB + recovery env copy.
2. Generate a new ≥32-char random secret offline.
3. Update `/etc/banksumut-pms/prod.env`.
4. Recreate/restart **app** only in the change window.
5. Expect all users to re-authenticate.

### PostgreSQL credentials

1. Backup with current credentials.
2. `ALTER USER … PASSWORD …` inside Postgres (authorized).
3. Update `POSTGRES_PASSWORD` in host env (and any explicit `DATABASE_URL` if used).
4. Recreate **app** (and **db** only if container env must refresh — prefer rolling carefully; data is in `pm_pgdata`).
5. Verify health and login.

### Administrator password

1. Prefer in-app change while logged in as that admin.
2. If bootstrap user was never created, set `DEFAULT_ADMIN_PASSWORD` before first create.
3. If account exists, env bootstrap password is ignored for login — rotate the **stored** password.
4. After historical exposure, assume compromise: rotate stored admin password **and** `SECRET_KEY` **and** DB password.

Never paste real values into Git, Issues, Actions logs, or this document.

---

## Database backup & recovery checklist

### Backup requirements

- Use `pg_dump` custom format (`-Fc`) from the running `pm_db` container or an authorized local socket.
- Include globals if roles matter (`pg_dumpall --roles-only`) when rotating roles.
- Store under a host path outside the git tree, e.g. `/var/backups/banksumut-pms/`, mode `0700`.
- Encrypt at rest if organizational policy requires (age/gpg) — keys not in git.

### Access protection

- Root or dedicated backup user only.
- No world-readable dumps.
- Do not commit dumps (`backups/` is gitignored).

### Restore validation (isolated)

1. Start disposable Postgres (separate volume / port).
2. `pg_restore` into empty DB.
3. Run app against restore with `SEED_DATA=false` and a **copy** of env pointing at the disposable DB.
4. Confirm schema (`ensure_schema` idempotent) and spot-check row counts.
5. Destroy disposable resources.

### Schema compatibility

- App applies additive `ensure_schema()` on startup.
- Restores from older dumps may need one app start to add columns.
- Do not drop volumes as a “rollback”.

### Recovery ownership

- Named production owner + deputy.
- Backup success notification / last-good timestamp recorded in ops notes (no secrets).

### Rollback limitations

- Git/Actions deploy has **no** automatic image rollback.
- Rollback = redeploy previous git SHA **with** intact host env + volumes.
- `git reset --hard` never restores deleted Docker volumes.
- Schema DDL is generally forward-only; rolling back code may leave extra columns (usually safe).

---

## Related files

- `docker-compose.prod.yml` — external `PM_ENV_FILE`, required interpolations
- `.github/workflows/deploy.yml` — preflight, validate, compose config, health, revision logging
- `scripts/validate_prod_env.sh` / `scripts/compose_prod.sh`
- `docs/PHASE5_ROLLOUT_CHECKLIST.md` — org-scope enablement (keep `ORG_SCOPE_ENFORCEMENT=false` for initial release)
- `docs/CICD.md` — SSH/Actions secrets setup (host keys, not app DB passwords)
