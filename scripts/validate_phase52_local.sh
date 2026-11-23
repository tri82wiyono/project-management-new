#!/usr/bin/env bash
# Disposable local validation for Phase 5.2 secure prod config.
# Uses fake credentials only. Does not touch production or trigger Actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

WORKDIR="${ROOT}/tmp/phase52-validation"
rm -rf "${WORKDIR}"
mkdir -p "${WORKDIR}"
chmod 700 "${WORKDIR}"

PASS=0
FAIL=0
note() { echo "NOTE: $*"; }
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

# --- 1) Missing env fails closed ---
if PM_ENV_FILE="${WORKDIR}/does-not-exist.env" \
  ./scripts/compose_prod.sh config >/dev/null 2>"${WORKDIR}/missing.err"; then
  fail "missing env should fail"
else
  pass "missing env fails safely"
fi

# --- 2) Incomplete env fails validation ---
cat >"${WORKDIR}/incomplete.env" <<'EOF'
POSTGRES_DB=project_mgmt
POSTGRES_USER=pm_user
EOF
chmod 600 "${WORKDIR}/incomplete.env"
if ./scripts/validate_prod_env.sh "${WORKDIR}/incomplete.env" >/dev/null 2>"${WORKDIR}/incomplete.err"; then
  fail "incomplete env should fail validate"
else
  pass "incomplete env rejected"
fi

# --- 3) Placeholder secrets rejected ---
cat >"${WORKDIR}/placeholder.env" <<'EOF'
POSTGRES_DB=project_mgmt
POSTGRES_USER=pm_user
POSTGRES_PASSWORD=change_me_strong_db_password
APP_URL=https://pm.example.com
APP_ENV=production
SEED_DATA=false
SECRET_KEY=change_me_to_a_long_random_secret_at_least_32_chars
COOKIE_SECURE=true
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=change_me_strong_admin_password
ORG_SCOPE_ENFORCEMENT=false
EOF
chmod 600 "${WORKDIR}/placeholder.env"
if ./scripts/validate_prod_env.sh "${WORKDIR}/placeholder.env" >/dev/null 2>"${WORKDIR}/placeholder.err"; then
  fail "placeholder secrets should fail"
else
  pass "placeholder secrets rejected"
fi

# --- 4) Valid disposable env accepted ---
# Fake values only — not production credentials
FAKE_SECRET="local-phase52-test-secret-key-not-for-prod-0001"
FAKE_DBPASS="LocalTestDbPass-phase52-99"
FAKE_ADMIN="LocalTestAdminPass-phase52"
cat >"${WORKDIR}/valid.env" <<EOF
POSTGRES_DB=project_mgmt
POSTGRES_USER=pm_user
POSTGRES_PASSWORD=${FAKE_DBPASS}
APP_URL=https://pm.example.test
APP_ENV=production
SEED_DATA=false
SECRET_KEY=${FAKE_SECRET}
COOKIE_SECURE=true
DEFAULT_ADMIN_EMAIL=admin@example.test
DEFAULT_ADMIN_PASSWORD=${FAKE_ADMIN}
DEFAULT_ADMIN_NAME=System Admin
ORG_SCOPE_ENFORCEMENT=false
APP_HOST_PORT=8891
EOF
chmod 600 "${WORKDIR}/valid.env"

if ./scripts/validate_prod_env.sh "${WORKDIR}/valid.env" >"${WORKDIR}/valid.out" 2>"${WORKDIR}/valid.err"; then
  pass "valid env accepted"
else
  fail "valid env rejected unexpectedly"
  cat "${WORKDIR}/valid.err" || true
fi

# Ensure validator output does not echo secret material
if grep -F "${FAKE_SECRET}" "${WORKDIR}/valid.out" "${WORKDIR}/valid.err" 2>/dev/null; then
  fail "SECRET_KEY leaked in validator output"
else
  pass "validator output has no SECRET_KEY value"
fi
if grep -F "${FAKE_DBPASS}" "${WORKDIR}/valid.out" "${WORKDIR}/valid.err" 2>/dev/null; then
  fail "DB password leaked in validator output"
else
  pass "validator output has no DB password"
fi

# --- 5) Compose config resolves with external env (requires docker) ---
if ! command -v docker >/dev/null 2>&1; then
  note "docker not available — skip compose config resolution"
else
  # Ensure external network exists for config/up compatibility without touching prod
  docker network inspect mismanajemen_default >/dev/null 2>&1 \
    || docker network create mismanajemen_default >/dev/null

  if PM_ENV_FILE="${WORKDIR}/valid.env" \
    ./scripts/compose_prod.sh config \
    >"${WORKDIR}/compose.resolved.yml" 2>"${WORKDIR}/compose.err"; then
    pass "compose config resolves with external env"
  else
    fail "compose config failed"
    cat "${WORKDIR}/compose.err" || true
  fi

  # Resolved file must not be committed; check it isn't empty and contains service names
  if grep -q 'pm_app\|container_name: pm_app' "${WORKDIR}/compose.resolved.yml" 2>/dev/null \
    || grep -q 'pm_app' "${WORKDIR}/compose.resolved.yml" 2>/dev/null; then
    pass "resolved compose references app service"
  else
    # compose config uses service key "app"
    if grep -q '^  app:' "${WORKDIR}/compose.resolved.yml"; then
      pass "resolved compose references app service"
    else
      fail "resolved compose missing app service"
    fi
  fi

  # Shell override must not win over host file (compose_prod.sh unsets critical keys)
  if ORG_SCOPE_ENFORCEMENT=true PM_ENV_FILE="${WORKDIR}/valid.env" \
    ./scripts/compose_prod.sh config 2>/dev/null \
    | awk '/ORG_SCOPE_ENFORCEMENT:/ {print $2; exit}' \
    | grep -qx '"false"\|false'; then
    pass "shell ORG_SCOPE override neutralized by compose_prod.sh"
  else
    fail "shell ORG_SCOPE_ENFORCEMENT=true overrode host file"
  fi

  # Missing --env-file / missing PM file should fail required env_file
  if docker compose -f docker-compose.prod.yml config >/dev/null 2>"${WORKDIR}/noenv.err"; then
    # May still fail on missing required interpolations — either way must not silently succeed with defaults
    fail "compose without env unexpectedly succeeded (insecure fallback risk)"
  else
    pass "compose without host env fails closed"
  fi
fi

# --- 6) Git history unchanged by this script; no commit ---
if git -C "${ROOT}" rev-parse HEAD >/dev/null; then
  pass "git repository intact"
fi

# Scrub disposable secrets from disk after checks (keep only pass/fail markers)
rm -f "${WORKDIR}/valid.env" "${WORKDIR}/compose.resolved.yml" \
  "${WORKDIR}/placeholder.env" "${WORKDIR}/incomplete.env"
printf 'phase52_local_validation completed\n' >"${WORKDIR}/RESULT.txt"
echo "PASS_COUNT=${PASS}" >>"${WORKDIR}/RESULT.txt"
echo "FAIL_COUNT=${FAIL}" >>"${WORKDIR}/RESULT.txt"

echo "==== SUMMARY PASS=${PASS} FAIL=${FAIL} ===="
if [[ "${FAIL}" -ne 0 ]]; then
  exit 1
fi
exit 0
