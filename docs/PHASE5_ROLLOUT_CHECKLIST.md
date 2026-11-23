# Phase 5 — Organizational Scope Production Rollout Checklist

**Do not enable `ORG_SCOPE_ENFORCEMENT` in production until every item below is complete and approved.**

## Prerequisites

1. Phase 0–4 code deployed via approved release process (not this checklist alone).
2. Additive `ensure_schema()` ownership columns present and verified.
3. Backup of production database taken and restore drill noted.
4. Local/staging E2E with enforcement ON passed (`scripts/run_phase5_e2e.sh`).

## Staged sequence

1. **Migration verification** — confirm ownership columns/indexes/FKs on a staging clone.
2. **User placement readiness** — critical users have `primary_bidang_id` where required.
3. **Leadership assignment** — `divisions.leader_user_id` / `bidangs.leader_user_id` set from trusted records (not role names).
4. **Project ownership classification** — Admin classifies all legacy `unassigned` projects (no auto-infer from PIC).
5. **Role permission verification** — review Pemimpin/Staff keys; enable pending granular permissions only after enforcement plan is approved; never silent mass elevate.
6. **Cross-unit membership verification** — collaborative projects have explicit `team_members`.
7. **Enforcement-enabled integration tests** — run against isolated/staging DB only.
8. **Authorized production activation** — set `ORG_SCOPE_ENFORCEMENT=true` via approved change window; restart app.
9. **Post-activation monitoring** — 404/403 spikes, audit `project_ownership_classified`, support tickets.
10. **Recovery** — set `ORG_SCOPE_ENFORCEMENT=false` and restart to restore Phase 3 global visibility for permitted users (classification data retained).

## Production readiness vs local E2E

Isolated E2E PASS ≠ production READY.

Production additionally requires classification of existing projects, placement/leadership correctness, credential remediation, and authorized rollout approval.
