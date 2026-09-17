#!/usr/bin/env bash
# nRouter Pure-Curl Health Checks Shell Runner
#
# Runs all curl-based health checks against the Gateway.
# Usage:
#   bash scripts/curl_health_checks.sh
#   bash scripts/curl_health_checks.sh --output-dir dist/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export NROUTER_BASE_URL="${NROUTER_BASE_URL:-https://api.nrouter.ai/v1}"

if [[ -z "${NROUTER_API_KEY:-}" ]]; then
  # Fall back to local admin test key if available
  TEST_ENV_FILE="${HOME}/.nrouter_admin_keys/nrouter-test/prod/credentials.env"
  if [[ -f "${TEST_ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${TEST_ENV_FILE}"
    export NROUTER_API_KEY="${NROUTER_TEST_API_KEY:-}"
  fi
fi

if [[ -z "${NROUTER_API_KEY:-}" ]]; then
  echo "Error: NROUTER_API_KEY environment variable is required." >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/curl_health_checks.py" "$@"
