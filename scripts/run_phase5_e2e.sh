#!/usr/bin/env bash
# Start isolated test Postgres and run Phase 5 E2E with enforcement ON.
# Does not modify .env, production, or the main app database volume (pm_pgdata).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.test.yml)
TEST_URL="postgresql+psycopg2://pm_test_user:pm_test_only_not_for_production@127.0.0.1:5439/project_mgmt_test"

echo "==> Starting isolated test Postgres (pm_db_test / pm_pgdata_test)"
"${COMPOSE[@]}" up -d db_test

echo "==> Waiting for health"
for i in $(seq 1 40); do
  if "${COMPOSE[@]}" exec -T db_test pg_isready -U pm_test_user -d project_mgmt_test >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
"${COMPOSE[@]}" exec -T db_test pg_isready -U pm_test_user -d project_mgmt_test

export DATABASE_URL="$TEST_URL"
export ORG_SCOPE_ENFORCEMENT=true
export SEED_DATA=false
export APP_ENV=test
export COOKIE_SECURE=false
# Disposable secrets — test only
export SECRET_KEY="phase5-test-secret-key-not-for-production-use-32"
export DEFAULT_ADMIN_EMAIL="admin.phase5@example.test"
export DEFAULT_ADMIN_PASSWORD="Phase5Admin@Test99"
export DEFAULT_ADMIN_NAME="Phase5 Test Admin"

echo "==> Verifying isolation markers"
python3 "$ROOT/scripts/verify_isolated_test_db.py"

echo "==> Running Phase 5 E2E (fresh Python process → correct engine bind)"
# Prefer host venv if present; otherwise run via disposable container on host network.
if command -v python3 >/dev/null && python3 -c "import fastapi,sqlalchemy,psycopg2" 2>/dev/null; then
  python3 -m unittest tests.test_phase5_e2e -v
else
  echo "Host Python deps missing — running via app image with host network"
  docker run --rm --network host \
    -e DATABASE_URL="$DATABASE_URL" \
    -e ORG_SCOPE_ENFORCEMENT=true \
    -e SEED_DATA=false \
    -e APP_ENV=test \
    -e COOKIE_SECURE=false \
    -e SECRET_KEY="$SECRET_KEY" \
    -e DEFAULT_ADMIN_EMAIL="$DEFAULT_ADMIN_EMAIL" \
    -e DEFAULT_ADMIN_PASSWORD="$DEFAULT_ADMIN_PASSWORD" \
    -e DEFAULT_ADMIN_NAME="$DEFAULT_ADMIN_NAME" \
    -v "$ROOT/app:/app/app" \
    -v "$ROOT/tests:/app/tests" \
    -v "$ROOT/scripts:/app/scripts" \
    -w /app \
    project-management-app:latest \
    python -m unittest tests.test_phase5_e2e -v
fi

echo "==> Phase 5 E2E finished"
