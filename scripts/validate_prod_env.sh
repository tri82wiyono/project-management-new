#!/usr/bin/env bash
# Validate a production env file without printing secret values.
# Usage: validate_prod_env.sh /absolute/path/to/prod.env
set -euo pipefail

ENV_FILE="${1:-}"
if [[ -z "${ENV_FILE}" ]]; then
  echo "USAGE: $0 /absolute/path/to/prod.env" >&2
  exit 2
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "FAIL: env file missing: ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! -r "${ENV_FILE}" ]]; then
  echo "FAIL: env file not readable by current user" >&2
  exit 1
fi

# Permission guidance (warn only if we can stat mode)
if command -v stat >/dev/null 2>&1; then
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%OLp' "${ENV_FILE}" 2>/dev/null || echo '')"
  if [[ -n "${mode}" && "${mode}" != "600" && "${mode}" != "400" ]]; then
    echo "WARN: env file mode is ${mode}; prefer 600 or 400 (owner-only)" >&2
  fi
fi

required_keys=(
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  APP_URL
  APP_ENV
  SEED_DATA
  SECRET_KEY
  COOKIE_SECURE
  DEFAULT_ADMIN_EMAIL
  DEFAULT_ADMIN_PASSWORD
)

missing=0
weak=0

get_val() {
  local key="$1"
  # shellcheck disable=SC2002
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n1 || true)"
  if [[ -z "${line}" ]]; then
    echo ""
    return 0
  fi
  echo "${line#*=}"
}

for key in "${required_keys[@]}"; do
  val="$(get_val "${key}")"
  if [[ -z "${val}" ]]; then
    echo "FAIL: missing or empty required key: ${key}" >&2
    missing=1
    continue
  fi
  # Strength / anti-placeholder checks — never print the value
  case "${key}" in
    SECRET_KEY)
      if [[ "${#val}" -lt 32 ]]; then
        echo "FAIL: SECRET_KEY too short (minimum 32 characters)" >&2
        weak=1
      fi
      lowered="$(printf '%s' "${val}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lowered}" == *change_me* || "${lowered}" == *change-me* || "${lowered}" == ganti_* ]]; then
        echo "FAIL: SECRET_KEY looks like a placeholder" >&2
        weak=1
      fi
      ;;
    POSTGRES_PASSWORD|DEFAULT_ADMIN_PASSWORD)
      if [[ "${#val}" -lt 12 ]]; then
        echo "FAIL: ${key} too short (minimum 12 characters)" >&2
        weak=1
      fi
      lowered="$(printf '%s' "${val}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lowered}" == *change_me* || "${lowered}" == *change-me* || "${lowered}" == admin@12345 || "${lowered}" == ganti_* ]]; then
        echo "FAIL: ${key} looks like a placeholder or known-insecure default" >&2
        weak=1
      fi
      ;;
    SEED_DATA)
      lowered="$(printf '%s' "${val}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lowered}" != "false" && "${lowered}" != "0" && "${lowered}" != "no" ]]; then
        echo "FAIL: SEED_DATA must be false for production" >&2
        weak=1
      fi
      ;;
    APP_ENV)
      lowered="$(printf '%s' "${val}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lowered}" != "production" && "${lowered}" != "prod" ]]; then
        echo "FAIL: APP_ENV must be production (or prod) for production deploy" >&2
        weak=1
      fi
      ;;
    COOKIE_SECURE)
      lowered="$(printf '%s' "${val}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lowered}" != "true" && "${lowered}" != "1" && "${lowered}" != "yes" ]]; then
        echo "WARN: COOKIE_SECURE is not true — only acceptable behind intentional HTTP cutover" >&2
      fi
      ;;
  esac
done

# Optional but recommended for initial Phase 5 release
org="$(get_val ORG_SCOPE_ENFORCEMENT)"
if [[ -n "${org}" ]]; then
  lowered="$(printf '%s' "${org}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${lowered}" == "true" || "${lowered}" == "1" || "${lowered}" == "yes" ]]; then
    echo "WARN: ORG_SCOPE_ENFORCEMENT=true — ensure classification checklist is complete" >&2
  fi
fi

if [[ "${missing}" -ne 0 || "${weak}" -ne 0 ]]; then
  echo "RESULT: INVALID (secrets not printed)" >&2
  exit 1
fi

echo "RESULT: OK (required keys present; values not printed)"
echo "ENV_FILE_BASENAME=$(basename "${ENV_FILE}")"
