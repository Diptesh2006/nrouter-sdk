#!/usr/bin/env bash
# SDKCI-004 — first-party static analysis, mirroring the dead CodeQL gate.
#
# CodeQL runs on this repo as GitHub DEFAULT SETUP across nine languages, which
# means there is no workflow file to run locally and nothing to copy. Since the
# 2026-09-02 Actions billing lock every push to a WORLD-READABLE repo has had
# its static security analysis silently skipped, and it is the one dead gate
# with no local equivalent.
#
# `scripts/security-audit.sh` is NOT this. It audits DEPENDENCY advisories
# (osv-scanner / pip-audit / npm audit) — third-party CVEs. This scans the code
# we wrote. Both are needed and neither substitutes for the other.
#
# WHY p/default AND NOT p/ci. Measured 2026-09-04 against a planted probe
# (os.system("echo " + user_input), subprocess(..., shell=True), eval(...)):
#
#     p/ci              21 rules, 0 findings   <- would have shipped a gate
#                                                 that catches a textbook
#                                                 command injection: nothing
#     p/security-audit  79 rules, 2 findings
#     p/default        728 rules, 2 findings
#     r/python         371 rules, 4 findings
#
# p/ci is the ruleset the card suggested and it is the one that does not bite.
# p/default is multi-language, which matters here: this repo is nine SDKs.
#
# ⚠️ semgrep scans GIT-TRACKED FILES ONLY. An untracked probe is skipped
# entirely and the scan still exits 0 — which is how the first version of this
# measurement "proved" p/ci was fine. `--self-test` below plants a TRACKED
# probe for exactly that reason.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${NROUTER_SAST_CONFIG:-p/default}"
TARGETS=(sdks conformance tests scripts)
EXCLUDES=(--exclude=node_modules --exclude=target --exclude=build --exclude=.dart_tool --exclude=.venv)

scan() {
  semgrep --config="$CONFIG" --error --metrics=off "${EXCLUDES[@]}" "$@"
}

self_test() {
  # Prove the gate BITES before trusting a green run, and prove it is scanning
  # a non-empty target set — a clean scan over zero files exits 0 too.
  # NOT `local`: the EXIT trap runs after this function returns, so a local
  # would be unbound by the time cleanup reads it — which printed
  # "probe: unbound variable" after an otherwise green self-test.
  PROBE_REL="conformance/_sast_selftest_probe.py"
  local probe="$ROOT/$PROBE_REL" fails=0
  cleanup() {
    rm -f "$ROOT/$PROBE_REL"
    git -C "$ROOT" rm -q --cached "$PROBE_REL" 2>/dev/null || true
  }
  trap cleanup EXIT

  cat > "$probe" <<'PROBE'
import os
def run(user_input):
    os.system("echo " + user_input)
    eval(user_input)
PROBE
  # TRACKED, or semgrep skips it and the self-test proves nothing.
  git -C "$ROOT" add -N "$PROBE_REL" >/dev/null 2>&1

  if scan --quiet "$probe" >/dev/null 2>&1; then
    printf '  FAIL planted injection was NOT reported — the gate is decorative\n'
    fails=1
  else
    printf '  ok   planted injection is reported\n'
  fi

  local scanned
  scanned="$(semgrep --config="$CONFIG" --metrics=off "${EXCLUDES[@]}" "${TARGETS[@]/#/$ROOT/}" 2>&1 \
    | sed -n 's/.*Targets scanned: \([0-9][0-9]*\).*/\1/p' | head -1)"
  if [ "${scanned:-0}" -ge 100 ]; then
    printf '  ok   scans a real corpus (%s targets)\n' "$scanned"
  else
    printf '  FAIL scanned only %s target(s) — a clean scan over nothing exits 0\n' "${scanned:-0}"
    fails=1
  fi

  [ "$fails" -eq 0 ] && printf '\nok: SAST gate bites and is scanning\n' && return 0
  printf '\nFAIL: SAST gate did not prove itself\n'
  return 1
}

if [ "${1:-}" = "--self-test" ]; then
  command -v semgrep >/dev/null 2>&1 || { printf 'semgrep is absent\n'; exit 1; }
  self_test
  exit $?
fi

cd "$ROOT"
scan "${TARGETS[@]}"
