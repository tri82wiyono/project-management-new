# Production preflight via GitHub Actions (read-only)

Use the existing Actions → VPS SSH secrets to collect Gate A–C evidence **without** deploying.

## Why not use “Deploy to VPS”?

`deploy.yml` `workflow_dispatch` runs `git reset --hard` + `compose up --build`. That **changes production**. Do **not** use it for Gate checks.

## Workflow

File: `.github/workflows/production-preflight.yml`  
Trigger: **`workflow_dispatch` only** (no `push`).

Checks (SSH on VPS, read-only):

- Deployed git SHA / branch
- `pm_app` / `pm_db` running
- `GET /api/health`
- Worktree `.env` vs `/etc/banksumut-pms/prod.env` (mode/owner only; flag values for `SEED_DATA` / `ORG_SCOPE_ENFORCEMENT` / `APP_ENV`)
- Docker volumes
- Backup directory inventory (names/sizes/dates only)
- Whether current compose already expects external env

Does **not**: restart, rebuild, migrate, rotate, write files, dump secrets, or touch DB data.

## How to run before the workflow exists on `main`

GitHub can dispatch a workflow from a **non-default** branch that contains the file. It is **not** available for manual run on `main` until that file is on `main` (or you always pass `--ref`).

### 1) Ensure the workflow is on the feature branch

Push (feature only — does **not** auto-deploy):

```bash
git push origin feature/phase-5-scope-readiness
```

### 2) Authenticate GitHub CLI (operator workstation)

```bash
gh auth login
# or: export GH_TOKEN=...  (repo scope: actions:write, actions:read)
```

### 3) Dispatch against the feature ref

```bash
gh workflow run production-preflight.yml \
  --ref feature/phase-5-scope-readiness \
  -f note='Gate A-C evidence'

gh run list --workflow=production-preflight.yml --limit 3
gh run watch
gh run view --log
```

UI alternative: Actions → **Production preflight (read-only)** → branch dropdown = `feature/phase-5-scope-readiness` → Run workflow.

If the UI only lists workflows present on the default branch, use `gh` with `--ref` as above, or merge **only after** Gates pass (prefer not merging a preflight-only change early if it risks a full Phase 5 deploy).

### 4) Interpret results

| Log marker | Meaning |
|------------|---------|
| `GATE_A3=PASS` / `GATE_A4=PASS` | Containers + health OK |
| `git_head=…` | Current production revision (expect `f8b1c41…` until Phase 5 deploy) |
| `host_env=absent` | Bootstrap `/etc/banksumut-pms/prod.env` still required (Gate C) |
| `host_env=present` + `host_env_mode_ok=YES` + flags false/production | Gate C metadata OK (still run validator after scripts land) |
| `GATE_B_RESTORE=NOT_VERIFIED_BY_THIS_JOB` | Admin must still perform/confirm isolated restore |
| `GATE_D_ROTATION=REQUIRES_ADMIN_APPROVAL…` | Rotation never done by this job |

### 5) Also verify last **Deploy** run (separate)

```bash
gh run list --workflow="Deploy to VPS" --limit 5
gh run view <id> --json conclusion,headSha,event,createdAt
```

Confirms whether Actions→VPS SSH still works for deploy jobs. Do **not** re-run Deploy for probing.

## Shortest path to finish Gate A–D

1. `gh auth login` (if needed).
2. Push this workflow on `feature/phase-5-scope-readiness` (if not already).
3. Run **Production preflight (read-only)** with `--ref feature/phase-5-scope-readiness`.
4. From the log, mark Gate A evidence; note whether host env exists.
5. **Administrator (authorized VPS session or break-glass):** execute checklist sections B→C→D from the operational checklist / `PRODUCTION_SECURE_CONFIG.md` (backup+restore, copy env to `/etc/banksumut-pms/prod.env`, rotate). Preflight job must **not** do these.
6. Re-run preflight to confirm `host_env=present`, flags, health still PASS.
7. Only then merge feature → `main` (triggers Deploy).

## Admin-only actions (approval required)

| Action | Why Actions preflight cannot do it |
|--------|-------------------------------------|
| Create `/etc/banksumut-pms/prod.env` | Would change VPS config |
| `pg_dump` / isolated restore | Writes backup; restore needs disposable DB |
| Rotate `SECRET_KEY` / DB / admin password | Changes secrets and may restart app |
| Merge to `main` | Triggers production deploy |
