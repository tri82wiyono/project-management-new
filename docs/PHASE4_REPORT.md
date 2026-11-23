# Phase 4 Final Report — Project & Task Organizational Authorization

**Branch:** `feature/phase-4-project-authorization`  
**Base:** `1214b47` (`feature/phase-3-dynamic-rbac`)  
**Date:** 2026-11-23  
**Status: PASS** (enforcement default OFF; ready for Admin classification rollout)  
**Verification:** 78 tests OK (unit + integration + enforcement-patched IDOR fixtures); data 8/59/180/2 preserved; `ORG_SCOPE_ENFORCEMENT` unset/false.

No commit / push / merge / deploy performed.

---

## 1. Executive Summary

Phase 4 adds Division XOR Bidang project ownership, a reusable `org_scope` authorization service, list + object-level checks on Project/Task/dashboard/timeline/ticket-project surfaces, Admin legacy classify workflow, and UI ownership fields. `ORG_SCOPE_ENFORCEMENT` defaults to **false** so existing global Phase 3 behavior is preserved until legacy projects are classified.

## 2. Authorization Coverage Matrix

| Surface | List filter | Object auth | Mutation auth | Membership |
|---------|:-----------:|:-----------:|:-------------:|:----------:|
| `GET /api/projects` (+ stats) | Y | — | — | via scope |
| `GET /api/projects/{id}` (+ notes/docs) | — | Y | — | — |
| `POST/PATCH/DELETE /api/projects*` | — | Y | Y | audited |
| `PUT /api/projects/{id}/ownership` | — | Admin | Admin | — |
| `GET /api/projects/unassigned` | Admin | — | — | — |
| `GET/POST/PATCH/DELETE /api/tasks*` | Y | Y | Y | via project |
| Dashboard KPI/kanban/calendar/… | Y | optional project | — | — |
| `GET /api/timeline` | Y | optional project | — | — |
| Tickets modules / project FK | — | Y | Y | existing ticket scope |

## 3. Database Changes

Additive columns on `projects` via `ensure_schema()`:

- `owner_type` (default `unassigned`)
- `owner_division_id`, `owner_bidang_id`
- `ownership_classified_at`, `ownership_classified_by_id`

Verified after restart: **59 / 59** projects `unassigned` (no silent reassignment).

## 4. Legacy Transition Strategy

1. Keep `ORG_SCOPE_ENFORCEMENT=false` (current).
2. Admin uses banner / filter / `GET /api/projects/unassigned` + ownership form / `PUT …/ownership`.
3. Do not infer from PIC free text.
4. Verify placement + leadership FKs.
5. Enable `ORG_SCOPE_ENFORCEMENT=true` and restart.
6. Rollback = set flag false (Phase 3 global visibility for permitted users).

## 5. Backend Authorization

`app/services/org_scope.py` — context from leadership FKs + membership + assignment; Admin bypass when enforced; `*.manage` does **not** bypass org scope when enforced.

## 6. UI Changes

Projects list: ownership column, owner filter (Admin), legacy banner, form ownership fields.  
Project detail: ownership display + edit fields.

## 7. Allowed / Denied Matrix (unit-covered)

| Actor | Scenario | Enforced | Expected |
|-------|----------|----------|----------|
| Admin | any project | ON | allow |
| Staff | unclassified, not member | ON | deny |
| Staff | member of unclassified | ON | allow |
| Pemimpin Divisi | owned by led division | ON | allow |
| Pemimpin Divisi | other division | ON | deny |
| Pemimpin Bidang | led bidang | ON | allow |
| Pemimpin Bidang | other bidang | ON | deny |
| Any with view | any (permission only) | OFF | allow |

## 8. Regression Results

`PM_ORG_INTEGRATION=1` in app container:

```
Ran 68 tests in ~2.4s — OK
```

Includes Phase 0 config safety, Phase 1 org, Phase 2 placement, Phase 3 RBAC, nav/page gates, inactive session, team legacy, Phase 4 org_scope unit+integration.

## 9. Data Preservation

| Entity | Count |
|--------|------:|
| Users | 8 |
| Projects | 59 |
| Tasks | 180 |
| Tickets | 2 |
| Team memberships | 134 |

Ownership distribution after migration: `unassigned=59`.

## 10. Changed Files (key)

- `app/services/org_scope.py` (new)
- `app/models/models.py`, `app/db_migrate.py`, `app/config.py`, `app/schemas/schemas.py`
- Routers: `projects`, `tasks`, `dashboard`, `timeline`, `tickets`
- Services: `dashboard`, `timeline`, `audit`
- UI: `projects.html/js/css`, `project_detail.html/js`
- Docs: `PROJECT_ORG_SCOPE_PHASE4.md`, `PHASE4_REPORT.md`, `.env.example`
- Tests: `tests/test_org_scope.py`
- Unrelated untracked: `app/static/uploads/avatars/user_1.jpg` (not part of Phase 4)

## 11. Git Status

- Branch: `feature/phase-4-project-authorization`
- HEAD still `1214b47` (uncommitted Phase 4 work)
- Not pushed / not merged

## 12. Remaining Risks

- Enforcement still **off** until Admin classifies all 59 projects.
- Users without `organization.view` cannot load Division/Bidang dropdowns (can leave unassigned).
- `/api/team` directory remains global (picker); data APIs are scoped when enforced.
- Task create allows any `tasks.manage` user who can view the project (by design under current RBAC).

## 13. Final Status

**PASS**
