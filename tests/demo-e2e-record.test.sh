#!/usr/bin/env bash
set -euo pipefail

# nRouter Multi-Language SDK End-to-End Demo Certification Test
# Verifies all active SDKs against demo key configuration

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$ROOT_DIR"

echo "======================================================================"
echo "nRouter SDK Multi-Language Demo & End-to-End Test Suite"
echo "======================================================================"

# 1. Run Python Demo E2E
echo ""
echo ">>> [1/5] Executing Python SDK Demo E2E..."
"$PYTHON_BIN" examples/python/demo_e2e_suite.py

# 2. Run TypeScript/Node Demo E2E
echo ""
echo ">>> [2/5] Executing TypeScript/JavaScript SDK Demo E2E..."
node examples/typescript/demo_e2e_suite.js

# 3. Run Swift SDK E2E Contract Suite
echo ""
echo ">>> [3/5] Executing Swift SDK Contract & Wire Suite..."
swift test --filter ContractTests

# 4. Run Kotlin SDK E2E Contract Suite
echo ""
echo ">>> [4/5] Executing Kotlin SDK Contract & Wire Suite..."
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export PATH="$JAVA_HOME/bin:$PATH"
(cd sdks/kotlin && ./gradlew test --tests "ai.nrouter.sdk.ContractTest")

# 5. Run Java SDK E2E Suite
echo ""
echo ">>> [5/5] Executing Java SDK Contract & Wire Suite..."
(cd sdks/java && mvn test -q)

echo ""
echo "======================================================================"
echo "ALL SDK DEMO & END-TO-END VERIFICATIONS PASSED"
echo "======================================================================"
