#!/usr/bin/env python3
"""nRouter Request Identity Pure-Curl Health Check (`tracing_curl`).

`x-nr-request-id` is the one thread that ties a customer's support ticket to a
spend row. It must exist on EVERY response the gateway produces, success or
refusal, it must be a UUID, and it must be the gateway's own — never a value a
caller supplied.

  Happy path
    1. A served response carries a UUID `x-nr-request-id`.
    2. A served response names the model in `x-nr-model`.
    3. `x-nr-latency-ms` is an integer on a served response.

  Adversarial
    4. A 400 refusal still carries a UUID request id.
    5. Two requests never share a request id.
    6. A refusal carries no `x-nr-routing` and no `x-nr-attempts`.
    7. A 401 still carries a UUID request id (support can trace a bad key).
    8. A caller-supplied `x-nr-request-id` is OVERWRITTEN, never echoed.
    9. A refusal body leaks no stack trace, host or connection detail.
   10. `x-nr-trace-id`, when present, is lowercase hex of a plausible length.

Usage:
  python3 scripts/curl_health_checks/tracing_curl.py --self-test
  python3 scripts/curl_health_checks/tracing_curl.py --quick
  python3 scripts/curl_health_checks/tracing_curl.py --step-summary
  python3 scripts/curl_health_checks/tracing_curl.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
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
    wire_contract_self_test,
)

FEATURE = "tracing"
DEFAULT_MODEL = "openai/gpt-4o-mini"
INVALID_KEY = "sk-nrouter-invalid-key-0000"
FORGED_REQUEST_ID = "deadbeef-dead-beef-dead-beefdeadbeef"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
TRACE_ID_RE = re.compile(r"^[0-9a-f]{16,32}$")
INTERNAL_LEAK_MARKERS = (
    "Traceback",
    "panicked at",
    "thread '",
    "Caused by:",
    "postgres://",
    "password=",
    "/src/",
    ".rs:",
)


class TracingCurlHealthCheck:
    """Health check runner for request identity and trace correlation."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self,
        body: Any,
        key: Optional[str] = None,
        key_label: str = "$NROUTER_API_KEY",
        extra_headers: Optional[List[Tuple[str, str]]] = None,
        raw_body: Optional[str] = None,
    ) -> Tuple[List[str], str]:
        path = self.route
        self._current_path = path
        url = f"{self.base_url}{path}"
        payload = raw_body if raw_body is not None else json.dumps(body)
        args = [
            "-H", f"Authorization: Bearer {key or self.api_key}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
        ]
        shown = [
            f'curl -sS -D - -X POST "$NROUTER_BASE_URL{path}"',
            f'  -H "Authorization: Bearer {key_label}"',
            '  -H "Content-Type: application/json"',
        ]
        for header_name, header_value in extra_headers or []:
            args += ["-H", f"{header_name}: {header_value}"]
            shown.append(f'  -H "{header_name}: {header_value}"')
        args += ["-X", "POST", "-d", payload, url]
        shown.append(f"  -d '{payload}'")
        return args, " \\\n".join(shown)

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
        # A 403 naming key_route_not_allowed means the request never reached the
        # behaviour under test: NOT-CONFIGURED, whatever the check wanted.
        scope_blocked = note_route_scope(self, status, headers)
        if scope_blocked:
            detail = self.scope_detail or detail
        row = {
            "name": name,
            "request": request,
            "status": status,
            "headers": reported_headers(headers),
            "assertion": assertion,
            "result": (
                NOT_CONFIGURED
                if (not_configured or scope_blocked)
                else (PASS if ok else FAIL)
            ),
            "expected_failure": expected_failure,
        }
        if detail:
            row["detail"] = sanitize(detail)
        self.results.append(row)
        return row

    def _chat(self, prompt: str = "ping") -> Dict[str, Any]:
        return build_body(self.route, self.model, prompt, max_tokens=8)

    # ------------------------------------------------------------ happy checks

    def check_request_id_on_served_response(self) -> Dict[str, Any]:
        name = "request_id_on_served_response"
        assertion = (
            "200; x-nr-request-id present and a canonical UUID; the wire's "
            "served body carries a completion"
        )
        args, request = self._prepare(self._chat())
        status, headers, body, _ = self.curl_fn(args)
        request_id = headers.get("x-nr-request-id")
        body_ok, body_detail = served_body_ok(self.route, body)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (request_id is not None, "x-nr-request-id absent on a served response"),
            (
                request_id is not None and bool(UUID_RE.match(request_id)),
                f"x-nr-request-id {request_id!r} is not a UUID",
            ),
            (body_ok, body_detail),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_model_header_on_served_response(self) -> Dict[str, Any]:
        name = "model_header_on_served_response"
        assertion = (
            "200; x-nr-model present and non-empty; it names an nRouter alias, "
            "never a bare upstream deployment identifier"
        )
        args, request = self._prepare(self._chat())
        status, headers, _, _ = self.curl_fn(args)
        model = headers.get("x-nr-model")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (bool(model), "x-nr-model absent on a served response"),
            (
                model is None or not model.startswith(("deployment-", "azure-", "arn:")),
                f"x-nr-model {model!r} looks like an internal deployment identifier",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_latency_header_is_integer(self) -> Dict[str, Any]:
        name = "latency_header_is_integer"
        assertion = (
            "200; x-nr-latency-ms present (the spec marks it ALWAYS emitted, so its "
            "absence is a contract break, not a missing fixture) and a non-negative "
            "integer under an hour"
        )
        args, request = self._prepare(self._chat())
        status, headers, _, _ = self.curl_fn(args)
        raw = headers.get("x-nr-latency-ms")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (raw is not None, "x-nr-latency-ms absent, but the spec marks it always emitted"),
            (raw is not None and raw.isdigit(), f"x-nr-latency-ms {raw!r} is not an integer"),
            (
                raw is not None and raw.isdigit() and 0 <= int(raw) <= 3_600_000,
                f"x-nr-latency-ms {raw!r} outside 0..3600000 ms",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def check_request_id_on_refusal(self) -> Dict[str, Any]:
        name = "request_id_on_refusal"
        assertion = (
            "400; x-nr-request-id present and a UUID; error.type present "
            "(a refusal is traceable too)"
        )
        args, request = self._prepare(
            None, raw_body=json.dumps({"model": self.model, "messages": "not-an-array"})
        )
        status, headers, body, _ = self.curl_fn(args)
        request_id = headers.get("x-nr-request-id")
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (request_id is not None, "x-nr-request-id absent on a refusal"),
            (
                request_id is not None and bool(UUID_RE.match(request_id)),
                f"x-nr-request-id {request_id!r} is not a UUID",
            ),
            (bool(err.get("type")), "error.type absent"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_request_ids_are_unique(self) -> Dict[str, Any]:
        name = "request_ids_are_unique"
        assertion = (
            "both responses answer 200 or 400; both carry x-nr-request-id; the two "
            "values DIFFER; the second is a canonical UUID (a shared id collapses "
            "two spend rows into one)"
        )
        first_args, _ = self._prepare(self._chat("ping one"))
        first_status, first_headers, _, _ = self.curl_fn(first_args)
        second_args, request = self._prepare(self._chat("ping one"))
        status, headers, _, _ = self.curl_fn(second_args)
        first_id = first_headers.get("x-nr-request-id")
        second_id = headers.get("x-nr-request-id")
        ok, detail = assert_all([
            (first_status in (200, 400), f"unexpected first status {first_status}"),
            (status in (200, 400), f"unexpected second status {status}"),
            (first_id is not None and second_id is not None, "a response carried no x-nr-request-id"),
            (first_id != second_id, f"two requests shared the request id {first_id!r}"),
            (
                second_id is not None and bool(UUID_RE.match(second_id)),
                f"x-nr-request-id {second_id!r} is not a UUID",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_refusal_has_no_routing_headers(self) -> Dict[str, Any]:
        name = "refusal_has_no_routing_headers"
        assertion = (
            "400; x-nr-routing and x-nr-attempts ABSENT; x-nr-request-id still "
            "present (identity survives, routing claims do not)"
        )
        args, request = self._prepare(
            None, raw_body=json.dumps({"model": self.model, "messages": "not-an-array"})
        )
        status, headers, _, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            ("x-nr-routing" not in headers, "x-nr-routing present on a refusal"),
            ("x-nr-attempts" not in headers, "x-nr-attempts present on a refusal"),
            (bool(headers.get("x-nr-request-id")), "x-nr-request-id absent on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_request_id_on_unauthorized(self) -> Dict[str, Any]:
        name = "request_id_on_unauthorized"
        assertion = (
            "401; x-nr-request-id present and a UUID; x-nr-auth-reason present; "
            "no cost header"
        )
        args, request = self._prepare(
            self._chat(), key=INVALID_KEY, key_label="sk-nrouter-invalid-key-0000"
        )
        status, headers, _, _ = self.curl_fn(args)
        request_id = headers.get("x-nr-request-id")
        ok, detail = assert_all([
            (status == 401, f"expected 401, got {status}"),
            (request_id is not None, "x-nr-request-id absent on a 401"),
            (
                request_id is not None and bool(UUID_RE.match(request_id)),
                f"x-nr-request-id {request_id!r} is not a UUID",
            ),
            (bool(headers.get("x-nr-auth-reason")), "x-nr-auth-reason absent on a 401"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a 401"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_client_supplied_request_id_is_overwritten(self) -> Dict[str, Any]:
        name = "client_supplied_request_id_is_overwritten"
        assertion = (
            "200; the response x-nr-request-id is the gateway's own, NEVER the "
            "value the caller sent (a caller that picks its own id can collide "
            "with, or overwrite, another tenant's trace)"
        )
        args, request = self._prepare(
            self._chat(), extra_headers=[("x-nr-request-id", FORGED_REQUEST_ID)]
        )
        status, headers, _, _ = self.curl_fn(args)
        request_id = headers.get("x-nr-request-id")
        ok, detail = assert_all([
            (status in (200, 400), f"unexpected status {status}"),
            (request_id is not None, "x-nr-request-id absent"),
            (
                request_id != FORGED_REQUEST_ID,
                "the gateway echoed a caller-supplied x-nr-request-id",
            ),
            (
                request_id is not None and bool(UUID_RE.match(request_id)),
                f"x-nr-request-id {request_id!r} is not a UUID",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_refusal_body_leaks_nothing_internal(self) -> Dict[str, Any]:
        name = "refusal_body_leaks_nothing_internal"
        assertion = (
            "400; error.type and error.message present; body carries no stack "
            "trace, source path, connection string or upstream hostname"
        )
        args, request = self._prepare(
            None, raw_body='{"model": "' + self.model + '", "messages": [}'
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        leaked = [marker for marker in INTERNAL_LEAK_MARKERS if marker in body]
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            (not leaked, f"refusal body carries internal detail: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_trace_id_shape(self) -> Dict[str, Any]:
        name = "trace_id_shape"
        assertion = (
            "200; x-nr-trace-id, when emitted, is 16-32 lowercase hex characters "
            "and is not the all-zero trace"
        )
        args, request = self._prepare(self._chat())
        status, headers, _, _ = self.curl_fn(args)
        trace_id = headers.get("x-nr-trace-id")
        if trace_id is None:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="x-nr-trace-id is absent; no valid trace exists for this request",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (bool(TRACE_ID_RE.match(trace_id)), f"x-nr-trace-id {trace_id!r} is not lowercase hex"),
            (set(trace_id) != {"0"}, "x-nr-trace-id is the all-zero trace"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_request_id_on_served_response,
            self.check_request_id_on_refusal,
            self.check_request_ids_are_unique,
            self.check_client_supplied_request_id_is_overwritten,
        ]
        if not quick:
            checks = [
                self.check_request_id_on_served_response,
                self.check_model_header_on_served_response,
                self.check_latency_header_is_integer,
                self.check_request_id_on_refusal,
                self.check_request_ids_are_unique,
                self.check_refusal_has_no_routing_headers,
                self.check_request_id_on_unauthorized,
                self.check_client_supplied_request_id_is_overwritten,
                self.check_refusal_body_leaks_nothing_internal,
                self.check_trace_id_shape,
            ]
        run_checks_with_scope_guard(self, checks)
        return self.summarize()

    def summarize(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r["result"] == PASS)
        failed = sum(1 for r in self.results if r["result"] == FAIL)
        unconfigured = sum(1 for r in self.results if r["result"] == NOT_CONFIGURED)
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
            "adversarial_checks": sum(1 for r in self.results if r["expected_failure"]),
            "all_passed": failed == 0,
            "partial": unconfigured > 0,
        }

    def render_markdown_summary(self, suite: Dict[str, Any]) -> str:
        badge = "🟢 **PASSED**" if suite["all_passed"] else "🔴 **FAILED**"
        if suite["all_passed"] and suite["partial"]:
            badge = "🟡 **PARTIAL (checks not configured on this plane)**"
        lines = [
            "## 🧵 nRouter Pure-Curl Health Check: Request Identity & Tracing",
            "",
            f"**Status**: {badge} | **Base URL**: `{suite['base_url']}` | "
            f"**Route**: `{suite['route']}` | **Model**: `{suite['model']}` | "
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
    print("Running tracing_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

    def auth_of(args: List[str]) -> str:
        for index, arg in enumerate(args):
            if arg == "-H" and args[index + 1].lower().startswith("authorization:"):
                return args[index + 1].split(" ", 2)[-1]
        return ""

    def raw_payload(args: List[str]) -> str:
        for index, arg in enumerate(args):
            if arg == "-d":
                return args[index + 1]
        return ""

    def make_backend() -> Callable:
        counter = {"n": 0}

        def mock_curl(args, timeout_s=40, stdin_data=None):
            counter["n"] += 1
            request_id = f"{counter['n']:08x}-1111-2222-3333-444444444444"
            base = {"x-nr-request-id": request_id, "x-nr-latency-ms": "31"}
            if auth_of(args) == INVALID_KEY:
                headers = dict(base)
                headers["x-nr-auth-reason"] = "unauthorized"
                return 401, headers, json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
                ), 3.0
            payload = raw_payload(args)
            try:
                body = json.loads(payload)
            except Exception:
                return 400, dict(base), json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "malformed JSON body"}}
                ), 2.0
            if not isinstance(body.get("messages"), list):
                return 400, dict(base), json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "messages must be an array"}}
                ), 2.0
            headers = dict(base)
            headers.update({
                "x-nr-model": DEFAULT_MODEL,
                "x-nr-trace-id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "x-nr-request-cost": "0.000022",
                "x-nr-cost-status": "exact",
            })
            if args[-1].endswith("/messages"):
                return 200, headers, json.dumps(
                    {"content": [{"type": "text", "text": "pong"}]}
                ), 30.0
            return 200, headers, json.dumps({"choices": [{"message": {"content": "pong"}}]}), 30.0

        return mock_curl

    checker = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="sk-nrouter-mock-key", curl_fn=make_backend()
    )
    suite = checker.run_suite()
    assert suite["feature"] == FEATURE
    assert suite["total_checks"] == 10, suite["total_checks"]
    assert suite["adversarial_checks"] >= 7, suite["adversarial_checks"]
    assert suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in suite["checks"] if r["result"] == FAIL
    ]
    for row in suite["checks"]:
        assert {"name", "request", "status", "headers", "assertion", "result", "expected_failure"} <= set(row)
        assert "sk-nrouter-mock-key" not in row["request"], "raw key leaked into report"

    # BITE 1: an echoed caller-supplied request id must go red.
    def echoes_caller_id() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            for index, arg in enumerate(args):
                if arg == "-H" and args[index + 1].lower().startswith("x-nr-request-id:"):
                    headers = dict(headers)
                    headers["x-nr-request-id"] = args[index + 1].split(":", 1)[1].strip()
            return status, headers, body, latency

        return mock

    echoing = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=echoes_caller_id()
    )
    echo_row = next(
        r for r in echoing.run_suite()["checks"]
        if r["name"] == "client_supplied_request_id_is_overwritten"
    )
    assert echo_row["result"] == FAIL, "echoing a caller-supplied request id must fail"

    # BITE 2: a refusal with no request id must go red.
    def drops_id_on_refusal() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status >= 400:
                headers = {k: v for k, v in headers.items() if k != "x-nr-request-id"}
            return status, headers, body, latency

        return mock

    dropped = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=drops_id_on_refusal()
    )
    assert dropped.run_suite(quick=True)["all_passed"] is False, (
        "a refusal without a request id must fail"
    )

    # BITE 3: a constant request id across requests must go red.
    def constant_id(args, timeout_s=40, stdin_data=None):
        headers = {
            "x-nr-request-id": "11111111-1111-1111-1111-111111111111",
            "x-nr-model": DEFAULT_MODEL,
            "x-nr-latency-ms": "10",
        }
        return 200, headers, json.dumps({"choices": [{"message": {"content": "x"}}]}), 10.0

    constant = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=constant_id
    )
    unique_row = next(
        r for r in constant.run_suite(quick=True)["checks"] if r["name"] == "request_ids_are_unique"
    )
    assert unique_row["result"] == FAIL, "a constant request id must fail"

    # BITE 4: a leaked stack trace in the refusal body must go red.
    def leaky() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if status == 400:
                body = json.dumps({
                    "error": {"type": "invalid_request_error", "message": "bad body at src/http/route.rs:118"}
                })
            return status, headers, body, latency

        return mock

    leaking = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=leaky()
    )
    leak_row = next(
        r for r in leaking.run_suite()["checks"] if r["name"] == "refusal_body_leaks_nothing_internal"
    )
    assert leak_row["result"] == FAIL, "an internal source path in a refusal must fail"

    # NOT-CONFIGURED when no trace id is emitted.
    def no_trace() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            headers = {k: v for k, v in headers.items() if k != "x-nr-trace-id"}
            return status, headers, body, latency

        return mock

    untraced = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=no_trace()
    )
    trace_row = next(r for r in untraced.run_suite()["checks"] if r["name"] == "trace_id_shape")
    assert trace_row["result"] == NOT_CONFIGURED, trace_row["result"]

    # BITE 5: x-nr-latency-ms is ALWAYS emitted per the spec, so its absence is a
    # contract break and must FAIL — never be excused as an unconfigured plane.
    def drops_latency() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            headers = {k: v for k, v in headers.items() if k != "x-nr-latency-ms"}
            return status, headers, body, latency

        return mock

    latency_less = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=drops_latency()
    )
    latency_row = next(
        r for r in latency_less.run_suite()["checks"] if r["name"] == "latency_header_is_integer"
    )
    assert latency_row["result"] == FAIL, (
        "a missing x-nr-latency-ms must FAIL (the spec marks it always emitted), got "
        f"{latency_row['result']}"
    )

    # A transport failure can only FAIL; it is never an absent precondition.
    def transport_failure(args, timeout_s=40, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 8.0

    broken = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=transport_failure
    )
    broken_suite = broken.run_suite(quick=True)
    assert broken_suite["all_passed"] is False, "a transport failure must fail the suite"
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # BOTH WIRES: request identity is wire-independent, but the served-body
    # assertion is not.
    messages_suite = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001", curl_fn=make_backend(),
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

    scoped_suite = TracingCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_route_not_allowed
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert any(
        "NROUTER_HEALTH_ROUTE" in r.get("detail", "") for r in scoped_suite["checks"]
    ), "the scope refusal must name the override to set"

    assert "Request Identity" in checker.render_markdown_summary(suite)
    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] tracing_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Request Identity Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)
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
        checker = TracingCurlHealthCheck(
            base_url=args.base_url, api_key=api_key, route=args.route, model=args.model
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Request Identity Curl Health Check ===\n"
        f"Base URL: {args.base_url} | route: {checker.route} | model: {checker.model}",
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
