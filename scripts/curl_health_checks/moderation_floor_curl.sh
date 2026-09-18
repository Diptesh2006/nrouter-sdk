#!/usr/bin/env bash
# nRouter Moderation Floor Pure-Curl Health Check Shell Runner
#
# Proves the platform moderation floor in BOTH directions: a hostile prompt is
# refused, and an ordinary prompt that merely contains personal data is SERVED.
#
# Usage:
#   bash scripts/curl_health_checks/moderation_floor_curl.sh --self-test
#   bash scripts/curl_health_checks/moderation_floor_curl.sh --quick
#   bash scripts/curl_health_checks/moderation_floor_curl.sh
#   bash scripts/curl_health_checks/moderation_floor_curl.sh --step-summary
#
# Optional plane configuration:
#   NROUTER_GUARDRAILS_DISABLED_API_KEY   a key whose organization turned its own
#                                         guardrails off (proves the platform
#                                         floor is not tenant-disableable)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export NROUTER_BASE_URL="${NROUTER_BASE_URL:-https://api.nrouter.ai/v1}"

IS_SELF_TEST=false
for arg in "$@"; do
  if [[ "$arg" == "--self-test" ]]; then
    IS_SELF_TEST=true
    break
  fi
done

if [[ "$IS_SELF_TEST" != "true" && -z "${NROUTER_API_KEY:-}" ]]; then
  TEST_ENV_FILE="${HOME}/.nrouter_admin_keys/nrouter-test/prod/credentials.env"
  if [[ -f "${TEST_ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${TEST_ENV_FILE}"
    export NROUTER_API_KEY="${NROUTER_TEST_API_KEY:-}"
  fi
fi

if [[ "$IS_SELF_TEST" != "true" && -z "${NROUTER_API_KEY:-}" ]]; then
  echo "Error: NROUTER_API_KEY environment variable is required." >&2
  echo "Provide NROUTER_API_KEY or use --self-test for offline validation." >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/moderation_floor_curl.py" "$@"
