#!/usr/bin/env bash
# nRouter Feature-by-Feature Pure-Curl Health Check Shell Runner
#
# Runs feature-specific curl health checks against Gateway endpoints and parameters.
# Usage:
#   bash scripts/curl_health_checks/feature_curl.sh --self-test
#   bash scripts/curl_health_checks/feature_curl.sh --quick
#   bash scripts/curl_health_checks/feature_curl.sh
#   bash scripts/curl_health_checks/feature_curl.sh --step-summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export NROUTER_BASE_URL="${NROUTER_BASE_URL:-https://api.nrouter.ai/v1}"

# Check if running offline self-test
IS_SELF_TEST=false
for arg in "$@"; do
  if [[ "$arg" == "--self-test" ]]; then
    IS_SELF_TEST=true
    break
  fi
done

if [[ "$IS_SELF_TEST" != "true" && -z "${NROUTER_API_KEY:-}" ]]; then
  # Fall back to local admin test key if available
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

python3 "${SCRIPT_DIR}/feature_curl.py" "$@"
