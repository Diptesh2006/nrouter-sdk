#!/usr/bin/env python3
"""nRouter Wire Contract Pure-Curl Health Check (`contract_curl`).

`spec/nrouter-sdk-spec.json` is what every SDK in this repository is generated
and tested against. This module asks the live gateway whether that is still
true, in both directions:

  Happy path
    1. The published OpenAPI document names every `x-nr-*` response header the
       spec lists — a header a client must handle but cannot discover is a
       documentation defect.
    2. Every `x-nr-*` header on a served response is IN the spec — an
       undocumented header is an unversioned promise.
    3. `x-nr-response-cache` only takes a value the spec enumerates.

  Adversarial
    4. A refusal carries `error.type` and a non-empty `error.message`.
    5. When a refusal carries `error.code`, that code is a key the spec defines.
    6. No upstream provider header survives egress.
    7. An unknown `x-nr-*` REQUEST header is not reflected back.
    8. No server-internal `x-nr-*` header (internal, signature, org) is visible.
    9. `x-nr-cost-status` is inside its enum.
   10. `x-nr-guardrails` is inside its enum.
   11. A 401 carries an `x-nr-auth-reason` inside its enum.

Usage:
  python3 scripts/curl_health_checks/contract_curl.py --self-test
  python3 scripts/curl_health_checks/contract_curl.py --quick
  python3 scripts/curl_health_checks/contract_curl.py --step-summary
  python3 scripts/curl_health_checks/contract_curl.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Shared plumbing: ONE curl invocation, ONE response parser, ONE credential rule.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import (  # noqa: E402
    DEFAULT_BASE_URL,
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
    prompt_field,
    reported_headers,
    resolve_api_key,
    resolve_model,
    resolve_route,
    run_checks_with_scope_guard,
    run_curl,
    sanitize,
    suite_verdict,
    wire_contract_self_test,
)

FEATURE = "contract"
# There is deliberately no `DEFAULT_MODEL` here. The model under test comes from
# `resolve_model()` like everywhere else in this directory; a local constant
# duplicating it was read only by this file's own mock, which then echoed a
# model the checker had never asked for.
INVALID_KEY = "sk-nrouter-invalid-key-0000"
SPOOF_HEADER = "x-nr-fake-spoof-header"

SPEC_PATH = Path(__file__).resolve().parents[2] / "spec" / "nrouter-sdk-spec.json"

# Headers an upstream provider sets that must never reach a customer.
FORBIDDEN_UPSTREAM_PREFIXES = ("openai-", "anthropic-", "x-ratelimit-", "x-amzn-", "x-goog-")
FORBIDDEN_UPSTREAM_HEADERS = ("cf-ray", "x-request-id", "server", "x-envoy-upstream-service-time")
# Server-only headers that exist but must never be customer-visible.
INTERNAL_HEADER_MARKERS = ("x-nr-internal", "x-nr-signature", "x-nr-org", "x-nr-probe")


def load_spec(path: Path = SPEC_PATH) -> Dict[str, Any]:
    """Read the published SDK spec. It is the contract; this module never edits it."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


class ContractCurlHealthCheck:
    """Health check runner comparing the live wire against the published spec."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        spec: Optional[Dict[str, Any]] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.spec = spec if spec is not None else load_spec()
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ------------------------------------------------------------ spec helpers

    def spec_headers(self) -> Set[str]:
        return {name.lower() for name in (self.spec.get("response_headers") or {})}

    def spec_header_values(self, name: str) -> Set[str]:
        entry = (self.spec.get("response_headers") or {}).get(name) or {}
        return set(entry.get("values") or [])

    def spec_error_codes(self) -> Set[str]:
        return set(self.spec.get("errors") or {})

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self,
        method: str,
        path: str,
        body: Any = None,
        key: Optional[str] = None,
        key_label: str = "$NROUTER_API_KEY",
        extra_headers: Optional[List[Tuple[str, str]]] = None,
        raw_body: Optional[str] = None,
    ) -> Tuple[List[str], str]:
        self._current_path = path
        url = f"{self.base_url}{path}"
        args = ["-H", f"Authorization: Bearer {key or self.api_key}"]
        shown = [
            f'curl -sS -D - -X {method} "$NROUTER_BASE_URL{path}"',
            f'  -H "Authorization: Bearer {key_label}"',
        ]
        for header_name, header_value in extra_headers or []:
            args += ["-H", f"{header_name}: {header_value}"]
            shown.append(f'  -H "{header_name}: {header_value}"')
        payload = raw_body if raw_body is not None else (
            json.dumps(body) if body is not None else None
        )
        args += ["-X", method]
        if payload is not None:
            args += ["-H", "Content-Type: application/json", "-d", payload]
            shown.append('  -H "Content-Type: application/json"')
            shown.append(f"  -d '{payload}'")
        args.append(url)
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
            # The CALLER's detail wins. Both can be true at once, but the
            # caller's names what THIS check wanted and what it saw, while the
            # scope detail is the same sentence on every row — letting the
            # generic one overwrite the specific one throws away the only part
            # of the transcript that told the rows apart. When the caller says
            # nothing, the scope detail fills in, because a NOT-CONFIGURED row
            # with no explanation is not evidence of anything.
            detail = detail or self.scope_detail or ""
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

    def _chat(self, prompt: str = "contract probe") -> Dict[str, Any]:
        return build_body(self.route, self.model, prompt, max_tokens=16)

    # ------------------------------------------------------------ happy checks

    def check_openapi_lists_every_spec_header(self) -> Dict[str, Any]:
        name = "openapi_lists_every_spec_header"
        assertion = (
            "200; the OpenAPI document names every x-nr-* response header that "
            "spec/nrouter-sdk-spec.json publishes"
        )
        args, request = self._prepare("GET", "/openapi.json")
        status, headers, body, _ = self.curl_fn(args)
        if status != 200 or not body.strip():
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=f"the OpenAPI document is not served here (HTTP {status})",
                not_configured=True,
            )
        expected = self.spec_headers()
        if not expected:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="spec/nrouter-sdk-spec.json declares no response_headers",
                not_configured=True,
            )
        lowered = body.lower()
        missing = sorted(header for header in expected if header not in lowered)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (bool(parse_json(body)), "the OpenAPI body is not JSON"),
            (not missing, f"the OpenAPI document never names: {missing}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_response_headers_are_subset_of_spec(self) -> Dict[str, Any]:
        name = "response_headers_are_subset_of_spec"
        assertion = (
            "200; every x-nr-* response header is a key of the spec's "
            "response_headers (no undocumented header on the customer wire)"
        )
        args, request = self._prepare("POST", self.route, self._chat())
        status, headers, _, _ = self.curl_fn(args)
        expected = self.spec_headers()
        if not expected:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="spec/nrouter-sdk-spec.json declares no response_headers",
                not_configured=True,
            )
        seen = {header for header in headers if header.startswith("x-nr-")}
        undocumented = sorted(seen - expected)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (bool(seen), "the served response carried no x-nr-* header at all"),
            (not undocumented, f"undocumented x-nr-* headers on the wire: {undocumented}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_response_cache_value_in_enum(self) -> Dict[str, Any]:
        name = "response_cache_value_in_enum"
        assertion = "200; x-nr-response-cache, when present, is one of hit|miss|bypass"
        args, request = self._prepare("POST", self.route, self._chat("cache enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-response-cache")
        value = headers.get("x-nr-response-cache")
        if value is None and status == 200:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="the request was served but this plane emits no x-nr-response-cache",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (bool(allowed), "the spec publishes no value list for x-nr-response-cache"),
            (value in allowed, f"x-nr-response-cache {value!r} outside {sorted(allowed)}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def check_refusal_carries_type_and_message(self) -> Dict[str, Any]:
        name = "refusal_carries_type_and_message"
        assertion = (
            "400; error.type is a non-empty string; error.message is non-empty "
            "prose; the envelope has no other top-level key than error"
        )
        args, request = self._prepare(
            "POST",
            self.route,
            None,
            # Malformed for THIS wire: the prompt field is present, wrong type.
            raw_body=json.dumps(
                {"model": self.model, **{prompt_field(self.route): "not-an-array"}}
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        parsed = parse_json(body)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (isinstance(err.get("type"), str) and err["type"].strip() != "", "error.type missing or empty"),
            (
                isinstance(err.get("message"), str) and err["message"].strip() != "",
                "error.message missing or empty",
            ),
            (set(parsed) == {"error"}, f"the refusal envelope carries extra top-level keys: {sorted(set(parsed) - {'error'})}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_refusal_code_is_in_spec(self) -> Dict[str, Any]:
        name = "refusal_code_is_in_spec"
        assertion = (
            "400; when error.code is present it is a key the spec's errors section "
            "defines (a code outside the spec is a code no client's table contains)"
        )
        args, request = self._prepare(
            "POST",
            self.route,
            None,
            # Malformed for THIS wire: the prompt field is present, wrong type.
            raw_body=json.dumps(
                {"model": self.model, **{prompt_field(self.route): "not-an-array"}}
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        code = err.get("code")
        known = self.spec_error_codes()
        # An absent code IS allowed by the spec, but only on an actual refusal.
        # If the request was not even refused, that is a FAIL below.
        if code is None and status == 400:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail=(
                    "the request was refused 400 but carries no error.code (the spec "
                    "marks code optional), so there was nothing to check against the table"
                ),
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(known), "the spec publishes no errors section"),
            (code in known, f"error.code {code!r} is not one of {sorted(known)}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_no_upstream_headers_leak(self) -> Dict[str, Any]:
        name = "no_upstream_headers_leak"
        assertion = (
            "200; no openai-*, anthropic-*, x-ratelimit-*, cf-ray or server header "
            "survives egress; the response is ours, not the provider's"
        )
        args, request = self._prepare("POST", self.route, self._chat("egress probe"))
        status, headers, _, _ = self.curl_fn(args)
        leaked = sorted(
            header
            for header in headers
            if header.startswith(FORBIDDEN_UPSTREAM_PREFIXES) or header in FORBIDDEN_UPSTREAM_HEADERS
        )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (not leaked, f"upstream provider headers reached the customer: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_unknown_request_header_not_reflected(self) -> Dict[str, Any]:
        name = "unknown_request_header_not_reflected"
        assertion = (
            f"200; a caller-invented {SPOOF_HEADER} request header is absent from "
            "the response and absent from the body"
        )
        args, request = self._prepare(
            "POST",
            self.route,
            self._chat("reflection probe"),
            extra_headers=[(SPOOF_HEADER, "evil")],
        )
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (SPOOF_HEADER not in headers, f"{SPOOF_HEADER} was reflected back to the caller"),
            ("evil" not in body, "the invented header value appeared in the response body"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_no_internal_headers_visible(self) -> Dict[str, Any]:
        name = "no_internal_headers_visible"
        assertion = (
            "200; no server-only header (x-nr-internal*, x-nr-signature, x-nr-org*, "
            "x-nr-probe*) is visible to the customer"
        )
        args, request = self._prepare("POST", self.route, self._chat("internal probe"))
        status, headers, _, _ = self.curl_fn(args)
        leaked = sorted(
            header for header in headers if any(header.startswith(marker) for marker in INTERNAL_HEADER_MARKERS)
        )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (not leaked, f"server-only headers are customer-visible: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_cost_status_value_in_enum(self) -> Dict[str, Any]:
        name = "cost_status_value_in_enum"
        assertion = (
            "200; x-nr-cost-status is exact or unpriced; and unpriced NEVER ships "
            "alongside an x-nr-request-cost header"
        )
        args, request = self._prepare("POST", self.route, self._chat("cost enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-cost-status")
        value = headers.get("x-nr-cost-status")
        if value is None and status == 200:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="the request was served but carried no x-nr-cost-status to check",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (value in allowed, f"x-nr-cost-status {value!r} outside {sorted(allowed)}"),
            (
                not (value == "unpriced" and "x-nr-request-cost" in headers),
                "an unpriced response also carried a cost header",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_guardrails_value_in_enum(self) -> Dict[str, Any]:
        name = "guardrails_value_in_enum"
        assertion = (
            "200; x-nr-guardrails, when present, is one of the six values the spec "
            "enumerates; a served response never reports blocked"
        )
        args, request = self._prepare("POST", self.route, self._chat("guardrail enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-guardrails")
        value = headers.get("x-nr-guardrails")
        if value is None and status == 200:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="the request was served but carried no x-nr-guardrails to check",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (value in allowed, f"x-nr-guardrails {value!r} outside {sorted(allowed)}"),
            (value != "blocked", "a 200 response reported x-nr-guardrails: blocked"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_auth_reason_value_in_enum(self) -> Dict[str, Any]:
        name = "auth_reason_value_in_enum"
        assertion = (
            "401; x-nr-auth-reason present and inside the spec enum; error.type "
            "present; the body names no key material"
        )
        args, request = self._prepare(
            "POST",
            self.route,
            self._chat(),
            key=INVALID_KEY,
            key_label="sk-nrouter-invalid-key-0000",
        )
        status, headers, body, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-auth-reason")
        value = headers.get("x-nr-auth-reason")
        ok, detail = assert_all([
            (status == 401, f"expected 401, got {status}"),
            (value is not None, "x-nr-auth-reason absent on a 401"),
            (value in allowed, f"x-nr-auth-reason {value!r} outside {sorted(allowed)}"),
            (bool(error_of(body).get("type")), "error.type absent on a 401"),
            (INVALID_KEY not in body, "the refusal echoed the presented key back"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_response_headers_are_subset_of_spec,
            self.check_refusal_carries_type_and_message,
            self.check_no_upstream_headers_leak,
            self.check_auth_reason_value_in_enum,
        ]
        if not quick:
            checks = [
                self.check_openapi_lists_every_spec_header,
                self.check_response_headers_are_subset_of_spec,
                self.check_response_cache_value_in_enum,
                self.check_refusal_carries_type_and_message,
                self.check_refusal_code_is_in_spec,
                self.check_no_upstream_headers_leak,
                self.check_unknown_request_header_not_reflected,
                self.check_no_internal_headers_visible,
                self.check_cost_status_value_in_enum,
                self.check_guardrails_value_in_enum,
                self.check_auth_reason_value_in_enum,
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
            # The ONE verdict rule, shared by every module and by run_all.py:
            # nothing failed AND something was actually proven. See
            # `_curl_common.suite_verdict`.
            **suite_verdict(passed, failed, unconfigured),
        }

    def render_markdown_summary(self, suite: Dict[str, Any]) -> str:
        badge = "🟢 **PASSED**" if suite["all_passed"] else "🔴 **FAILED**"
        if suite["all_passed"] and suite["partial"]:
            badge = "🟡 **PARTIAL (checks not configured on this plane)**"
        lines = [
            "## 📜 nRouter Pure-Curl Health Check: Wire Contract",
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
    print("Running contract_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

    spec = load_spec()
    assert spec, f"the published spec is unreadable at {SPEC_PATH}"
    assert spec.get("response_headers"), "the spec declares no response_headers"
    assert spec.get("errors"), "the spec declares no errors"
    spec_headers = {name.lower() for name in spec["response_headers"]}

    def header_of(args: List[str], name: str) -> Optional[str]:
        for index, arg in enumerate(args):
            if arg == "-H" and args[index + 1].lower().startswith(f"{name}:"):
                return args[index + 1].split(":", 1)[1].strip()
        return None

    served_headers = {
        "x-nr-request-id": "55555555-0000-1111-2222-333333333333",
        "x-nr-latency-ms": "42",
        # `x-nr-model` is filled per request by the mock, from the model the
        # checker actually asked for — see `mock_curl`. A constant here echoes a
        # model nobody requested, which is exactly what `x-nr-model` is for
        # catching.
        "x-nr-request-cost": "0.000023",
        "x-nr-cost-status": "exact",
        "x-nr-input-tokens": "6",
        "x-nr-output-tokens": "4",
        "x-nr-total-tokens": "10",
        "x-nr-guardrails": "pass",
        "x-nr-response-cache": "miss",
        "content-type": "application/json",
    }
    openapi_document = json.dumps(
        {"openapi": "3.1.0", "components": {"headers": {name: {} for name in sorted(spec_headers)}}}
    )

    def mock_curl(args, timeout_s=40, stdin_data=None):
        endpoint = args[-1]
        auth = header_of(args, "authorization") or ""
        if endpoint.endswith("/openapi.json"):
            return 200, {"content-type": "application/json"}, openapi_document, 9.0
        if auth.endswith(INVALID_KEY):
            headers = {
                "x-nr-request-id": "66666666-0000-1111-2222-333333333333",
                "x-nr-auth-reason": "unauthorized",
                "content-type": "application/json",
            }
            return 401, headers, json.dumps(
                {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
            ), 3.0
        payload = ""
        for index, arg in enumerate(args):
            if arg == "-d":
                payload = args[index + 1]
        body = parse_json(payload)
        if not isinstance(body.get("messages"), list):
            return 400, {
                "x-nr-request-id": "77777777-0000-1111-2222-333333333333",
                "x-nr-latency-ms": "2",
                "content-type": "application/json",
            }, json.dumps(
                {"error": {"type": "invalid_request", "code": "invalid_request", "message": "messages must be an array"}}
            ), 2.0
        # Echo the model the request actually named: `x-nr-model` reports what
        # the gateway served, so a mock that answers with a constant cannot
        # catch a check asking for one model and being handed another.
        headers = dict(served_headers)
        headers["x-nr-model"] = str(body.get("model") or "")
        return 200, headers, json.dumps(
            {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 10}}
        ), 30.0

    checker = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        spec=spec,
        curl_fn=mock_curl,
    )
    suite = checker.run_suite()
    assert suite["feature"] == FEATURE
    assert suite["total_checks"] == 11, suite["total_checks"]
    assert suite["adversarial_checks"] >= 8, suite["adversarial_checks"]
    assert suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in suite["checks"] if r["result"] == FAIL
    ]
    for row in suite["checks"]:
        assert {"name", "request", "status", "headers", "assertion", "result", "expected_failure"} <= set(row)
        assert "sk-nrouter-mock-key" not in row["request"], "raw key leaked into report"

    # BITE 1: an undocumented x-nr-* header must go red.
    def emits_undocumented(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 200 and not args[-1].endswith("/openapi.json"):
            headers = dict(headers)
            headers["x-nr-undocumented-experiment"] = "1"
        return status, headers, body, latency

    undocumented = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=emits_undocumented
    )
    undoc_row = next(
        r for r in undocumented.run_suite(quick=True)["checks"]
        if r["name"] == "response_headers_are_subset_of_spec"
    )
    assert undoc_row["result"] == FAIL, "an undocumented x-nr-* header must fail"

    # BITE 2: an upstream provider header that survives egress must go red.
    def leaks_upstream(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 200 and not args[-1].endswith("/openapi.json"):
            headers = dict(headers)
            headers["x-ratelimit-remaining-requests"] = "4999"
        return status, headers, body, latency

    leaky = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=leaks_upstream
    )
    leak_row = next(
        r for r in leaky.run_suite(quick=True)["checks"] if r["name"] == "no_upstream_headers_leak"
    )
    assert leak_row["result"] == FAIL, "a leaked provider header must fail"

    # BITE 3: an error code outside the spec table must go red.
    def invents_a_code(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 400:
            body = json.dumps(
                {"error": {"type": "invalid_request", "code": "totally_new_code", "message": "nope"}}
            )
        return status, headers, body, latency

    inventive = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=invents_a_code
    )
    code_row = next(
        r for r in inventive.run_suite()["checks"] if r["name"] == "refusal_code_is_in_spec"
    )
    assert code_row["result"] == FAIL, "an off-spec error code must fail"

    # BITE 4: an OpenAPI document missing a published header must go red.
    def thin_openapi(args, timeout_s=40, stdin_data=None):
        if args[-1].endswith("/openapi.json"):
            return 200, {"content-type": "application/json"}, json.dumps(
                {"openapi": "3.1.0", "components": {"headers": {"x-nr-request-id": {}}}}
            ), 8.0
        return mock_curl(args, timeout_s, stdin_data)

    thin = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=thin_openapi
    )
    openapi_row = next(
        r for r in thin.run_suite()["checks"] if r["name"] == "openapi_lists_every_spec_header"
    )
    assert openapi_row["result"] == FAIL, "an incomplete OpenAPI document must fail"

    # BITE 5: a reflected spoof header must go red.
    def reflects(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        spoof = header_of(args, SPOOF_HEADER)
        if spoof:
            headers = dict(headers)
            headers[SPOOF_HEADER] = spoof
        return status, headers, body, latency

    reflector = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=reflects
    )
    reflect_row = next(
        r for r in reflector.run_suite()["checks"]
        if r["name"] == "unknown_request_header_not_reflected"
    )
    assert reflect_row["result"] == FAIL, "a reflected caller header must fail"

    # NOT-CONFIGURED, never PASS, when no OpenAPI document is served.
    def no_openapi(args, timeout_s=40, stdin_data=None):
        if args[-1].endswith("/openapi.json"):
            return 404, {}, "not found", 2.0
        return mock_curl(args, timeout_s, stdin_data)

    silent = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=no_openapi
    )
    silent_row = next(
        r for r in silent.run_suite()["checks"] if r["name"] == "openapi_lists_every_spec_header"
    )
    assert silent_row["result"] == NOT_CONFIGURED, silent_row["result"]

    # BITE 6: a request that was never REFUSED cannot excuse itself with "the
    # spec makes error.code optional". Only a real 400 may report NOT-CONFIGURED.
    def never_refuses(args, timeout_s=40, stdin_data=None):
        if args[-1].endswith("/openapi.json"):
            return 200, {"content-type": "application/json"}, openapi_document, 9.0
        return 200, {**served_headers, "x-nr-model": "mock/served"}, json.dumps(
            {"choices": [{"message": {"content": "served anyway"}}]}
        ), 30.0

    permissive = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=never_refuses
    )
    permissive_suite = permissive.run_suite()
    code_row = next(
        r for r in permissive_suite["checks"] if r["name"] == "refusal_code_is_in_spec"
    )
    assert code_row["result"] == FAIL, (
        "a malformed request that was SERVED must FAIL, not report NOT-CONFIGURED; "
        f"got {code_row['result']}"
    )

    # A transport failure can only FAIL; it is never an absent precondition.
    def transport_failure(args, timeout_s=40, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 5.0

    broken = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=transport_failure
    )
    broken_suite = broken.run_suite(quick=True)
    assert broken_suite["all_passed"] is False, "a transport failure must fail the suite"
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # BOTH WIRES: the header contract is wire-independent, the bodies are not.
    def messages_aware(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 200 and args[-1].endswith("/messages"):
            body = json.dumps({"content": [{"type": "text", "text": "ok"}]})
        return status, headers, body, latency

    messages_suite = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001", spec=spec, curl_fn=messages_aware,
    ).run_suite()
    assert messages_suite["route"] == "/messages"
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]

    # A route-scoped key short-circuits as NOT-CONFIGURED, not as failures...
    def mock_route_not_allowed(args, timeout_s=40, stdin_data=None):
        if args[-1].endswith("/openapi.json"):
            return 200, {"content-type": "application/json"}, openapi_document, 9.0
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec,
        curl_fn=mock_route_not_allowed,
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert any(
        "NROUTER_HEALTH_ROUTE" in r.get("detail", "") for r in scoped_suite["checks"]
    ), "the scope refusal must name the override to set"
    # The OpenAPI document is not on the route under test, so it still answers:
    # one real pass with the rest absent is a PARTIAL pass — real but incomplete
    # evidence, and it says so.
    assert scoped_suite["passed_checks"] >= 1, scoped_suite["passed_checks"]
    assert scoped_suite["all_passed"] is True and scoped_suite["partial"] is True, scoped_suite
    assert scoped_suite["proved_nothing"] is False, scoped_suite

    # ...but a suite in which EVERY row is NOT-CONFIGURED proved NOTHING, and must
    # never read as passing. Under `all_passed = failed == 0` this was green: zero
    # failures, zero proof, and a CI gate reading `all_passed` waved it through as
    # release evidence. The module's own summarizer is what is exercised here.
    absent = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec,
        curl_fn=mock_route_not_allowed,
    )
    absent.results = [dict(row, result=NOT_CONFIGURED) for row in scoped_suite["checks"]]
    absent_suite = absent.summarize()
    assert absent_suite["not_configured_checks"] == absent_suite["total_checks"], absent_suite
    assert absent_suite["all_passed"] is False, (
        "an all-NOT-CONFIGURED suite proved nothing and must not report all_passed"
    )
    assert absent_suite["proved_nothing"] is True, absent_suite["passed_checks"]

    # ...but a refusal on a DIFFERENT path (the OpenAPI document) must not
    # short-circuit the route under test: that path is not what is being tested.
    def openapi_forbidden(args, timeout_s=40, stdin_data=None):
        if args[-1].endswith("/openapi.json"):
            return 403, {"x-nr-auth-reason": "key_route_not_allowed"}, "forbidden", 2.0
        return mock_curl(args, timeout_s, stdin_data)

    partial = ContractCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", spec=spec, curl_fn=openapi_forbidden
    )
    partial_suite = partial.run_suite()
    assert partial_suite["total_checks"] == suite["total_checks"], (
        "a refusal on the OpenAPI path short-circuited the whole module"
    )
    openapi_row = next(
        r for r in partial_suite["checks"] if r["name"] == "openapi_lists_every_spec_header"
    )
    assert openapi_row["result"] == NOT_CONFIGURED, openapi_row["result"]
    assert partial_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in partial_suite['checks'] if r['result'] == FAIL]}"
    )

    assert "Wire Contract" in checker.render_markdown_summary(suite)
    # ---- R8: no dead constant, no unused import ----------------------------
    # `DEFAULT_MODEL` duplicated the shared default and was read only by this
    # file's own mock, which then echoed a model the checker had not asked for.
    # A constant that only the test reads is a place for the test and the code
    # to disagree.
    module = sys.modules[__name__]
    assert not hasattr(module, "DEFAULT_MODEL"), (
        "DEFAULT_MODEL is dead — the model under test comes from resolve_model()"
    )
    import ast as _ast

    _source = Path(__file__).read_text()
    _tree = _ast.parse(_source)
    _imported = {
        alias.name
        for node in _ast.walk(_tree)
        if isinstance(node, _ast.ImportFrom) and node.module == "_curl_common"
        for alias in node.names
    }
    _used = {n.id for n in _ast.walk(_tree) if isinstance(n, _ast.Name)} | {
        n.attr for n in _ast.walk(_tree) if isinstance(n, _ast.Attribute)
    }
    assert not (_imported - _used), (
        f"imported from _curl_common and never used: {sorted(_imported - _used)}"
    )

    # ---- R8: a caller's detail is more specific than the scope detail ------
    # Both can be true at once. The caller's names what THIS check wanted and
    # what it saw; the scope detail is the same sentence on every row. Letting
    # the generic one overwrite the specific one threw away the only part of the
    # transcript that distinguished the rows.
    class _DetailProbe(ContractCurlHealthCheck):
        pass

    probe = _DetailProbe(base_url="https://mock.invalid/v1", api_key="k", route="/chat/completions")
    probe._current_path = probe.route
    scoped_headers = {"x-nr-auth-reason": "key_route_not_allowed"}
    row = probe._record(
        "caller_detail_wins", "(req)", 403, scoped_headers,
        "the caller's detail survives a scope refusal",
        False, False, detail="the caller saw x-nr-cost-status: unpriced on a served row",
    )
    assert row["result"] == NOT_CONFIGURED, row
    assert row["detail"] == "the caller saw x-nr-cost-status: unpriced on a served row", row["detail"]
    # ...and with NO caller detail the scope detail is still reported, because a
    # NOT-CONFIGURED row with no explanation is not evidence of anything.
    probe.scope_detail = None
    probe.results.clear()
    probe._current_path = probe.route
    bare = probe._record(
        "scope_detail_when_silent", "(req)", 403, scoped_headers,
        "the scope detail fills in when the caller says nothing",
        False, False,
    )
    assert bare["result"] == NOT_CONFIGURED, bare
    assert "key_route_not_allowed" in bare.get("detail", ""), bare

    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] contract_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Wire Contract Curl Health Check")
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
        checker = ContractCurlHealthCheck(
            base_url=args.base_url, api_key=api_key, route=args.route, model=args.model
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Wire Contract Curl Health Check ===\n"
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
