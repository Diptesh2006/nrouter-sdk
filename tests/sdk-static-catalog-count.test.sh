#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

hits=$(git grep -nEI '(^|[^[:alnum:]_])[0-9]{2,4}\+?[[:space:]]+(AI[[:space:]]+|LLM[[:space:]]+)?models([^[:alnum:]_]|$)' -- . || true)
if [ -n "$hits" ]; then
  echo "FAIL: SDK content hardcodes a current catalog size; use the live catalog instead:" >&2
  printf '%s\n' "$hits" >&2
  exit 1
fi

grep -q 'https://nrouter.ai/api/public/models' README.md || {
  echo "FAIL: SDK README must name the canonical live catalog authority" >&2
  exit 1
}

echo "SDK static catalog count guard: PASS"
