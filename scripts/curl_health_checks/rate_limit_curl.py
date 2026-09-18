#!/usr/bin/env python3
"""nRouter Rate Limit Pure-Curl Health Check (`rate_limit_curl`).

A throughput refusal must be a POLITE refusal: it names how long to wait, it
names which ceiling refused, and it charges nothing.

  Happy path
    1. A single served request carries no `x-nr-limit-source` (nothing refused).
    2. A burst past the key's RPM produces a 429 carrying `Retry-After` > 0 and
       an `x-nr-limit-source` the spec lists.

  Adversarial
    3. The 429 carries NO `x-nr-request-cost` and no token headers.
    4. A bad key during the same burst answers 401 with `x-nr-auth-reason` —
       authentication runs BEFORE the throughput gate.
    5. The 429 body is a well-formed refusal envelope with no internal detail.
    6. `Retry-After` parses as a positive integer number of seconds.
    7. `x-nr-limit-source` is inside the spec's value list.
    8. A depleted budget answers 402 and names its source.

A plane whose key RPM is above the burst size reports NOT-CONFIGURED for the
throughput checks; it never reports PASS on an unobserved 429.

Usage:
  python3 scripts/curl_health_checks/rate_limit_curl.py --self-test
  python3 scripts/curl_health_checks/rate_limit_curl.py --quick
  python3 scripts/curl_health_checks/rate_limit_curl.py --step-summary
  python3 scripts/curl_health_checks/rate_limit_curl.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Shared plumbing: ONE curl invocation, ONE response parser, ONE credential rule.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import (  # noqa: E402
    DEFAULT_BASE_URL,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_UNRUNNABLE,
    FAIL,
    MISSING_KEY_MESSAGE,
    NOT_CONFIGURED,
    PASS,
    add_wire_arguments,
    assert_all,
    build_body,
    emit_results,
    error_of,
    json_stdout_contract_self_test,
    note_route_scope,
    parse_json,
    parser_contract_self_test,
    reported_headers,
    resolve_api_key,
    resolve_model,
    resolve_route,
    run_checks_with_scope_guard,
    run_curl,
    sanitize,
    served_body_ok,
    suite_verdict,
    wire_contract_self_test,
)

FEATURE = "rate_limit"
NOT_EVALUATED = "NOT-EVALUATED"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_BURST = 24
DEFAULT_BURST_CONCURRENCY = 8

LIMIT_SOURCE_VALUES = {
    "key",
    "plan",
    "team",
    "user",
    "budget",
    "plan_window_h8",
    "plan_window_day",
    "plan_window_week",
    "capacity",
    "plan_allowance_exhausted",
    "plan_required",
}
AUTH_REASON_VALUES = {
    "unauthorized",
    "key_blocked",
    "key_expired",
    "key_route_not_allowed",
    "key_ip_not_allowed",
    "key_network_policy_invalid",
    "auth_backend_unavailable",
}
INTERNAL_LEAK_MARKERS = (
    "Traceback",
    "panicked at",
    "thread '",
    "Caused by:",
    "postgres://",
    "password=",
    "/src/",
)
INVALID_KEY = "sk-nrouter-invalid-key-0000"


def retry_after_seconds(headers: Dict[str, str]) -> Optional[int]:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return int(float(raw.strip()))
    except ValueError:
        return None


class RateLimitCurlHealthCheck:
    """Health check runner for throughput and budget refusals."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        burst: int = DEFAULT_BURST,
        depleted_api_key: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.burst = burst
        self.depleted_api_key = depleted_api_key or os.environ.get(
            "NROUTER_DEPLETED_API_KEY", ""
        )
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []
        self._refusal: Optional[Tuple[int, Dict[str, str], str]] = None
        self._burst_ran = False
        # The burst is itself a setup step, so it reports its own outcome. A
        # burst where nothing came back does NOT mean "the ceiling is generous";
        # it means the probe never ran, and the checks that read it must FAIL.
        self._burst_stats: Dict[str, int] = {
            "sent": 0,
            "served": 0,
            "refused_429": 0,
            "other_status": 0,
            "transport_failures": 0,
        }

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self, key: Optional[str] = None, key_label: str = "$NROUTER_API_KEY"
    ) -> Tuple[List[str], str]:
        path = self.route
        self._current_path = path
        url = f"{self.base_url}{path}"
        payload = json.dumps(build_body(self.route, self.model, "ping", max_tokens=8))
        args = [
            "-H", f"Authorization: Bearer {key or self.api_key}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
            "-X", "POST",
            "-d", payload,
            url,
        ]
        shown = " \\\n".join([
            f'curl -sS -D - -X POST "$NROUTER_BASE_URL{path}"',
            f'  -H "Authorization: Bearer {key_label}"',
            '  -H "Content-Type: application/json"',
            f"  -d '{payload}'",
        ])
        return args, shown

    def _record(
        self,
        name: str,
        request: str,
        status: int,
        headers: Dict[str, str],
        assertion: str,
        ok: bool,
        expected_failure: bool,
        detail: str = "",
        not_configured: bool = False,
        not_evaluated: bool = False,
    ) -> Dict[str, Any]:
        # A 403 naming key_route_not_allowed means the request never reached the
        # behaviour under test: NOT-CONFIGURED, whatever the check wanted.
        scope_blocked = note_route_scope(self, status, headers)
        if scope_blocked:
            detail = self.scope_detail or detail
        result = (
            NOT_EVALUATED
            if not_evaluated
            else (
                NOT_CONFIGURED
                if (not_configured or scope_blocked)
                else (PASS if ok else FAIL)
            )
        )
        row = {
            "name": name,
            "request": request,
            "status": status,
            "headers": reported_headers(headers),
            "assertion": assertion,
            "result": result,
            "expected_failure": expected_failure,
        }
        if detail:
            row["detail"] = sanitize(detail)
        self.results.append(row)
        return row

    def _no_refusal_row(
        self, name: str, request: str, assertion: str, absent_detail: str
    ) -> Dict[str, Any]:
        """Record the "no 429 was observed" outcome, honestly.

        A burst that could not run is a FAIL. Only a burst that ran cleanly and
        was never refused is an absent precondition.
        """
        broken = self._burst_precondition()
        if broken:
            return self._record(
                name, request, 0, {}, assertion, False, True, detail=broken
            )
        return self._record(
            name, request, 0, {}, assertion, False, True,
            detail=absent_detail, not_configured=True,
        )

    def _burst_request_string(self) -> str:
        _, single = self._prepare()
        return (
            f"# {self.burst} concurrent copies of this request, then read the first 429\n"
            f"for i in $(seq 1 {self.burst}); do\n"
            + "\n".join(f"  {line}" for line in single.splitlines())
            + " &\ndone; wait"
        )

    def _is_store_outage(self, refusal: Optional[Tuple[int, Dict[str, str], str]]) -> bool:
        if not refusal:
            return False
        status, headers, _ = refusal
        return status == 429 and "retry-after" not in headers and "x-nr-limit-source" not in headers

    def _store_outage_row(
        self, name: str, request: str, status: int, headers: Dict[str, str], assertion: str
    ) -> Dict[str, Any]:
        return self._record(
            name, request, status, headers, assertion, False, True,
            detail="NOT-EVALUATED (store outage): the 429 response lacked both Retry-After and x-nr-limit-source",
            not_evaluated=True,
        )

    def _observe_refusal(self) -> Optional[Tuple[int, Dict[str, str], str]]:
        """Fire the burst once and keep the first throughput refusal seen."""
        if self._burst_ran:
            return self._refusal
        self._burst_ran = True
        args, _ = self._prepare()
        responses: List[Tuple[int, Dict[str, str], str]] = []
        self._burst_stats["sent"] = self.burst
        with ThreadPoolExecutor(max_workers=DEFAULT_BURST_CONCURRENCY) as pool:
            futures = [pool.submit(self.curl_fn, args) for _ in range(self.burst)]
            for future in futures:
                try:
                    status, headers, body, _ = future.result()
                except Exception:  # pragma: no cover - defensive
                    self._burst_stats["transport_failures"] += 1
                    continue
                if status == 0:
                    self._burst_stats["transport_failures"] += 1
                elif status == 429:
                    self._burst_stats["refused_429"] += 1
                elif 200 <= status < 300:
                    self._burst_stats["served"] += 1
                else:
                    self._burst_stats["other_status"] += 1
                responses.append((status, headers, body))
        for status, headers, body in responses:
            if status == 429:
                self._refusal = (status, headers, body)
                break
        return self._refusal

    def _burst_precondition(self) -> Optional[str]:
        """Why a missing 429 is NOT a provably absent precondition, if it isn't.

        Returns a failure reason when the burst itself did not run properly, and
        None when "no 429" genuinely means the ceiling is above the burst size.
        """
        stats = self._burst_stats
        if stats["transport_failures"]:
            return (
                f"{stats['transport_failures']} of {stats['sent']} burst requests failed "
                "in transport, so the ceiling was never actually exercised"
            )
        if stats["served"] == 0:
            return (
                f"none of the {stats['sent']} burst requests was served "
                f"(other statuses: {stats['other_status']}), so nothing consumed the ceiling"
            )
        return None

    # ------------------------------------------------------------ happy checks

    def check_served_request_has_no_limit_source(self) -> Dict[str, Any]:
        name = "served_request_has_no_limit_source"
        assertion = (
            "200; the wire's served body carries a completion; x-nr-limit-source ABSENT and "
            "retry-after ABSENT on a served response"
        )
        args, request = self._prepare()
        status, headers, body, _ = self.curl_fn(args)
        if status == 429:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="the plane was already rate limited before the baseline ran",
                not_configured=True,
            )
        body_ok, body_detail = served_body_ok(self.route, body)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (body_ok, body_detail),
            ("x-nr-limit-source" not in headers, "x-nr-limit-source present on a served response"),
            ("retry-after" not in headers, "retry-after present on a served response"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_burst_returns_429_with_retry_after(self) -> Dict[str, Any]:
        name = "burst_returns_429_with_retry_after"
        assertion = (
            "429 observed in the burst; Retry-After present and > 0; "
            "x-nr-limit-source present and inside the spec enum; error.type present"
        )
        refusal = self._observe_refusal()
        request = self._burst_request_string()
        if refusal is None:
            return self._no_refusal_row(
                name, request, assertion,
                f"a {self.burst}-request burst ran cleanly and produced no 429; this "
                "key's RPM ceiling is above the burst size, so the refusal path was "
                "never exercised",
            )
        status, headers, body = refusal
        if self._is_store_outage(refusal):
            return self._store_outage_row(name, request, status, headers, assertion)
        retry = retry_after_seconds(headers)
        source = headers.get("x-nr-limit-source")
        err = error_of(body)
        ok, detail = assert_all([
            (status == 429, f"expected 429, got {status}"),
            ("retry-after" in headers, "Retry-After absent on a 429"),
            (retry is not None and retry > 0, f"Retry-After {headers.get('retry-after')!r} is not > 0"),
            (source is not None, "x-nr-limit-source absent on a 429"),
            (source in LIMIT_SOURCE_VALUES, f"x-nr-limit-source {source!r} outside the spec enum"),
            (bool(err.get("type")), "error.type absent on a 429"),
            (bool(str(err.get("message", "")).strip()), "error.message empty on a 429"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ------------------------------------------------------ adversarial checks

    def check_refusal_carries_no_cost(self) -> Dict[str, Any]:
        name = "refusal_carries_no_cost"
        assertion = (
            "429; none of x-nr-request-cost, x-nr-cost-status, x-nr-input-tokens, "
            "x-nr-output-tokens, x-nr-total-tokens is present (a refused request spends $0)"
        )
        refusal = self._observe_refusal()
        request = self._burst_request_string()
        if refusal is None:
            return self._no_refusal_row(
                name, request, assertion,
                "the burst ran cleanly and was never refused, so no 429 cost headers exist to inspect",
            )
        status, headers, _ = refusal
        if self._is_store_outage(refusal):
            return self._store_outage_row(name, request, status, headers, assertion)
        leaked = [
            header
            for header in (
                "x-nr-request-cost",
                "x-nr-cost-status",
                "x-nr-input-tokens",
                "x-nr-output-tokens",
                "x-nr-total-tokens",
            )
            if header in headers
        ]
        ok, detail = assert_all([
            (status == 429, f"expected 429, got {status}"),
            (not leaked, f"metering headers present on a refusal: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_auth_failure_precedes_rate_limit(self) -> Dict[str, Any]:
        name = "auth_failure_precedes_rate_limit"
        assertion = (
            "401 (never 429); x-nr-auth-reason present and inside the spec enum; "
            "error.type present; no cost header"
        )
        args, request = self._prepare(key=INVALID_KEY, key_label="sk-nrouter-invalid-key-0000")
        status, headers, body, _ = self.curl_fn(args)
        reason = headers.get("x-nr-auth-reason")
        err = error_of(body)
        ok, detail = assert_all([
            (status == 401, f"expected 401, got {status}"),
            (status != 429, "an unauthenticated caller was rate limited instead of refused"),
            (reason is not None, "x-nr-auth-reason absent on a 401"),
            (reason in AUTH_REASON_VALUES, f"x-nr-auth-reason {reason!r} outside the spec enum"),
            (bool(err.get("type")), "error.type absent on a 401"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a 401"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_refusal_body_leaks_nothing_internal(self) -> Dict[str, Any]:
        name = "refusal_body_leaks_nothing_internal"
        assertion = (
            "429; error.type and error.message present; body carries no stack trace, "
            "connection string, upstream hostname or provider header name"
        )
        refusal = self._observe_refusal()
        request = self._burst_request_string()
        if refusal is None:
            return self._no_refusal_row(
                name, request, assertion,
                "the burst ran cleanly and was never refused, so no 429 body exists to inspect",
            )
        status, headers, body = refusal
        if self._is_store_outage(refusal):
            return self._store_outage_row(name, request, status, headers, assertion)
        err = error_of(body)
        leaked = [marker for marker in INTERNAL_LEAK_MARKERS if marker in body]
        provider_leak = [
            header for header in headers if header.startswith(("openai-", "anthropic-", "x-ratelimit-"))
        ]
        ok, detail = assert_all([
            (status == 429, f"expected 429, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            (not leaked, f"refusal body carries internal detail: {leaked}"),
            (not provider_leak, f"upstream provider headers survived egress stripping: {provider_leak}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_retry_after_is_positive_integer(self) -> Dict[str, Any]:
        name = "retry_after_is_positive_integer"
        assertion = (
            "429; Retry-After parses as an integer number of seconds, strictly > 0 "
            "and <= 3600 (a client can actually wait it out)"
        )
        refusal = self._observe_refusal()
        request = self._burst_request_string()
        if refusal is None:
            return self._no_refusal_row(
                name, request, assertion,
                "the burst ran cleanly and was never refused, so there was no Retry-After to parse",
            )
        status, headers, _ = refusal
        if self._is_store_outage(refusal):
            return self._store_outage_row(name, request, status, headers, assertion)
        raw = headers.get("retry-after")
        retry = retry_after_seconds(headers)
        ok, detail = assert_all([
            (status == 429, f"expected 429, got {status}"),
            (raw is not None, "Retry-After absent"),
            (retry is not None, f"Retry-After {raw!r} does not parse as seconds"),
            (retry is not None and 0 < retry <= 3600, f"Retry-After {raw!r} outside 1..3600 seconds"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_limit_source_value_in_spec(self) -> Dict[str, Any]:
        name = "limit_source_value_in_spec"
        assertion = "429; x-nr-limit-source is exactly one of the values the spec publishes"
        refusal = self._observe_refusal()
        request = self._burst_request_string()
        if refusal is None:
            return self._no_refusal_row(
                name, request, assertion,
                "the burst ran cleanly and was never refused, so there was no x-nr-limit-source to read",
            )
        status, headers, _ = refusal
        if self._is_store_outage(refusal):
            return self._store_outage_row(name, request, status, headers, assertion)
        source = headers.get("x-nr-limit-source")
        ok, detail = assert_all([
            (status == 429, f"expected 429, got {status}"),
            (source is not None, "x-nr-limit-source absent on a 429"),
            (
                source in LIMIT_SOURCE_VALUES,
                f"x-nr-limit-source {source!r} is not in {sorted(LIMIT_SOURCE_VALUES)}",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_depleted_budget_names_its_source(self) -> Dict[str, Any]:
        name = "depleted_budget_names_its_source"
        assertion = (
            "402; x-nr-limit-source present and inside the spec enum; error.type "
            "present; no cost header (nothing was spent)"
        )
        if not self.depleted_api_key:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail="NROUTER_DEPLETED_API_KEY unset: no exhausted-budget key on this plane",
                not_configured=True,
            )
        args, request = self._prepare(
            key=self.depleted_api_key, key_label="$NROUTER_DEPLETED_API_KEY"
        )
        status, headers, body, _ = self.curl_fn(args)
        source = headers.get("x-nr-limit-source")
        err = error_of(body)
        ok, detail = assert_all([
            (status == 402, f"expected 402, got {status}"),
            (source is not None, "x-nr-limit-source absent on a 402"),
            (source in LIMIT_SOURCE_VALUES, f"x-nr-limit-source {source!r} outside the spec enum"),
            (bool(err.get("type")), "error.type absent on a 402"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a 402"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        self._refusal = None
        self._burst_ran = False
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_served_request_has_no_limit_source,
            self.check_auth_failure_precedes_rate_limit,
        ]
        if not quick:
            checks = [
                self.check_served_request_has_no_limit_source,
                self.check_burst_returns_429_with_retry_after,
                self.check_refusal_carries_no_cost,
                self.check_auth_failure_precedes_rate_limit,
                self.check_refusal_body_leaks_nothing_internal,
                self.check_retry_after_is_positive_integer,
                self.check_limit_source_value_in_spec,
                self.check_depleted_budget_names_its_source,
            ]
        run_checks_with_scope_guard(self, checks)
        return self.summarize()

    def summarize(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r["result"] == PASS)
        failed = sum(1 for r in self.results if r["result"] == FAIL)
        unconfigured = sum(1 for r in self.results if r["result"] == NOT_CONFIGURED)
        not_evaluated = sum(1 for r in self.results if r["result"] == NOT_EVALUATED)
        return {
            "feature": FEATURE,
            "base_url": self.base_url,
            "route": self.route,
            "model": self.model,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checks": self.results,
            "total_checks": len(self.results),
            "passed_checks": passed,
            "failed_checks": failed,
            "not_configured_checks": unconfigured,
            "not_evaluated_checks": not_evaluated,
            "adversarial_checks": sum(1 for r in self.results if r["expected_failure"]),
            # The ONE verdict rule, shared by every module and by run_all.py:
            # nothing failed AND something was actually proven. See
            # `_curl_common.suite_verdict`.
            **suite_verdict(passed, failed, unconfigured, not_evaluated),
        }

    def render_markdown_summary(self, suite: Dict[str, Any]) -> str:
        badge = "🟢 **PASSED**" if suite["all_passed"] else "🔴 **FAILED**"
        if suite["all_passed"] and suite["partial"]:
            if suite.get("not_evaluated_checks", 0) > 0 and not suite.get("not_configured_checks", 0):
                badge = "🟡 **PARTIAL (checks not evaluated on this plane)**"
            elif suite.get("not_evaluated_checks", 0) > 0:
                badge = "🟡 **PARTIAL (checks not configured / not evaluated on this plane)**"
            else:
                badge = "🟡 **PARTIAL (checks not configured on this plane)**"
        lines = [
            "## 🚦 nRouter Pure-Curl Health Check: Rate Limits",
            "",
            f"**Status**: {badge} | **Base URL**: `{suite['base_url']}` | "
            f"**Route**: `{suite['route']}` | **Model**: `{suite['model']}` | "
            f"**Adversarial**: {suite['adversarial_checks']}/{suite['total_checks']}",
            "",
            "| Check | Adversarial | HTTP | Result | Assertion | Detail |",
            "|---|---|---|---|---|---|",
        ]
        for row in suite["checks"]:
            icon = {PASS: "✅", FAIL: "❌", NOT_CONFIGURED: "⚪", NOT_EVALUATED: "⚠️"}.get(row["result"], "⚪")
            lines.append(
                f"| `{row['name']}` | {'yes' if row['expected_failure'] else 'no'} | "
                f"{row['status']} | {icon} {row['result']} | {row['assertion']} | "
                f"{row.get('detail', '')} |"
            )
        return "\n".join(lines)


def run_self_test() -> int:
    print("Running rate_limit_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

    def auth_of(args: List[str]) -> str:
        for index, arg in enumerate(args):
            if arg == "-H" and args[index + 1].lower().startswith("authorization:"):
                return args[index + 1].split(" ", 2)[-1]
        return ""

    def make_backend(rpm: int = 3) -> Callable:
        state = {"served": 0}

        def mock_curl(args, timeout_s=40, stdin_data=None):
            key = auth_of(args)
            base = {"x-nr-request-id": "dddddddd-0000-1111-2222-333333333333"}
            if key == INVALID_KEY:
                headers = dict(base)
                headers["x-nr-auth-reason"] = "unauthorized"
                return 401, headers, json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
                ), 3.0
            if key == "sk-nrouter-depleted":
                headers = dict(base)
                headers["x-nr-limit-source"] = "budget"
                return 402, headers, json.dumps(
                    {"error": {"type": "gateway_error", "message": "insufficient credits"}}
                ), 4.0
            state["served"] += 1
            if state["served"] > rpm:
                headers = dict(base)
                headers.update({"retry-after": "12", "x-nr-limit-source": "key"})
                return 429, headers, json.dumps(
                    {"error": {"type": "gateway_error", "message": "rate limit exceeded"}}
                ), 3.0
            headers = dict(base)
            headers.update({
                "x-nr-model": DEFAULT_MODEL,
                "x-nr-request-cost": "0.000021",
                "x-nr-cost-status": "exact",
            })
            if args[-1].endswith("/messages"):
                return 200, headers, json.dumps(
                    {"content": [{"type": "text", "text": "pong"}]}
                ), 30.0
            return 200, headers, json.dumps({"choices": [{"message": {"content": "pong"}}]}), 30.0

        return mock_curl

    checker = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        burst=12,
        depleted_api_key="sk-nrouter-depleted",
        curl_fn=make_backend(),
    )
    suite = checker.run_suite()
    assert suite["feature"] == FEATURE
    assert suite["total_checks"] == 8, suite["total_checks"]
    assert suite["adversarial_checks"] >= 6, suite["adversarial_checks"]
    assert suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in suite["checks"] if r["result"] == FAIL
    ]
    for row in suite["checks"]:
        assert {"name", "request", "status", "headers", "assertion", "result", "expected_failure"} <= set(row)
        assert "sk-nrouter-mock-key" not in row["request"], "raw key leaked into report"

    # BITE 1: a 429 without Retry-After must go red.
    def no_retry_after() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status == 429:
                headers = {k: v for k, v in headers.items() if k != "retry-after"}
            return status, headers, body, latency

        return mock

    blunt = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=12, curl_fn=no_retry_after()
    )
    assert blunt.run_suite()["all_passed"] is False, "a 429 without Retry-After must fail"

    # A 429 lacking BOTH Retry-After and x-nr-limit-source is a store outage => NOT-EVALUATED
    def mock_store_outage_429() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status == 429:
                headers = {k: v for k, v in headers.items() if k not in ("retry-after", "x-nr-limit-source")}
            return status, headers, body, latency

        return mock

    outage = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        burst=12,
        depleted_api_key="sk-nrouter-depleted",
        curl_fn=mock_store_outage_429(),
    )
    outage_suite = outage.run_suite()
    outage_row = next(r for r in outage_suite["checks"] if r["name"] == "burst_returns_429_with_retry_after")
    assert outage_row["result"] == "NOT-EVALUATED", outage_row["result"]
    assert "NOT-EVALUATED (store outage)" in outage_row["detail"], outage_row["detail"]
    assert outage_row["result"] != FAIL and outage_row["result"] != PASS
    assert outage_suite["not_configured_checks"] == 0, outage_suite["not_configured_checks"]
    assert outage_suite["not_evaluated_checks"] > 0, outage_suite["not_evaluated_checks"]
    assert outage_suite["partial"] is True, outage_suite["partial"]

    # BITE 2: a billed refusal must go red.
    def billed_refusal() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status == 429:
                headers = dict(headers)
                headers["x-nr-request-cost"] = "0.000005"
            return status, headers, body, latency

        return mock

    billed = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=12, curl_fn=billed_refusal()
    )
    billed_suite = billed.run_suite()
    cost_row = next(r for r in billed_suite["checks"] if r["name"] == "refusal_carries_no_cost")
    assert cost_row["result"] == FAIL, "a billed 429 must fail"

    # BITE 3: a stack trace in the refusal body must go red.
    def leaky_body() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status == 429:
                body = json.dumps({
                    "error": {
                        "type": "gateway_error",
                        "message": "rate limit exceeded\nTraceback (most recent call last)",
                    }
                })
            return status, headers, body, latency

        return mock

    leaky = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=12, curl_fn=leaky_body()
    )
    leak_row = next(
        r for r in leaky.run_suite()["checks"] if r["name"] == "refusal_body_leaks_nothing_internal"
    )
    assert leak_row["result"] == FAIL, "an internal leak in a refusal body must fail"

    # NOT-CONFIGURED, never PASS, when the burst never trips a ceiling.
    generous = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=4, curl_fn=make_backend(rpm=10_000)
    )
    generous_suite = generous.run_suite()
    burst_row = next(
        r for r in generous_suite["checks"] if r["name"] == "burst_returns_429_with_retry_after"
    )
    assert burst_row["result"] == NOT_CONFIGURED, burst_row["result"]
    assert generous_suite["all_passed"] is True, "an unobserved ceiling is PARTIAL, not a failure"

    # ...but a burst that could not RUN is a FAIL, not an absent precondition.
    # Without this, a gateway that refuses the probe in transport looks exactly
    # like a gateway with a generous ceiling.
    def burst_never_lands(args, timeout_s=40, stdin_data=None):
        if auth_of(args) == INVALID_KEY:
            return 401, {"x-nr-request-id": "a", "x-nr-auth-reason": "unauthorized"}, json.dumps(
                {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
            ), 2.0
        return 0, {}, "curl exit code 56: Recv failure", 10.0

    unlanded = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=6, curl_fn=burst_never_lands
    )
    unlanded_suite = unlanded.run_suite()
    for check_name in (
        "burst_returns_429_with_retry_after",
        "refusal_carries_no_cost",
        "refusal_body_leaks_nothing_internal",
        "retry_after_is_positive_integer",
        "limit_source_value_in_spec",
    ):
        row = next(r for r in unlanded_suite["checks"] if r["name"] == check_name)
        assert row["result"] == FAIL, (
            f"{check_name}: a burst that failed in transport must FAIL, not report "
            f"NOT-CONFIGURED; got {row['result']}"
        )
        assert "transport" in row.get("detail", ""), row.get("detail")

    # A burst where every request is refused with a non-429 status also never
    # exercised the ceiling, and must not be excused as "generous".
    def burst_always_500(args, timeout_s=40, stdin_data=None):
        if auth_of(args) == INVALID_KEY:
            return 401, {"x-nr-request-id": "a", "x-nr-auth-reason": "unauthorized"}, json.dumps(
                {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
            ), 2.0
        return 500, {"x-nr-request-id": "b"}, json.dumps(
            {"error": {"type": "gateway_error", "message": "upstream unavailable"}}
        ), 10.0

    broken = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=6, curl_fn=burst_always_500
    )
    broken_row = next(
        r for r in broken.run_suite()["checks"] if r["name"] == "burst_returns_429_with_retry_after"
    )
    assert broken_row["result"] == FAIL, (
        f"a burst where nothing was served must FAIL; got {broken_row['result']}"
    )

    # BOTH WIRES: the served baseline must read the Anthropic-shaped body too.
    messages_suite = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001", burst=12,
        depleted_api_key="sk-nrouter-depleted", curl_fn=make_backend(),
    ).run_suite()
    assert messages_suite["route"] == "/messages"
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]

    # A route-scoped key short-circuits as NOT-CONFIGURED, not as failures.
    def mock_route_not_allowed(args, timeout_s=40, stdin_data=None):
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = RateLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", burst=4, curl_fn=mock_route_not_allowed
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert any(
        "NROUTER_HEALTH_ROUTE" in r.get("detail", "") for r in scoped_suite["checks"]
    ), "the scope refusal must name the override to set"
    # ...and that suite proved NOTHING, so it must never read as passing. Under
    # `all_passed = failed == 0` this was green: zero failures, zero proof, and a
    # CI gate reading `all_passed` waved it through as release evidence.
    assert scoped_suite["not_configured_checks"] == scoped_suite["total_checks"], scoped_suite
    assert scoped_suite["all_passed"] is False, (
        "an all-NOT-CONFIGURED suite proved nothing and must not report all_passed"
    )
    assert scoped_suite["proved_nothing"] is True, scoped_suite["passed_checks"]

    assert "Rate Limits" in checker.render_markdown_summary(suite)
    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] rate_limit_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Rate Limit Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)
    parser.add_argument("--burst", type=int, default=DEFAULT_BURST)
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return EXIT_UNRUNNABLE

    try:
        checker = RateLimitCurlHealthCheck(
            base_url=args.base_url, api_key=api_key,
            route=args.route, model=args.model, burst=args.burst,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Rate Limit Curl Health Check ===\n"
        f"Base URL: {args.base_url} | route: {checker.route} | "
        f"model: {checker.model} | burst: {args.burst}",
        file=sys.stderr if args.json else sys.stdout,
    )
    suite = checker.run_suite(quick=args.quick)
    return emit_results(
        suite,
        checker.render_markdown_summary(suite),
        as_json=args.json,
        step_summary=args.step_summary,
    )


if __name__ == "__main__":
    sys.exit(main())
