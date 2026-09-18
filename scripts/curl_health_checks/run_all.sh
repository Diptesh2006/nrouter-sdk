#!/usr/bin/env bash
# nRouter Consolidated Pure-Curl Health Checks Runner Shell Script
#
# Runs all consolidated curl health checks (Models & Providers, Guardrails, Endpoints & Parameters).
# Usage:
#   bash scripts/curl_health_checks/run_all.sh --self-test
#   bash scripts/curl_health_checks/run_all.sh --quick
#   bash scripts/curl_health_checks/run_all.sh
#   bash scripts/curl_health_checks/run_all.sh --step-summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export NROUTER_BASE_URL="${NROUTER_BASE_URL:-https://api.nrouter.ai/v1}"

IS_SELF_TEST=false
for arg in "$@"; do
  if [[ "$arg" == "--self-test" ]]; then
    IS_SELF_TEST=true
    break
  fi
done

# The key comes from NROUTER_API_KEY and nowhere else — no credentials-file
# fallback, for the same reason the Python modules refuse one.
if [[ "$IS_SELF_TEST" != "true" && -z "${NROUTER_API_KEY:-}" ]]; then
  echo "Error: NROUTER_API_KEY environment variable is required." >&2
  echo "Provide NROUTER_API_KEY or use --self-test for offline validation." >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/run_all.py" "$@"
