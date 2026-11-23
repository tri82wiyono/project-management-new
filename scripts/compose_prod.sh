#!/usr/bin/env bash
# Thin wrapper: always pass the host-local env file to Docker Compose.
# Usage:
#   PM_ENV_FILE=/etc/banksumut-pms/prod.env ./scripts/compose_prod.sh config
#   PM_ENV_FILE=... ./scripts/compose_prod.sh up -d --build app
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PM_ENV_FILE="${PM_ENV_FILE:-/etc/banksumut-pms/prod.env}"
export PM_ENV_FILE

if [[ ! -f "${PM_ENV_FILE}" ]]; then
  echo "FAIL: PM_ENV_FILE missing: ${PM_ENV_FILE}" >&2
  echo "Prepare host-local secrets before compose (see docs/PRODUCTION_SECURE_CONFIG.md)." >&2
  exit 1
fi

"${ROOT}/scripts/validate_prod_env.sh" "${PM_ENV_FILE}"

# Compose prefers process environment over --env-file for interpolation.
# Clear critical keys so the host-local file is authoritative (no silent shell override).
# Values are never printed.
for key in \
  ORG_SCOPE_ENFORCEMENT SEED_DATA APP_ENV COOKIE_SECURE SECRET_KEY \
  POSTGRES_PASSWORD POSTGRES_USER POSTGRES_DB APP_URL APP_HOST_PORT \
  DEFAULT_ADMIN_EMAIL DEFAULT_ADMIN_PASSWORD DEFAULT_ADMIN_NAME DATABASE_URL
do
  unset "${key}" 2>/dev/null || true
done

exec docker compose --env-file "${PM_ENV_FILE}" -f docker-compose.prod.yml "$@"
