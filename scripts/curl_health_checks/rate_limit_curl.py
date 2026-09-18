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
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FEATURE = "rate_limit"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_BURST = 24
DEFAULT_BURST_CONCURRENCY = 8

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

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

SECRET_PATTERNS = [
    re.compile(r"sk-nrouter-[A-Za-z0-9_-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]
REPORTED_HEADERS = ("content-type", "cache-control", "retry-after", "x-content-type-options")


def sanitize(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def run_curl(
    args: List[str],
    timeout_s: int = 40,
    stdin_data: Optional[str] = None,
) -> Tuple[int, Dict[str, str], str, float]:
    """Execute raw curl and parse status, headers, body and latency."""
    cmd = ["curl", "-sS", "-D", "-"] + args
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
        latency = round((time.monotonic() - start) * 1000.0, 1)
        raw = proc.stdout
    except subprocess.TimeoutExpired:
        return 0, {}, "Request timed out", round((time.monotonic() - start) * 1000.0, 1)
    except Exception as exc:  # pragma: no cover - defensive
        return 0, {}, f"Subprocess error: {exc}", 0.0

    if proc.returncode != 0 and not raw:
        return 0, {}, f"curl exit code {proc.returncode}: {proc.stderr.strip()}", latency

    parts = raw.split("\r\n\r\n")
    if len(parts) == 1:
        parts = raw.split("\n\n")
    header_block = ""
    for part in parts[:-1]:
        if part.startswith("HTTP/") or "\nHTTP/" in part or "\r\nHTTP/" in part:
            header_block = part
    body = parts[-1] if parts else ""

    headers: Dict[str, str] = {}
    status = 0
    for line in header_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("HTTP/"):
            match = re.match(r"^HTTP/[0-9.]+\s+(\d+)", line)
            if match:
                status = int(match.group(1))
        elif ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers, body, latency


def assert_all(conditions: List[Tuple[bool, str]]) -> Tuple[bool, str]:
    failed = [message for ok, message in conditions if not ok]
    return (not failed, "; ".join(failed))


def parse_json(body: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def error_of(body: str) -> Dict[str, Any]:
    err = parse_json(body).get("error")
    return err if isinstance(err, dict) else {}


def retry_after_seconds(headers: Dict[str, str]) -> Optional[int]:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return int(float(raw.strip()))
    except ValueError:
        return None


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class RateLimitCurlHealthCheck:
    """Health check runner for throughput and budget refusals."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        burst: int = DEFAULT_BURST,
        depleted_api_key: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.model = model
        self.burst = burst
        self.depleted_api_key = depleted_api_key or os.environ.get(
            "NROUTER_DEPLETED_API_KEY", ""
        )
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []
        self._refusal: Optional[Tuple[int, Dict[str, str], str]] = None
        self._burst_ran = False

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self, key: Optional[str] = None, key_label: str = "$NROUTER_API_KEY"
    ) -> Tuple[List[str], str]:
        path = "/chat/completions"
        url = f"{self.base_url}{path}"
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        })
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
    ) -> Dict[str, Any]:
        row = {
            "name": name,
            "request": request,
            "status": status,
            "headers": reported_headers(headers),
            "assertion": assertion,
            "result": NOT_CONFIGURED if not_configured else (PASS if ok else FAIL),
            "expected_failure": expected_failure,
        }
        if detail:
            row["detail"] = sanitize(detail)
        self.results.append(row)
        return row

    def _burst_request_string(self) -> str:
        _, single = self._prepare()
        return (
            f"# {self.burst} concurrent copies of this request, then read the first 429\n"
            f"for i in $(seq 1 {self.burst}); do\n"
            + "\n".join(f"  {line}" for line in single.splitlines())
            + " &\ndone; wait"
        )

    def _observe_refusal(self) -> Optional[Tuple[int, Dict[str, str], str]]:
        """Fire the burst once and keep the first throughput refusal seen."""
        if self._burst_ran:
            return self._refusal
        self._burst_ran = True
        args, _ = self._prepare()
        responses: List[Tuple[int, Dict[str, str], str]] = []
        with ThreadPoolExecutor(max_workers=DEFAULT_BURST_CONCURRENCY) as pool:
            futures = [pool.submit(self.curl_fn, args) for _ in range(self.burst)]
            for future in futures:
                try:
                    status, headers, body, _ = future.result()
                except Exception:  # pragma: no cover - defensive
                    continue
                responses.append((status, headers, body))
        for status, headers, body in responses:
            if status == 429:
                self._refusal = (status, headers, body)
                break
        return self._refusal

    # ------------------------------------------------------------ happy checks

    def check_served_request_has_no_limit_source(self) -> Dict[str, Any]:
        name = "served_request_has_no_limit_source"
        assertion = (
            "200; body.choices non-empty; x-nr-limit-source ABSENT and "
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
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
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
            return self._record(
                name, request, 0, {}, assertion, False, True,
                detail=(
                    f"a {self.burst}-request burst produced no 429; this key's RPM "
                    "ceiling is above the burst size, so the refusal path was never exercised"
                ),
                not_configured=True,
            )
        status, headers, body = refusal
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
            return self._record(
                name, request, 0, {}, assertion, False, True,
                detail="no 429 was observed, so its cost headers could not be inspected",
                not_configured=True,
            )
        status, headers, _ = refusal
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
            return self._record(
                name, request, 0, {}, assertion, False, True,
                detail="no 429 was observed, so its body could not be inspected",
                not_configured=True,
            )
        status, headers, body = refusal
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
            return self._record(
                name, request, 0, {}, assertion, False, True,
                detail="no 429 was observed, so Retry-After could not be parsed",
                not_configured=True,
            )
        status, headers, _ = refusal
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
            return self._record(
                name, request, 0, {}, assertion, False, True,
                detail="no 429 was observed, so x-nr-limit-source could not be read",
                not_configured=True,
            )
        status, headers, _ = refusal
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
        for check in checks:
            check()
        return self.summarize()

    def summarize(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r["result"] == PASS)
        failed = sum(1 for r in self.results if r["result"] == FAIL)
        unconfigured = sum(1 for r in self.results if r["result"] == NOT_CONFIGURED)
        return {
            "feature": FEATURE,
            "base_url": self.base_url,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checks": self.results,
            "total_checks": len(self.results),
            "passed_checks": passed,
            "failed_checks": failed,
            "not_configured_checks": unconfigured,
            "adversarial_checks": sum(1 for r in self.results if r["expected_failure"]),
            "all_passed": failed == 0,
            "partial": unconfigured > 0,
        }

    def render_markdown_summary(self, suite: Dict[str, Any]) -> str:
        badge = "🟢 **PASSED**" if suite["all_passed"] else "🔴 **FAILED**"
        if suite["all_passed"] and suite["partial"]:
            badge = "🟡 **PARTIAL (checks not configured on this plane)**"
        lines = [
            "## 🚦 nRouter Pure-Curl Health Check: Rate Limits",
            "",
            f"**Status**: {badge} | **Base URL**: `{suite['base_url']}` | "
            f"**Adversarial**: {suite['adversarial_checks']}/{suite['total_checks']}",
            "",
            "| Check | Adversarial | HTTP | Result | Assertion | Detail |",
            "|---|---|---|---|---|---|",
        ]
        for row in suite["checks"]:
            icon = {PASS: "✅", FAIL: "❌", NOT_CONFIGURED: "⚪"}[row["result"]]
            lines.append(
                f"| `{row['name']}` | {'yes' if row['expected_failure'] else 'no'} | "
                f"{row['status']} | {icon} {row['result']} | {row['assertion']} | "
                f"{row.get('detail', '')} |"
            )
        return "\n".join(lines)


def run_self_test() -> int:
    print("Running rate_limit_curl.py --self-test (offline mode)...")

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

    assert "Rate Limits" in checker.render_markdown_summary(suite)
    print("[PASS] rate_limit_curl.py self-test passed cleanly.")
    return 0


def resolve_api_key(explicit: str) -> str:
    if explicit:
        return explicit
    creds = Path.home() / ".nrouter_admin_keys/nrouter-test/prod/credentials.env"
    if creds.is_file():
        try:
            match = re.search(r'NROUTER_TEST_API_KEY=["\']?([^"\'\n]+)["\']?', creds.read_text())
            if match:
                return match.group(1)
        except Exception:
            return ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Rate Limit Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--burst", type=int, default=DEFAULT_BURST)
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        return 1

    checker = RateLimitCurlHealthCheck(
        base_url=args.base_url, api_key=api_key, model=args.model, burst=args.burst
    )
    print("=== nRouter Rate Limit Curl Health Check ===")
    print(f"Base URL: {args.base_url} | burst: {args.burst}")
    suite = checker.run_suite(quick=args.quick)
    for row in suite["checks"]:
        print(f"[{row['result']}] {row['name']} - HTTP {row['status']}")
        if row.get("detail"):
            print(f"        {row['detail']}")
    print(
        f"Checks: {suite['total_checks']} | passed {suite['passed_checks']} | "
        f"failed {suite['failed_checks']} | not-configured {suite['not_configured_checks']}"
    )

    if args.step_summary:
        target = os.environ.get("GITHUB_STEP_SUMMARY")
        if target:
            try:
                with open(target, "a") as handle:
                    handle.write("\n" + checker.render_markdown_summary(suite) + "\n")
            except Exception as exc:
                print(f"Warning: could not write step summary: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(suite, indent=2))

    return 0 if suite["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
