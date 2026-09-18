#!/usr/bin/env bash
# nRouter Per-Request Guardrails Pure-Curl Health Check Shell Runner
#
# Usage:
#   bash scripts/curl_health_checks/guardrails_request_curl.sh --self-test
#   bash scripts/curl_health_checks/guardrails_request_curl.sh --quick
#   bash scripts/curl_health_checks/guardrails_request_curl.sh
#   bash scripts/curl_health_checks/guardrails_request_curl.sh --step-summary
#
# Optional plane configuration (checks that need it report NOT-CONFIGURED without it):
#   NROUTER_GUARDRAIL_ID, NROUTER_GUARDRAIL_BLOCK_KEYWORD,
#   NROUTER_TENANT_BLOCK_KEYWORD, NROUTER_FOREIGN_GUARDRAIL_ID

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

# The key comes from NROUTER_API_KEY only. This wrapper deliberately does not
# read a credential out of a file on disk: the repository is public, a hardcoded
# path leaks an internal convention, and a fallback would send whatever key it
# found to whatever NROUTER_BASE_URL happens to be set to.
if [[ "$IS_SELF_TEST" != "true" && -z "${NROUTER_API_KEY:-}" ]]; then
  echo "NOT-CONFIGURED: NROUTER_API_KEY is not set, so no live check can run." >&2
  echo "  export NROUTER_API_KEY=sk-nrouter-...   # your own virtual key" >&2
  echo "  ...or pass --self-test for the offline verification, which needs no key." >&2
  exit 2
fi

python3 "${SCRIPT_DIR}/guardrails_request_curl.py" "$@"
