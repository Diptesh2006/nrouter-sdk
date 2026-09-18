#!/usr/bin/env bash
# nRouter Rate Limit Pure-Curl Health Check Shell Runner
#
# Usage:
#   bash scripts/curl_health_checks/rate_limit_curl.sh --self-test
#   bash scripts/curl_health_checks/rate_limit_curl.sh --quick
#   bash scripts/curl_health_checks/rate_limit_curl.sh
#   bash scripts/curl_health_checks/rate_limit_curl.sh --step-summary
#
# This module sends a deliberate burst against your own key. Run it against a
# key you are willing to rate limit.
#
# Optional plane configuration:
#   NROUTER_DEPLETED_API_KEY   a key whose budget is exhausted (proves the 402
#                              names its limit source)

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

python3 "${SCRIPT_DIR}/rate_limit_curl.py" "$@"
