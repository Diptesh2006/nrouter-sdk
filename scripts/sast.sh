#!/usr/bin/env bash
# SDKCI-004 — first-party static analysis, mirroring the dead CodeQL gate.
#
# CodeQL runs on this repo as GitHub DEFAULT SETUP across nine languages, which
# means there is no workflow file to run locally and nothing to copy. While that
# hosted analysis is dormant it is the one gate with no local equivalent, so
# this script is the local stand-in that keeps first-party code scanned.
#
# `scripts/security-audit.sh` is NOT this. It audits DEPENDENCY advisories
# (osv-scanner / pip-audit / npm audit) — third-party CVEs. This scans the code
# we wrote. Both are needed and neither substitutes for the other.
#
# ─────────────────────────────────────────────────────────────────────────────
# THIS IS NOT PARITY WITH CodeQL. Read the coverage before trusting a green run.
# ─────────────────────────────────────────────────────────────────────────────
#
# Rule counts measured 2026-09-04, semgrep 1.155.0, `p/default` over this tree
# (194 git-tracked files). Re-derive with the scan header, never quote these:
#
#     language   semgrep rules   CodeQL covered it?   verdict
#     python              243    yes                  comparable
#     ts                  163    yes                  comparable
#     js                  153    yes                  comparable
#     java                118    yes (java-kotlin)    comparable
#     go                   84    yes                  comparable
#     kotlin               18    yes (java-kotlin)    THIN
#     rust                  4    yes                  THIN — but see below
#     swift                 2    yes                  THIN, effectively token
#     yaml/json/bash    35/4/4   `actions` only       different thing entirely
#
#   RUST is the one thin row that is actually covered: the Rust lane in
#   test-all.sh already runs `cargo clippy --all-targets --all-features
#   -- -D warnings`. Do not duplicate clippy here; that lane is the Rust gate.
#
#   SWIFT and KOTLIN are genuinely weaker than CodeQL was. Two rules is not a
#   Swift security review. Nothing local replaces that today — say so rather
#   than letting a green lane imply it.
#
#   NOT SCANNED BY ANYTHING, here or on CodeQL: `sdks/dart` and `sdks/r`.
#   semgrep p/default ships no Dart or R rules and CodeQL's nine languages
#   never included them either, so this is a pre-existing hole this script
#   does not widen and does not close.
#
#   `actions` (workflow analysis) is NOT mirrored. The yaml rules above are
#   generic; they are not CodeQL's Actions threat model.
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
#
# EXIT CODES — three states, deliberately distinct. semgrep itself uses 0 for
# "clean" and 1 for "findings", so ABSENCE must be neither, or "the tool is not
# installed" reads as "the code is clean". That conflation is the whole defect
# this card exists to fix.
#
#     0   scanned, no findings
#     1   scanned, FOUND something
#    78   semgrep is ABSENT — nothing was scanned. NOT a pass.
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${NROUTER_SAST_CONFIG:-p/default}"
TARGETS=(sdks conformance tests scripts)
EXCLUDES=(--exclude=node_modules --exclude=target --exclude=build --exclude=.dart_tool --exclude=.venv)

# Absence is reported LOUDLY and distinctly, with the command that fixes it.
# Without this the script died on `semgrep: command not found` with exit 127 —
# technically non-zero, but it names no remedy and reads as a broken script
# rather than an unrun gate.
need_semgrep() {
  command -v semgrep >/dev/null 2>&1 && return 0
  cat >&2 <<'ABSENT'
=====================================================================
SKIPPED — semgrep is NOT INSTALLED. NOTHING WAS SCANNED.
=====================================================================
This is NOT a pass. The first-party static-analysis gate did not run,
so no first-party code was analysed at all.

Install it:

  brew install semgrep                  # macOS
  python3 -m pip install --user semgrep  # any platform
  pipx install semgrep                   # isolated

Then re-run:

  scripts/sast.sh --self-test   # prove the gate bites
  scripts/sast.sh               # scan
=====================================================================
ABSENT
  exit 78
}

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
  need_semgrep
  self_test
  exit $?
fi

need_semgrep
cd "$ROOT"
scan "${TARGETS[@]}"
