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
    ("context_limit", context_limit_curl, "ContextLimitCurlHealthCheck"),
    ("metering", metering_curl, "MeteringCurlHealthCheck"),
    ("tracing", tracing_curl, "TracingCurlHealthCheck"),
    ("moderation_floor", moderation_floor_curl, "ModerationFloorCurlHealthCheck"),
    ("mcp", mcp_curl, "McpCurlHealthCheck"),
    ("contract", contract_curl, "ContractCurlHealthCheck"),
    ("rate_limit", rate_limit_curl, "RateLimitCurlHealthCheck"),
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


def _not_evaluated_summary_self_test() -> int:
    """NOT-EVALUATED checks must be listed by name under their own heading in consolidated summary."""
    model_res = {
        "passed": True,
        "checks": [],
        "base_url": "https://api.test/v1",
        "summary": {"total_models": 0, "total_providers": 0, "probe_latency_ms": 0, "providers": {}},
        "probe": {"model": "m", "status": 200, "passed": True, "request_id": "r", "latency_ms": 0, "response_sample": ""},
    }
    guard_res = {
        "all_passed": True,
        "total_cases": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "base_url": "https://api.test/v1",
        "route": "/chat/completions",
        "model": "m",
        "category_summary": {},
        "checks": [],
    }
    feat_res = {
        "all_passed": True,
        "total_features": 0,
        "passed_features": 0,
        "failed_features": 0,
        "base_url": "https://api.test/v1",
        "route": "/chat/completions",
        "model": "m",
        "category_summary": {},
        "checks": [],
    }

    # Clean run: no NOT-EVALUATED checks
    clean_md = render_consolidated_summary("https://api.test/v1", model_res, guard_res, feat_res, [])
    if "### Not-Evaluated Checks" in clean_md:
        print("[FAIL] clean run should not render Not-Evaluated heading", file=sys.stderr)
        return 1

    # Suite with a NOT-EVALUATED check
    # The fixture obeys suite_verdict: one real pass alongside the
    # NOT-EVALUATED row, so all_passed=True / proved_nothing=False is a state
    # the helper can actually produce (zero passes never reads as passing).
    suite_with_ne = [{
        "feature": "rate_limit",
        "all_passed": True,
        "partial": True,
        "proved_nothing": False,
        "total_checks": 2,
        "passed_checks": 1,
        "failed_checks": 0,
        "not_configured_checks": 0,
        "not_evaluated_checks": 1,
        "adversarial_checks": 1,
        "checks": [
            {
                "name": "burst_returns_429_with_retry_after",
                "result": "NOT-EVALUATED",
                "not_evaluated": True,
            }
        ],
    }]
    ne_md = render_consolidated_summary("https://api.test/v1", model_res, guard_res, feat_res, suite_with_ne)
    if "### Not-Evaluated Checks" not in ne_md:
        print("[FAIL] missing '### Not-Evaluated Checks' heading in consolidated summary", file=sys.stderr)
        return 1
    if "burst_returns_429_with_retry_after" not in ne_md:
        print("[FAIL] NOT-EVALUATED check name missing under heading in summary", file=sys.stderr)
        return 1
    print("  consolidated summary not-evaluated heading: present by name — OK")
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
    ne_code = _not_evaluated_summary_self_test()
    if ne_code != 0:
        return ne_code

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
        # The verdict words come from the shared rule (`_curl_common.suite_verdict`),
        # which every module now carries: a suite in which nothing was proven is
        # NOT a pass, however few things failed.
        if suite["proved_nothing"]:
            state = "NOTHING-PROVEN"
        elif not suite["all_passed"]:
            state = "FAIL"
        elif suite["partial"]:
            state = "PARTIAL"
        else:
            state = "PASS"
        print(
            f"  ✓ {feature:<20} {state:<14} "
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
        # `proved_nothing` is reported per module, never averaged away: a domain
        # that reached the gateway zero times is not a domain that passed.
        if suite["proved_nothing"]:
            status = "⚪ Nothing proven"
        elif not suite["all_passed"]:
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

    def cell(result: Dict[str, Any], verdict_key: str) -> str:
        """One suite's status cell, under the shared rule."""
        if result.get("proved_nothing"):
            return "⚪ Nothing proven"
        return "✅ Pass" if result[verdict_key] else "❌ Fail"

    # Named, never averaged away: a domain that proved nothing is listed by name
    # so a reader of this report cannot mistake silence for evidence.
    nothing_proven = (
        (["Models & Providers"] if model_result.get("proved_nothing") else [])
        + (["Guardrails & WAF"] if guard_result.get("proved_nothing") else [])
        + (["Endpoints & Features"] if feature_result.get("proved_nothing") else [])
        + [s["feature"] for s in feature_suites if s.get("proved_nothing")]
    )

    # Collect NOT-EVALUATED checks across all suites:
    # A 429 lacking both Retry-After and x-nr-limit-source cannot be verified on wire alone.
    # NOT-EVALUATED counts as NOT PROVEN (never a pass) and is listed by name under its own heading.
    not_evaluated_checks: List[str] = []
    for suite in feature_suites:
        for check in suite.get("checks", []):
            if check.get("result") == "NOT-EVALUATED" or check.get("not_evaluated"):
                feature_name = suite.get("feature", "feature")
                not_evaluated_checks.append(f"{feature_name}: `{check.get('name', 'check')}`")
    for r, label in [
        (model_result, "models"),
        (guard_result, "guardrails"),
        (feature_result, "features"),
    ]:
        for check in r.get("checks", []):
            if check.get("result") == "NOT-EVALUATED" or check.get("not_evaluated"):
                not_evaluated_checks.append(f"{label}: `{check.get('name', 'check')}`")

    lines = [
        "# 🚀 nRouter Consolidated Health Check Report",
        "",
        f"**Overall Status**: {overall_badge} | **Base URL**: `{base_url}` | **Timestamp**: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`",
        "",
        "## Summary Overview",
        "",
        "| Check Suite | Scope / Focus | Checks Run | Passed | Failed | Status |",
        "|---|---|---|---|---|---|",
        f"| **Models & Providers** | Catalog & Live Provider Inference | {len(model_result['checks'])} | {sum(1 for c in model_result['checks'] if c['passed'])} | {sum(1 for c in model_result['checks'] if not c['passed'])} | {cell(model_result, 'passed')} |",
        f"| **Guardrails & WAF** | Moderation, Injection, Secrets, Evasions | {guard_result['total_cases']} | {guard_result['passed_cases']} | {guard_result['failed_cases']} | {cell(guard_result, 'all_passed')} |",
        f"| **Endpoints & Features** | Feature Probes Across All Endpoints & Params | {feature_result['total_features']} | {feature_result['passed_features']} | {feature_result['failed_features']} | {cell(feature_result, 'all_passed')} |",
        "",
    ]
    if nothing_proven:
        lines.extend([
            "> ⚪ **Proved nothing on this plane** (not evidence, whatever the failure count): "
            + ", ".join(f"`{name}`" for name in nothing_proven),
            "",
        ])
    if not_evaluated_checks:
        lines.extend([
            "### Not-Evaluated Checks (Not Proven)",
            "",
            "> ⚠️ **NOT-EVALUATED counts as NOT PROVEN (never a pass)**: The following checks could not be "
            "evaluated from the wire alone (e.g. rate-limit store outage fail-closed 429 response lacking "
            "both `Retry-After` and `x-nr-limit-source`). The operator gateway log is the arbiter: "
            "check for `rate-limit store unreachable — REFUSING`.",
            "",
        ])
        for item in not_evaluated_checks:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend([
        "---",
        "",
    ])

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
    # `feature_failures == 0` was the aggregate's own copy of the arithmetic this
    # directory just retired: zero failures across ten modules that each proved
    # nothing is not a pass. The aggregate now reads each module's shared verdict.
    feature_all_passed = all(suite["all_passed"] for suite in feature_suites)
    print(
        f"  Result:              {'PASS' if feature_all_passed else 'FAIL'}"
        f"{' (PARTIAL: ' + str(feature_unconfigured) + ' not-configured)' if feature_unconfigured else ''}\n"
    )

    # Named per module, never averaged away.
    nothing_proven = (
        (["models"] if model_res.get("proved_nothing") else [])
        + (["guardrails"] if guard_res.get("proved_nothing") else [])
        + (["features"] if feat_res.get("proved_nothing") else [])
        + [s["feature"] for s in feature_suites if s.get("proved_nothing")]
    )

    # The same aggregation the markdown report makes: every suite, the three
    # legacy modules INCLUDED — a NOT-EVALUATED row in one of them must reach the
    # console and the JSON summary too, not only the markdown.
    not_evaluated_checks = [
        f"{s.get('feature', 'feature')}: {c.get('name', 'check')}"
        for s in feature_suites
        for c in s.get("checks", [])
        if c.get("result") == "NOT-EVALUATED" or c.get("not_evaluated")
    ] + [
        f"{label}: {c.get('name', 'check')}"
        for r, label in [(model_res, "models"), (guard_res, "guardrails"), (feat_res, "features")]
        for c in r.get("checks", [])
        if c.get("result") == "NOT-EVALUATED" or c.get("not_evaluated")
    ]

    overall_passed = (
        model_res["passed"]
        and guard_res["all_passed"]
        and feat_res["all_passed"]
        and feature_all_passed
    )

    print("============================================================")
    print(f"OVERALL STATUS:   {'🟢 ALL OPERATIONAL (PASS)' if overall_passed else '🔴 FAILURES DETECTED (FAIL)'}")
    if nothing_proven:
        print(
            "PROVED NOTHING:   ⚪ "
            + ", ".join(nothing_proven)
            + "  (a domain that proved nothing is not evidence)"
        )
    if not_evaluated_checks:
        print(
            "NOT EVALUATED:    ⚠️ "
            + ", ".join(not_evaluated_checks)
            + "  (not proven; check gateway logs: 'rate-limit store unreachable — REFUSING')"
        )
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
            # Per module, by name: a consumer reading only `overall_passed` still
            # learns which domains reached the gateway zero times.
            "proved_nothing": nothing_proven,
            "not_evaluated": not_evaluated_checks,
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
