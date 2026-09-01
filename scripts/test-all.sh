#!/usr/bin/env bash
# One local release gate for the ten SDKs, run as INDEPENDENT LANES.
#
# Live tests remain opt-in because they spend credits; set NROUTER_LIVE=1 only
# with a local/stage gateway and a key.
#
#   scripts/test-all.sh                     # run every lane the machine can run
#   NROUTER_REQUIRE_ALL=1 scripts/test-all.sh   # a skipped lane is also a failure
#   scripts/test-all.sh --self-test         # prove the engine's own honesty
#
# ---------------------------------------------------------------------------
# WHY LANES, AND WHY THE EXIT CODE IS THE POINT
# ---------------------------------------------------------------------------
#
# This script used to be one `set -e` straight line behind an all-or-nothing
# preflight: `need` exited 78 on the FIRST tool it could not find, so a machine
# without Dart learned nothing about its Go, Rust or Python SDKs. One absent
# toolchain blocked all ten lanes.
#
# It also invoked the Python suites while installing nothing, so on a clean
# checkout `tests/test_sdk_contract.py` died in COLLECTION at
# `ModuleNotFoundError: httpx2` — three steps after conformance and the security
# audit had already printed green. Every spec assertion in that module was a
# DEAD GATE, and it read like a test failure rather than a missing dependency.
#
# The contract now:
#
#   PASSED   the lane ran and its commands succeeded
#   FAILED   the lane ran and something in it returned non-zero  -> EXIT 1
#   SKIPPED  a prerequisite is absent, so the lane never executed -> named, loud,
#            and NEVER counted as a pass
#
# A skip does not fail the run by default, because blocking nine working lanes on
# one absent compiler is the defect this rewrite removes. `NROUTER_REQUIRE_ALL=1`
# is the release posture: there, a lane that did not run is not evidence.
#
# ---------------------------------------------------------------------------
# THE TRAP THIS FILE EXISTS TO AVOID: A GATE THAT EXITS 0 WITHOUT RUNNING
# ---------------------------------------------------------------------------
#
# MEASURED on this machine's /bin/bash 3.2.57, which is the shell that matters:
#
#     f() { echo one; false; echo TWO; }
#     rc=0; ( set -e; f ) || rc=$?     # prints TWO, and rc is 0
#     if ( set -e; f ); then ... fi    # prints TWO, and takes the THEN branch
#
# POSIX disables errexit inside any compound command whose status is being
# TESTED — the left side of `||`, an `if` condition, a `&&` chain. So the two
# obvious ways to run a lane and capture its result are exactly the two ways to
# make a failing lane report success. That is not theoretical: this workspace
# already ships a runner that prints "1 of 3 lanes FAILED" and exits 0, so
# anything gating on it is not gated.
#
# The fix here is that a lane body runs in a SEPARATE `bash -c` PROCESS with its
# own `set -euo pipefail`, and its status is captured on the FOLLOWING line
# rather than in a condition. A child process always honours its own errexit;
# the suppression rule cannot reach across the fork. Lane bodies are ALSO
# `&&`-chained, so the lane still fails correctly even if someone later
# reintroduces a subshell. Both belts are deliberate; do not remove either.
#
# `run_lane` therefore ALWAYS returns 0 and records into counters. The only
# thing that decides this script's exit status is `summary`.
#
# Regression gate: `scripts/test-all.sh --self-test` drives THESE functions with
# a synthetic pass, a synthetic failure and a synthetic missing prerequisite,
# and asserts both the counts and the exit code. It shares the engine with the
# real run, so it cannot drift from it.

set -uo pipefail
# NOTE: deliberately no `-e`. This driver's whole job is to continue past a
# failing lane. Errexit belongs INSIDE each lane, and each lane gets a real one.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT

REQUIRE_ALL="${NROUTER_REQUIRE_ALL:-0}"

PASSED=0
FAILED=0
SKIPPED=0
# Newline-delimited strings, NOT arrays: under `set -u`, bash 3.2 treats
# "${EMPTY[@]}" as an unbound variable and aborts the script. Measured, not
# assumed. A report that kills the reporter is worse than no report.
FAILED_LANES=""
SKIPPED_LANES=""

step() { printf '\n== %s ==\n' "$1"; }

# ---------------------------------------------------------------------------
# Prerequisite probes
# ---------------------------------------------------------------------------

# `have <requirement>` — true when the lane can run.
#
#   python       PYTHON_BIN resolved to a usable interpreter
#   py:<module>  the module imports under $PYTHON_BIN
#   pysdk        `nroutersdk` imports AND resolves to THIS checkout
#   jre          a Java runtime that actually starts
#   android      the Android SDK was located during preflight
#   <name>       an executable on PATH
have() {
  case "$1" in
    python)
      [ -n "${PYTHON_BIN:-}" ] && [ -x "$PYTHON_BIN" ]
      ;;
    py:*)
      [ -n "${PYTHON_BIN:-}" ] || return 1
      "$PYTHON_BIN" -c "import ${1#py:}" >/dev/null 2>&1
      ;;
    pysdk)
      # IDENTITY, not merely presence. A previously released `nrouter-sdk` from
      # PyPI imports perfectly and is not this checkout, so the contract tests
      # would compare the spec against a version nobody is editing — green, and
      # measuring the wrong tree.
      [ -n "${PYTHON_BIN:-}" ] || return 1
      local at
      at="$("$PYTHON_BIN" -c 'import nroutersdk,os;print(os.path.dirname(os.path.dirname(os.path.abspath(nroutersdk.__file__))))' 2>/dev/null)" || return 1
      [ "$at" = "$ROOT/sdks/python" ]
      ;;
    jre)
      # `command -v java` is a FALSE POSITIVE on macOS: /usr/bin/java is a stub
      # that exists with no JDK installed and answers "Unable to locate a Java
      # Runtime". Measured on this machine. Start it instead.
      if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        "$JAVA_HOME/bin/java" -version >/dev/null 2>&1
      else
        command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1
      fi
      ;;
    android)
      [ -n "${ANDROID_HOME:-}" ]
      ;;
    *)
      command -v "$1" >/dev/null 2>&1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# The lane engine
# ---------------------------------------------------------------------------

# run_lane <name> <requirements|-> <body>
#
# Always returns 0. It records; `summary` judges.
run_lane() {
  local name="$1" reqs="$2" body="$3"
  local req missing=""

  if [ "$reqs" != "-" ]; then
    for req in $reqs; do
      have "$req" || missing="$missing $req"
    done
  fi

  if [ -n "$missing" ]; then
    SKIPPED=$((SKIPPED + 1))
    SKIPPED_LANES="${SKIPPED_LANES}${name}|missing:${missing}
"
    printf '\n== %s ==\n' "$name"
    printf 'SKIPPED: prerequisite absent —%s\n' "$missing"
    printf '         This lane did NOT run. It is not a pass.\n'
    return 0
  fi

  printf '\n== %s ==\n' "$name"
  local status
  # The fork is load-bearing — see the header. `set -e` inside a child process
  # is honoured no matter what context the parent captured it from, and the
  # status is read on the NEXT line, never inside a condition.
  bash -c "set -euo pipefail; $body"
  status=$?

  if [ "$status" -eq 0 ]; then
    PASSED=$((PASSED + 1))
    printf '\nPASSED: %s\n' "$name"
  else
    FAILED=$((FAILED + 1))
    FAILED_LANES="${FAILED_LANES}${name}|exit ${status}
"
    printf '\nFAILED: %s (exit %s)\n' "$name" "$status"
  fi
  return 0
}

# summary — prints the verdict and RETURNS the script's exit status.
summary() {
  local total=$((PASSED + FAILED + SKIPPED))
  printf '\n=====================================================\n'
  printf 'SDK release gate — %s lanes\n' "$total"
  printf '=====================================================\n'
  printf '  PASSED   %s\n' "$PASSED"
  printf '  FAILED   %s\n' "$FAILED"
  printf '  SKIPPED  %s   (prerequisite absent — NOT a pass)\n' "$SKIPPED"

  if [ -n "$FAILED_LANES" ]; then
    printf '\nFAILED lanes:\n'
    printf '%s' "$FAILED_LANES" | while IFS='|' read -r n why; do
      [ -n "$n" ] && printf '  - %-28s %s\n' "$n" "$why"
    done
  fi

  if [ -n "$SKIPPED_LANES" ]; then
    printf '\nSKIPPED lanes (never executed):\n'
    printf '%s' "$SKIPPED_LANES" | while IFS='|' read -r n why; do
      [ -n "$n" ] && printf '  - %-28s %s\n' "$n" "$why"
    done
    printf '\nPython prerequisites, including the SDK itself, install in one step:\n'
    printf "  %s -m pip install -e '%s/sdks/python[dev]'\n" "${PYTHON_BIN:-python3}" "$ROOT"
    printf '\nOr without touching that interpreter:\n'
    printf '  python3 -m venv .venv && . .venv/bin/activate \\\n'
    printf "    && pip install -e 'sdks/python[dev]' \\\\\n"
    printf '    && PYTHON_BIN=$(command -v python) scripts/test-all.sh\n'
  fi

  if [ "$FAILED" -ne 0 ]; then
    printf '\nRESULT: FAILED — %s lane(s) returned non-zero.\n' "$FAILED"
    return 1
  fi
  if [ "$SKIPPED" -ne 0 ] && [ "$REQUIRE_ALL" = "1" ]; then
    printf '\nRESULT: INCOMPLETE — NROUTER_REQUIRE_ALL=1 and %s lane(s) never ran.\n' "$SKIPPED"
    return 1
  fi
  if [ "$SKIPPED" -ne 0 ]; then
    printf '\nRESULT: PASSED with %s lane(s) SKIPPED — this is NOT full release\n' "$SKIPPED"
    printf '        evidence. Re-run with NROUTER_REQUIRE_ALL=1 to require them.\n'
    return 0
  fi
  printf '\nRESULT: PASSED — all %s lanes ran and succeeded.\n' "$PASSED"
  return 0
}

# ---------------------------------------------------------------------------
# --self-test: mutation-proof the engine, using the engine
# ---------------------------------------------------------------------------
#
# Three synthetic lanes exercise the three outcomes, then the counters and the
# exit status of `summary` are asserted. If someone reintroduces the
# errexit-suppression bug, or makes a skip count as a pass, this goes red.
self_test() {
  local fails=0
  assert_eq() {
    if [ "$2" = "$3" ]; then
      printf '  ok   %s = %s\n' "$1" "$2"
    else
      printf '  FAIL %s: expected %s, got %s\n' "$1" "$3" "$2"
      fails=$((fails + 1))
    fi
  }

  printf '== engine self-test ==\n'

  run_lane "synthetic-pass" "-" "true && true" >/dev/null 2>&1
  # A body whose FIRST command fails and which then does more work: this is the
  # exact shape that reports success under `( set -e; ... ) || rc=$?`.
  run_lane "synthetic-fail" "-" "false && echo unreachable" >/dev/null 2>&1
  run_lane "synthetic-fail-midway" "-" "true && false && true" >/dev/null 2>&1
  run_lane "synthetic-skip" "definitely-not-a-real-tool-xyzzy" "true" >/dev/null 2>&1

  assert_eq "PASSED" "$PASSED" "1"
  assert_eq "FAILED" "$FAILED" "2"
  assert_eq "SKIPPED" "$SKIPPED" "1"

  case "$FAILED_LANES" in
    *synthetic-fail*) printf '  ok   failing lane is named in the report\n' ;;
    *) printf '  FAIL failing lane missing from the report\n'; fails=$((fails + 1)) ;;
  esac
  case "$SKIPPED_LANES" in
    *synthetic-skip*) printf '  ok   skipped lane is named in the report\n' ;;
    *) printf '  FAIL skipped lane missing from the report\n'; fails=$((fails + 1)) ;;
  esac

  local rc
  summary >/dev/null 2>&1
  rc=$?
  assert_eq "exit status with 2 FAILED" "$rc" "1"

  # A skip alone must NOT fail the run, and MUST fail it under REQUIRE_ALL.
  PASSED=1; FAILED=0; SKIPPED=1; FAILED_LANES=""; SKIPPED_LANES="s|missing: x
"
  REQUIRE_ALL=0; summary >/dev/null 2>&1; rc=$?
  assert_eq "exit status, skip only, default" "$rc" "0"
  REQUIRE_ALL=1; summary >/dev/null 2>&1; rc=$?
  assert_eq "exit status, skip only, REQUIRE_ALL=1" "$rc" "1"

  # An all-green run exits 0.
  PASSED=3; FAILED=0; SKIPPED=0; FAILED_LANES=""; SKIPPED_LANES=""
  REQUIRE_ALL=0; summary >/dev/null 2>&1; rc=$?
  assert_eq "exit status, all green" "$rc" "0"

  if [ "$fails" -eq 0 ]; then
    printf '\nok: test-all.sh engine is honest about pass, fail and skip\n'
    return 0
  fi
  printf '\nFAIL: %s engine assertion(s) failed\n' "$fails"
  return 1
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

# ---------------------------------------------------------------------------
# Preflight: resolve interpreters and SDK roots. NON-FATAL by design — an
# unresolved one turns into a named SKIP, not a dead run.
# ---------------------------------------------------------------------------

if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.13)"
  else
    PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
  fi
fi
if [ -n "${PYTHON_BIN:-}" ] && [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=""
fi
export PYTHON_BIN

if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ]; then
  export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
  export PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH
fi

if [ -z "${ANDROID_HOME:-}" ]; then
  if [ -d /opt/homebrew/share/android-commandlinetools/platforms/android-34 ]; then
    export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
  elif [ -d "$HOME/Library/Android/sdk/platforms/android-34" ]; then
    export ANDROID_HOME="$HOME/Library/Android/sdk"
  fi
fi

if [ -z "${PYTHON_BIN:-}" ]; then
  printf 'WARNING: no Python 3.10+ found; every Python lane will SKIP.\n' >&2
  printf '         Set PYTHON_BIN to the interpreter to use.\n' >&2
fi

# ---------------------------------------------------------------------------
# The lanes
# ---------------------------------------------------------------------------

run_lane "cross-SDK conformance" "python" \
  "'$PYTHON_BIN' '$ROOT/conformance/check_conformance.py' \
   && '$PYTHON_BIN' '$ROOT/conformance/check_conformance.py' --self-test"

# `pysdk` is what closes the dead gate: without the editable install this lane
# died in collection on `import httpx2`, and every spec assertion in
# tests/test_sdk_contract.py was unreachable.
run_lane "repository contract and catalog guards" "pysdk py:httpx2 py:openai py:pytest git" \
  "cd '$ROOT' \
   && '$PYTHON_BIN' -m unittest tests/test_sdk_contract.py \
   && '$PYTHON_BIN' -m pytest -q tests/test_release_versions.py \
   && bash '$ROOT/tests/sdk-static-catalog-count.test.sh'"

run_lane "cross-language demo E2E" "pysdk node swift mvn jre" \
  "bash '$ROOT/tests/demo-e2e-record.test.sh'"

run_lane "dependency security audit" "osv-scanner pip-audit npm" \
  "'$ROOT/scripts/security-audit.sh'"

run_lane "JavaScript / TypeScript" "npm" \
  "cd '$ROOT/sdks/js' && npm test"

run_lane "Python" "pysdk py:pytest py:pytest_asyncio" \
  "cd '$ROOT/sdks/python' && '$PYTHON_BIN' -m pytest -q"

run_lane "Java" "mvn jre" \
  "cd '$ROOT/sdks/java' && mvn -q test"

run_lane "Kotlin" "jre" \
  "cd '$ROOT/sdks/kotlin' && ./gradlew build publishToMavenLocal"

run_lane "Android" "jre android" \
  "cd '$ROOT/sdks/android' && ./gradlew build"

run_lane "Go" "go" \
  "cd '$ROOT/sdks/go' && go test ./... && go test -race ./... && go vet ./..."

run_lane "Rust" "cargo" \
  "cd '$ROOT/sdks/rust' \
   && cargo fmt --check \
   && cargo test --all-features \
   && cargo clippy --all-targets --all-features -- -D warnings"

run_lane "Swift" "swift" \
  "cd '$ROOT/sdks/swift' \
   && swift test \
   && swift build -Xswiftc -strict-concurrency=complete -Xswiftc -warnings-as-errors"

run_lane "Dart" "dart" \
  "cd '$ROOT/sdks/dart' && dart analyze && dart test && grep -Fx 'publish_to: none' pubspec.yaml"

run_lane "R" "Rscript" \
  "cd '$ROOT/sdks/r' && Rscript -e 'testthat::test_local(\".\", reporter=\"summary\")'"

summary
exit $?
