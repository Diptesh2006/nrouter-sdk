#!/usr/bin/env bash
# Fail the release gate on every known advisory that the supported package
# ecosystems can resolve from this repository's manifests and lockfiles.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need() {
  command -v "$1" >/dev/null || {
    echo "ERROR: required security tool '$1' is missing" >&2
    exit 78
  }
}

need osv-scanner
need pip-audit
need npm

osv-scanner scan source \
  --lockfile "$ROOT/sdks/js/package-lock.json" \
  --lockfile "$ROOT/sdks/java/pom.xml" \
  --lockfile "$ROOT/sdks/kotlin/gradle.lockfile" \
  --lockfile "$ROOT/sdks/android/gradle.lockfile" \
  --lockfile "$ROOT/sdks/rust/Cargo.lock" \
  --lockfile "$ROOT/sdks/dart/pubspec.lock"

(cd "$ROOT/sdks/js" && npm audit --omit=dev)
pip-audit --strict "$ROOT/sdks/python"

printf '\nOK: no known dependency vulnerabilities in the auditable SDK graphs\n'
