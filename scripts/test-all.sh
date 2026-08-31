#!/usr/bin/env bash
# One local release gate for all ten SDKs. Live tests remain opt-in because they
# spend credits; set NROUTER_LIVE=1 only with a local/stage gateway and key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() { printf '\n== %s ==\n' "$1"; }
need() { command -v "$1" >/dev/null || { echo "ERROR: required tool '$1' is missing" >&2; exit 78; }; }

for tool in npm mvn go cargo swift dart Rscript; do need "$tool"; done

if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3.13 >/dev/null; then
    PYTHON_BIN="$(command -v python3.13)"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: Python 3.10+ is required; set PYTHON_BIN to its executable" >&2
  exit 78
fi

if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ]; then
  export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
  export PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH
fi

if [ -z "${ANDROID_HOME:-}" ]; then
  if [ -d /opt/homebrew/share/android-commandlinetools/platforms/android-34 ]; then
    export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
  elif [ -d "$HOME/Library/Android/sdk/platforms/android-34" ]; then
    export ANDROID_HOME="$HOME/Library/Android/sdk"
  else
    echo "ERROR: Android SDK 34 is missing; set ANDROID_HOME after installing platform 34 and build-tools 34.0.0" >&2
    exit 78
  fi
fi

step "cross-SDK conformance and mutation proof"
"$PYTHON_BIN" "$ROOT/conformance/check_conformance.py"
"$PYTHON_BIN" "$ROOT/conformance/check_conformance.py" --self-test

step "repository contract and catalog guards"
(cd "$ROOT" && "$PYTHON_BIN" -m unittest tests/test_sdk_contract.py)
(cd "$ROOT" && "$PYTHON_BIN" -m pytest -q tests/test_release_versions.py)
bash "$ROOT/tests/sdk-static-catalog-count.test.sh"
bash "$ROOT/tests/demo-e2e-record.test.sh"

step "dependency security audit"
"$ROOT/scripts/security-audit.sh"

step "JavaScript / TypeScript"
(cd "$ROOT/sdks/js" && npm test)

step "Python"
(cd "$ROOT/sdks/python" && "$PYTHON_BIN" -m pytest -q)

step "Java"
(cd "$ROOT/sdks/java" && mvn -q test)

step "Kotlin"
(cd "$ROOT/sdks/kotlin" && ./gradlew build publishToMavenLocal)

step "Android"
(cd "$ROOT/sdks/android" && ./gradlew build)

step "Go"
(cd "$ROOT/sdks/go" && go test ./... && go test -race ./... && go vet ./...)

step "Rust"
(cd "$ROOT/sdks/rust" && cargo fmt --check && cargo test --all-features && cargo clippy --all-targets --all-features -- -D warnings)

step "Swift"
(cd "$ROOT/sdks/swift" && swift test && swift build -Xswiftc -strict-concurrency=complete -Xswiftc -warnings-as-errors)

step "Dart"
(cd "$ROOT/sdks/dart" && dart analyze && dart test && grep -Fx 'publish_to: none' pubspec.yaml)

step "R"
(cd "$ROOT/sdks/r" && Rscript -e 'testthat::test_local(".", reporter="summary")')

printf '\nOK: all ten SDK suites and the shared conformance gate passed\n'
