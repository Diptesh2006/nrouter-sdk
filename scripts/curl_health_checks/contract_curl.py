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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

FEATURE = "contract"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
INVALID_KEY = "sk-nrouter-invalid-key-0000"
SPOOF_HEADER = "x-nr-fake-spoof-header"

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

SPEC_PATH = Path(__file__).resolve().parents[2] / "spec" / "nrouter-sdk-spec.json"

# Headers an upstream provider sets that must never reach a customer.
FORBIDDEN_UPSTREAM_PREFIXES = ("openai-", "anthropic-", "x-ratelimit-", "x-amzn-", "x-goog-")
FORBIDDEN_UPSTREAM_HEADERS = ("cf-ray", "x-request-id", "server", "x-envoy-upstream-service-time")
# Server-only headers that exist but must never be customer-visible.
INTERNAL_HEADER_MARKERS = ("x-nr-internal", "x-nr-signature", "x-nr-org", "x-nr-probe")

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


def load_spec(path: Path = SPEC_PATH) -> Dict[str, Any]:
    """Read the published SDK spec. It is the contract; this module never edits it."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class ContractCurlHealthCheck:
    """Health check runner comparing the live wire against the published spec."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        spec: Optional[Dict[str, Any]] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.model = model
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

    def _chat(self, prompt: str = "contract probe") -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 16,
        }

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
        args, request = self._prepare("POST", "/chat/completions", self._chat())
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
        args, request = self._prepare("POST", "/chat/completions", self._chat("cache enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-response-cache")
        value = headers.get("x-nr-response-cache")
        if value is None:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="x-nr-response-cache is not emitted on this plane",
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
            "/chat/completions",
            None,
            raw_body=json.dumps({"model": self.model, "messages": "not-an-array"}),
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
            "/chat/completions",
            None,
            raw_body=json.dumps({"model": self.model, "messages": "not-an-array"}),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        code = err.get("code")
        known = self.spec_error_codes()
        if code is None:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail=(
                    "this refusal carries no error.code (the spec marks code optional), "
                    "so there was nothing to check against the spec table"
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
        args, request = self._prepare("POST", "/chat/completions", self._chat("egress probe"))
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
            "/chat/completions",
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
        args, request = self._prepare("POST", "/chat/completions", self._chat("internal probe"))
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
        args, request = self._prepare("POST", "/chat/completions", self._chat("cost enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-cost-status")
        value = headers.get("x-nr-cost-status")
        if value is None:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="x-nr-cost-status is not emitted on this response",
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
        args, request = self._prepare("POST", "/chat/completions", self._chat("guardrail enum probe"))
        status, headers, _, _ = self.curl_fn(args)
        allowed = self.spec_header_values("x-nr-guardrails")
        value = headers.get("x-nr-guardrails")
        if value is None:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="x-nr-guardrails is not emitted on this response",
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
            "/chat/completions",
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
            "## 📜 nRouter Pure-Curl Health Check: Wire Contract",
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
    print("Running contract_curl.py --self-test (offline mode)...")

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
        "x-nr-model": DEFAULT_MODEL,
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
        return 200, dict(served_headers), json.dumps(
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

    assert "Wire Contract" in checker.render_markdown_summary(suite)
    print("[PASS] contract_curl.py self-test passed cleanly.")
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
    parser = argparse.ArgumentParser(description="nRouter Wire Contract Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        return 1

    checker = ContractCurlHealthCheck(base_url=args.base_url, api_key=api_key, model=args.model)
    print("=== nRouter Wire Contract Curl Health Check ===")
    print(f"Base URL: {args.base_url}")
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
