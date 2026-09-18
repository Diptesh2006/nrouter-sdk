#!/usr/bin/env bash
# nRouter Guardrails Pure-Curl Health Check Shell Runner
#
# Runs curl-based guardrail health checks against the Gateway.
# Usage:
#   bash scripts/curl_health_checks/guardrail_curl.sh --self-test
#   bash scripts/curl_health_checks/guardrail_curl.sh --quick
#   bash scripts/curl_health_checks/guardrail_curl.sh
#   bash scripts/curl_health_checks/guardrail_curl.sh --step-summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export NROUTER_BASE_URL="${NROUTER_BASE_URL:-https://api.nrouter.ai/v1}"
export NROUTER_HEALTH_GUARDRAIL_ROUTE="${NROUTER_HEALTH_GUARDRAIL_ROUTE:-/messages}"
export NROUTER_HEALTH_GUARDRAIL_MODEL="${NROUTER_HEALTH_GUARDRAIL_MODEL:-claude-haiku-4-5-20251001}"

# Check if running offline self-test
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

python3 "${SCRIPT_DIR}/guardrail_curl.py" "$@"
