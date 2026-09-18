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
  3. Endpoints & Features (`feature_curl`)
  4. Per-feature curl proofs — ten adversarial-heavy modules, each with at least
     as many adversarial checks as happy-path ones, each asserting headers and
     body rather than a status code alone:
     `fallbacks_curl`, `guardrails_request_curl`, `cache_curl`,
     `rate_limit_curl`, `context_limit_curl`, `metering_curl`, `tracing_curl`,
     `moderation_floor_curl`, `mcp_curl`, `contract_curl`

Usage:
  python3 scripts/curl_health_checks/run_all.py --self-test
  python3 scripts/curl_health_checks/run_all.py --quick
  python3 scripts/curl_health_checks/run_all.py
  python3 scripts/curl_health_checks/run_all.py --step-summary
  python3 scripts/curl_health_checks/run_all.py --json
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure scripts/curl_health_checks is on path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import _curl_common
import model_curl
import guardrail_curl
import feature_curl

# Per-feature proof modules. Each exposes run_self_test(), a
# <Domain>CurlHealthCheck class with named checks, run_suite(quick=...) and
# render_markdown_summary(). Each returns the same JSON contract:
#   {feature, base_url, checks: [{name, request, status, headers, assertion,
#                                 result, expected_failure}]}
# `result` is PASS, FAIL or NOT-CONFIGURED — a check whose precondition is
# missing on the plane reports NOT-CONFIGURED and never PASS.
import fallbacks_curl
import guardrails_request_curl
import cache_curl
import rate_limit_curl
import context_limit_curl
import metering_curl
import tracing_curl
import moderation_floor_curl
import mcp_curl
import contract_curl

FEATURE_MODULES = [
    ("fallbacks", fallbacks_curl, "FallbacksCurlHealthCheck"),
    ("guardrails_request", guardrails_request_curl, "GuardrailsRequestCurlHealthCheck"),
    ("cache", cache_curl, "CacheCurlHealthCheck"),
    ("rate_limit", rate_limit_curl, "RateLimitCurlHealthCheck"),
    ("context_limit", context_limit_curl, "ContextLimitCurlHealthCheck"),
    ("metering", metering_curl, "MeteringCurlHealthCheck"),
    ("tracing", tracing_curl, "TracingCurlHealthCheck"),
    ("moderation_floor", moderation_floor_curl, "ModerationFloorCurlHealthCheck"),
    ("mcp", mcp_curl, "McpCurlHealthCheck"),
    ("contract", contract_curl, "ContractCurlHealthCheck"),
]


def _accepted_init_kwargs(factory: Any) -> set:
    """The keyword arguments a module's constructor DECLARES.

    Read from the signature, never from ``__code__.co_varnames``: that tuple
    lists every local variable in the body too, so a constructor that merely
    used a local called ``route`` would be handed ``route=`` and raise
    ``TypeError`` before a single request was sent.
    """
    try:
        return set(inspect.signature(factory.__init__).parameters) - {"self"}
    except (TypeError, ValueError):
        return set()


def _kwargs_detection_self_test() -> int:
    """The route/model hand-off must read a constructor's PARAMETERS, never its locals.

    A class whose ``__init__`` merely uses a local variable called ``route`` must
    not be handed ``route=`` — that call would raise ``TypeError`` and abort the
    whole run before a single request. A class that declares the parameter must
    receive it.
    """

    class Locals:
        def __init__(self, base_url: str, api_key: str) -> None:
            route = base_url  # a local, not a parameter
            self.route = route

    class Params:
        def __init__(self, base_url: str, api_key: str, route: str = "", model: str = "") -> None:
            self.route, self.model = route, model

    if "route" in _accepted_init_kwargs(Locals):
        print("[FAIL] kwargs detection reads locals as parameters", file=sys.stderr)
        return 1
    if {"route", "model"} - _accepted_init_kwargs(Params):
        print("[FAIL] kwargs detection misses declared parameters", file=sys.stderr)
        return 1
    print("  kwargs detection: parameters only — OK")
    return 0


def run_all_self_tests() -> int:
    """Run offline self-tests for all consolidated check modules."""
    print("=== Running Consolidated Offline Self-Tests ===")
    print("0. Testing _curl_common (shared transport, parser and credential rule)...")
    common_code = _curl_common.run_self_test()
    if common_code != 0:
        print("[FAIL] _curl_common self-test failed", file=sys.stderr)
        return common_code
    kwargs_code = _kwargs_detection_self_test()
    if kwargs_code != 0:
        return kwargs_code

    print("\n1. Testing model_curl module...")
    model_code = model_curl.run_self_test()
    if model_code != 0:
        print("[FAIL] model_curl self-test failed", file=sys.stderr)
        return model_code

    print("\n2. Testing guardrail_curl module...")
    guard_code = guardrail_curl.run_self_test()
    if guard_code != 0:
        print("[FAIL] guardrail_curl self-test failed", file=sys.stderr)
        return guard_code

    print("\n3. Testing feature_curl module...")
    feat_code = feature_curl.run_self_test()
    if feat_code != 0:
        print("[FAIL] feature_curl self-test failed", file=sys.stderr)
        return feat_code

    for index, (feature, module, _) in enumerate(FEATURE_MODULES, start=4):
        print(f"\n{index}. Testing {feature}_curl module...")
        code = module.run_self_test()
        if code != 0:
            print(f"[FAIL] {feature} self-test failed", file=sys.stderr)
            return code

    print("\n[PASS] All consolidated self-tests passed cleanly (100% offline verification).")
    return 0


def run_feature_suites(
    base_url: str, api_key: str, quick: bool, route: str = "", model: str = ""
) -> List[Dict[str, Any]]:
    """Run every per-feature proof module and return their JSON reports.

    The route and model reach every module, because a virtual key is commonly
    scoped to a subset of both — pointing the suite at a route the key may not
    use tests the key policy, not the gateway. `mcp_curl` has its own fixed path
    and ignores them.
    """
    suites: List[Dict[str, Any]] = []
    for feature, module, class_name in FEATURE_MODULES:
        factory = getattr(module, class_name)
        kwargs: Dict[str, Any] = {"base_url": base_url, "api_key": api_key}
        accepted = _accepted_init_kwargs(factory)
        if "route" in accepted:
            kwargs["route"] = route
        if "model" in accepted:
            kwargs["model"] = model
        checker = factory(**kwargs)
        suite = checker.run_suite(quick=quick)
        suite["_markdown"] = checker.render_markdown_summary(suite)
        suites.append(suite)
        state = "PASS" if suite["all_passed"] else "FAIL"
        if suite["all_passed"] and suite["partial"]:
            state = "PARTIAL"
        print(
            f"  ✓ {feature:<20} {state:<8} "
            f"{suite['passed_checks']}/{suite['total_checks']} passed, "
            f"{suite['failed_checks']} failed, "
            f"{suite['not_configured_checks']} not-configured, "
            f"{suite['adversarial_checks']} adversarial"
        )
    return suites


def render_feature_summary(suites: List[Dict[str, Any]]) -> str:
    """Render the per-feature proof table for the consolidated markdown report."""
    lines = [
        "## Per-Feature Curl Proofs",
        "",
        "| Feature | Checks | Passed | Failed | Not-Configured | Adversarial | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for suite in suites:
        if not suite["all_passed"]:
            status = "❌ Fail"
        elif suite["partial"]:
            status = "🟡 Partial"
        else:
            status = "✅ Pass"
        lines.append(
            f"| **{suite['feature']}** | {suite['total_checks']} | {suite['passed_checks']} | "
            f"{suite['failed_checks']} | {suite['not_configured_checks']} | "
            f"{suite['adversarial_checks']} | {status} |"
        )
    for suite in suites:
        lines.extend(["", "---", "", suite.get("_markdown", "")])
    return "\n".join(lines)


def render_consolidated_summary(
    base_url: str,
    model_result: Dict[str, Any],
    guard_result: Dict[str, Any],
    feature_result: Dict[str, Any],
    feature_suites: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render unified markdown summary for GitHub Step Summary or terminal reporting."""
    feature_suites = feature_suites or []
    overall_passed = (
        model_result["passed"]
        and guard_result["all_passed"]
        and feature_result["all_passed"]
        and all(suite["all_passed"] for suite in feature_suites)
    )
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
        f"| **Endpoints & Features** | Feature Probes Across All Endpoints & Params | {feature_result['total_features']} | {feature_result['passed_features']} | {feature_result['failed_features']} | {'✅ Pass' if feature_result['all_passed'] else '❌ Fail'} |",
        "",
        "---",
        "",
    ]

    # Include Models summary
    lines.append(model_curl.ModelCurlHealthCheck().render_markdown_summary(model_result))
    lines.append("\n---\n")
    # Include Guardrails summary
    lines.append(guardrail_curl.GuardrailCurlHealthCheck().render_markdown_summary(guard_result))
    lines.append("\n---\n")
    # Include Features summary
    lines.append(feature_curl.FeatureCurlHealthCheck().render_markdown_summary(feature_result))

    if feature_suites:
        lines.append("\n---\n")
        lines.append(render_feature_summary(feature_suites))

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
    parser.add_argument("--chat-model", default=feature_curl.DEFAULT_CHAT_MODEL, help="Model for feature chat completions")
    parser.add_argument("--messages-model", default=feature_curl.DEFAULT_MESSAGES_MODEL, help="Model for feature messages")
    parser.add_argument("--embed-model", default=feature_curl.DEFAULT_EMBED_MODEL, help="Model for feature embeddings")
    _curl_common.add_wire_arguments(parser)
    parser.add_argument("--step-summary", action="store_true", help="Write consolidated markdown summary to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Output aggregated JSON results to stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_all_self_tests()

    # The key comes from --api-key or NROUTER_API_KEY, and nowhere else. There
    # is deliberately no credentials-file fallback: this repository is public, a
    # hardcoded path leaks an internal convention, and a fallback would send
    # whatever key it found to whatever --base-url the caller passed.
    api_key = _curl_common.resolve_api_key(args.api_key)
    if not api_key:
        print(_curl_common.MISSING_KEY_MESSAGE, file=sys.stderr)
        return _curl_common.EXIT_UNRUNNABLE

    # THE --json CONTRACT: stdout carries EXACTLY one JSON document, so every
    # human line in this run is routed to stderr. stdout is restored just before
    # the document is written, below.
    machine_stdout = sys.stdout
    if args.json:
        sys.stdout = sys.stderr

    print("============================================================")
    print("      nRouter Consolidated Pure-Curl Health Checks          ")
    print("============================================================")
    print(f"Base URL:         {args.base_url}")
    print(f"Route / Model:    {args.route} / {args.model}")
    print(f"Mode:             {'Quick' if args.quick else 'Full Comprehensive'}")
    print(f"Probe Model:      {args.probe_model}")
    print(f"Guardrail Model:  {args.guardrail_model}")
    print(f"Chat Model:       {args.chat_model}")
    print(f"Messages Model:   {args.messages_model}")
    print(f"Embed Model:      {args.embed_model}")
    print("------------------------------------------------------------\n")

    # 1. Models & Providers
    print("▶ Running [1/4] Models & Providers Health Check...")
    # --route / --model are the ONE override surface and reach the three legacy
    # modules too; the env variables already did, the flags did not (round-4
    # measurement: 11 probes stayed on /chat/completions under --route).
    model_checker = model_curl.ModelCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        probe_model=args.probe_model,
        route=args.route,
        model=args.model,
    )
    model_res = model_checker.run_all()
    print(f"  ✓ Models Catalog:    {model_res['summary']['total_models']} models discovered")
    print(f"  ✓ Active Providers:  {model_res['summary']['total_providers']} providers active")
    print(f"  ✓ Provider Probe:    {model_res['summary']['probe_latency_ms']}ms latency")
    print(f"  Result:              {'PASS' if model_res['passed'] else 'FAIL'}\n")

    # 2. Guardrails
    print("▶ Running [2/4] Guardrails & WAF Health Check...")
    # --guardrail-route / --guardrail-model stay as deprecated aliases: they win
    # only when the caller set them away from their defaults.
    guard_route = (
        args.guardrail_route
        if args.guardrail_route != guardrail_curl.DEFAULT_GUARDRAIL_ROUTE
        else args.route
    )
    guard_model = (
        args.guardrail_model
        if args.guardrail_model != guardrail_curl.DEFAULT_GUARDRAIL_MODEL
        else args.model
    )
    guard_checker = guardrail_curl.GuardrailCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        route=guard_route,
        model=guard_model,
    )
    guard_res = guard_checker.run_suite(quick=args.quick)
    print(f"  ✓ Total Cases:       {guard_res['total_cases']}")
    print(f"  ✓ Cases Passed:      {guard_res['passed_cases']}")
    print(f"  ✓ Cases Failed:      {guard_res['failed_cases']}")
    print(f"  Result:              {'PASS' if guard_res['all_passed'] else 'FAIL'}\n")

    # 3. Endpoints & Features
    print("▶ Running [3/4] Endpoints & Parameters Health Check...")
    feat_checker = feature_curl.FeatureCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        chat_model=args.chat_model,
        messages_model=args.messages_model,
        embed_model=args.embed_model,
        route=args.route,
        model=args.model,
    )
    feat_res = feat_checker.run_suite(quick=args.quick)
    print(f"  ✓ Total Probes:      {feat_res['total_features']}")
    print(f"  ✓ Probes Passed:     {feat_res['passed_features']}")
    print(f"  ✓ Probes Failed:     {feat_res['failed_features']}")
    print(f"  Result:              {'PASS' if feat_res['all_passed'] else 'FAIL'}\n")

    # 4. Per-feature curl proofs (ten modules, adversarial-heavy)
    print("▶ Running [4/4] Per-Feature Curl Proofs...")
    feature_suites = run_feature_suites(
        args.base_url, api_key, args.quick, route=args.route, model=args.model
    )
    feature_failures = sum(suite["failed_checks"] for suite in feature_suites)
    feature_unconfigured = sum(suite["not_configured_checks"] for suite in feature_suites)
    print(
        f"  Result:              {'PASS' if feature_failures == 0 else 'FAIL'}"
        f"{' (PARTIAL: ' + str(feature_unconfigured) + ' not-configured)' if feature_unconfigured else ''}\n"
    )

    overall_passed = (
        model_res["passed"]
        and guard_res["all_passed"]
        and feat_res["all_passed"]
        and feature_failures == 0
    )

    print("============================================================")
    print(f"OVERALL STATUS:   {'🟢 ALL OPERATIONAL (PASS)' if overall_passed else '🔴 FAILURES DETECTED (FAIL)'}")
    print("============================================================")

    if args.step_summary:
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            summary_md = render_consolidated_summary(
                args.base_url, model_res, guard_res, feat_res, feature_suites
            )
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
            "features": feat_res,
            "feature_proofs": [
                {key: value for key, value in suite.items() if key != "_markdown"}
                for suite in feature_suites
            ],
        }
        sys.stdout = machine_stdout
        print(json.dumps(combined, indent=2))

    return _curl_common.EXIT_OK if overall_passed else _curl_common.EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
