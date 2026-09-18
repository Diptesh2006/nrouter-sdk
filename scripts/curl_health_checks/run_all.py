#!/usr/bin/env python3
"""nRouter Consolidated Pure-Curl Health Checks Runner (`run_all`).

Consolidates all modular health checks into a single runner:
  1. Models & Providers (`model_curl`):
     - Catalog verification (GET /v1/models)
     - Provider discovery & distribution (OpenAI, Anthropic, Google, Meta, etc.)
     - Live provider wire inference probe (POST /v1/chat/completions)
  2. Guardrails (`guardrail_curl`):
     - Platform moderation floor (explicit, toxicity, violence, self-harm, harmful intent)
     - Workplace / technical phrasing false-positive resistance
     - Guardrail presets: Prompt injection (DAN, overrides) and secret leakage detection
     - PII handling & redaction posture
     - Evasion normalization (homoglyphs, letter-spacing, leetspeak, base64 smuggling)
     - Wire contract assertions ($0 token spend on injection/refusal, exact posture headers)

Usage:
  python3 scripts/curl_health_checks/run_all.py --self-test
  python3 scripts/curl_health_checks/run_all.py --quick
  python3 scripts/curl_health_checks/run_all.py
  python3 scripts/curl_health_checks/run_all.py --step-summary
  python3 scripts/curl_health_checks/run_all.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure scripts/curl_health_checks is on path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import model_curl
import guardrail_curl


def run_all_self_tests() -> int:
    """Run offline self-tests for all consolidated check modules."""
    print("=== Running Consolidated Offline Self-Tests ===")
    print("1. Testing model_curl module...")
    model_code = model_curl.run_self_test()
    if model_code != 0:
        print("[FAIL] model_curl self-test failed", file=sys.stderr)
        return model_code

    print("\n2. Testing guardrail_curl module...")
    guard_code = guardrail_curl.run_self_test()
    if guard_code != 0:
        print("[FAIL] guardrail_curl self-test failed", file=sys.stderr)
        return guard_code

    print("\n[PASS] All consolidated self-tests passed cleanly (100% offline verification).")
    return 0


def render_consolidated_summary(
    base_url: str,
    model_result: Dict[str, Any],
    guard_result: Dict[str, Any],
) -> str:
    """Render unified markdown summary for GitHub Step Summary or terminal reporting."""
    overall_passed = model_result["passed"] and guard_result["all_passed"]
    overall_badge = "🟢 **ALL CHECKS OPERATIONAL**" if overall_passed else "🔴 **FAILURES DETECTED**"

    lines = [
        "# 🚀 nRouter Consolidated Health Check Report",
        "",
        f"**Overall Status**: {overall_badge} | **Base URL**: `{base_url}` | **Timestamp**: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`",
        "",
        "## Summary Overview",
        "",
        "| Check Suite | Scope / Focus | Checks Run | Passed | Failed | Status |",
        "|---|---|---|---|---|---|",
        f"| **Models & Providers** | Catalog & Live Provider Inference | {len(model_result['checks'])} | {sum(1 for c in model_result['checks'] if c['passed'])} | {sum(1 for c in model_result['checks'] if not c['passed'])} | {'✅ Pass' if model_result['passed'] else '❌ Fail'} |",
        f"| **Guardrails & WAF** | Moderation, Injection, Secrets, Evasions | {guard_result['total_cases']} | {guard_result['passed_cases']} | {guard_result['failed_cases']} | {'✅ Pass' if guard_result['all_passed'] else '❌ Fail'} |",
        "",
        "---",
        "",
    ]

    # Include Models summary
    lines.append(model_curl.ModelCurlHealthCheck().render_markdown_summary(model_result))
    lines.append("\n---\n")
    # Include Guardrails summary
    lines.append(guardrail_curl.GuardrailCurlHealthCheck().render_markdown_summary(guard_result))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Consolidated Pure-Curl Health Checks Runner")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test for all modules and exit")
    parser.add_argument("--quick", action="store_true", help="Run quick live verification (sample guardrails)")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", model_curl.DEFAULT_BASE_URL), help="Gateway Base URL")
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""), help="nRouter API key")
    parser.add_argument("--probe-model", default=model_curl.DEFAULT_PROBE_MODEL, help="Model to probe for chat completions")
    parser.add_argument("--guardrail-route", default=guardrail_curl.DEFAULT_GUARDRAIL_ROUTE, help="Route for guardrails check")
    parser.add_argument("--guardrail-model", default=guardrail_curl.DEFAULT_GUARDRAIL_MODEL, help="Model for guardrails check")
    parser.add_argument("--step-summary", action="store_true", help="Write consolidated markdown summary to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Output aggregated JSON results to stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_all_self_tests()

    api_key = args.api_key
    if not api_key:
        test_creds = Path.home() / ".nrouter_admin_keys/nrouter-test/prod/credentials.env"
        if test_creds.is_file():
            try:
                import re
                content = test_creds.read_text()
                match = re.search(r'NROUTER_TEST_API_KEY=["\']?([^"\'\n]+)["\']?', content)
                if match:
                    api_key = match.group(1)
            except Exception:
                pass

    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        print("Set NROUTER_API_KEY or use --self-test for offline validation.", file=sys.stderr)
        return 1

    print("============================================================")
    print("      nRouter Consolidated Pure-Curl Health Checks          ")
    print("============================================================")
    print(f"Base URL:         {args.base_url}")
    print(f"Mode:             {'Quick' if args.quick else 'Full Comprehensive'}")
    print(f"Probe Model:      {args.probe_model}")
    print(f"Guardrail Model:  {args.guardrail_model}")
    print("------------------------------------------------------------\n")

    # 1. Models & Providers
    print("▶ Running [1/2] Models & Providers Health Check...")
    model_checker = model_curl.ModelCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        probe_model=args.probe_model,
    )
    model_res = model_checker.run_all()
    print(f"  ✓ Models Catalog:    {model_res['summary']['total_models']} models discovered")
    print(f"  ✓ Active Providers:  {model_res['summary']['total_providers']} providers active")
    print(f"  ✓ Provider Probe:    {model_res['summary']['probe_latency_ms']}ms latency")
    print(f"  Result:              {'PASS' if model_res['passed'] else 'FAIL'}\n")

    # 2. Guardrails
    print("▶ Running [2/2] Guardrails & WAF Health Check...")
    guard_checker = guardrail_curl.GuardrailCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        route=args.guardrail_route,
        model=args.guardrail_model,
    )
    guard_res = guard_checker.run_suite(quick=args.quick)
    print(f"  ✓ Total Cases:       {guard_res['total_cases']}")
    print(f"  ✓ Cases Passed:      {guard_res['passed_cases']}")
    print(f"  ✓ Cases Failed:      {guard_res['failed_cases']}")
    print(f"  Result:              {'PASS' if guard_res['all_passed'] else 'FAIL'}\n")

    overall_passed = model_res["passed"] and guard_res["all_passed"]

    print("============================================================")
    print(f"OVERALL STATUS:   {'🟢 ALL OPERATIONAL (PASS)' if overall_passed else '🔴 FAILURES DETECTED (FAIL)'}")
    print("============================================================")

    if args.step_summary:
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            summary_md = render_consolidated_summary(args.base_url, model_res, guard_res)
            try:
                with open(step_summary_path, "a") as f:
                    f.write("\n" + summary_md + "\n")
                print(f"Appended consolidated summary to GITHUB_STEP_SUMMARY ({step_summary_path})")
            except Exception as exc:
                print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {exc}", file=sys.stderr)

    if args.json:
        combined = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": args.base_url,
            "overall_passed": overall_passed,
            "models_and_providers": model_res,
            "guardrails": guard_res,
        }
        print(json.dumps(combined, indent=2))

    return 0 if overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
