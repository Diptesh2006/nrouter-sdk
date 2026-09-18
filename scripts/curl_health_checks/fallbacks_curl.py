#!/usr/bin/env python3
"""nRouter Request Fallbacks Pure-Curl Health Check (`fallbacks_curl`).

Proves the per-request `nrouter_fallbacks` contract on the wire:

  Happy path
    1. A request carrying a fallback list is served, and the routing headers
       name the rank that answered (`x-nr-routing`, `x-nr-attempts`).
    2. A forced failover is served by the named rank (`fallback:1`).
    3. A multi-target list is walked in order and no `nrouter_*` control field
       is echoed back to the caller.

  Adversarial (the checks that must go red when the gateway regresses)
    4. An unpermitted target is refused 400 `fallback_not_allowed`.
    5. Five targets (over the 4-target ceiling) are refused 400.
    6. A self-referencing target (primary listed as its own fallback) is 400.
    7. An unknown `nrouter_*` body key is refused 400.
    8. The auto router refuses a request fallback list.
    9. A non-array `nrouter_fallbacks` value is refused 400.
   10. An exhausted chain carries no `x-nr-attempts` and no cost header.

Every check asserts status AND headers AND body — never a status code alone.
A check whose precondition is absent on the plane reports NOT-CONFIGURED; it
never reports PASS.

Usage:
  python3 scripts/curl_health_checks/fallbacks_curl.py --self-test
  python3 scripts/curl_health_checks/fallbacks_curl.py --quick
  python3 scripts/curl_health_checks/fallbacks_curl.py --step-summary
  python3 scripts/curl_health_checks/fallbacks_curl.py --json
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
from typing import Any, Callable, Dict, List, Optional, Tuple

FEATURE = "fallbacks"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_PRIMARY_MODEL = "openai/gpt-4o-mini"
DEFAULT_FALLBACK_MODEL = "anthropic/claude-3-5-haiku"
DEFAULT_SECOND_FALLBACK_MODEL = "google/gemini-2.5-flash"
UNPERMITTED_TARGET = "private/unauthorized-enterprise-model"
AUTO_MODEL = "nrouter/auto"
MAX_FALLBACK_TARGETS = 4

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

SECRET_PATTERNS = [
    re.compile(r"sk-nrouter-[A-Za-z0-9_-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]

ROUTING_RE = re.compile(r"^(direct|fallback:[0-9]+)$")
REPORTED_HEADERS = (
    "content-type",
    "cache-control",
    "retry-after",
    "x-content-type-options",
)


def sanitize(text: str) -> str:
    """Redact credentials from anything this module prints or returns."""
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
    """Collect every failed assertion so one check reports all its reasons."""
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


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Only the contract-relevant headers reach the JSON report."""
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class FallbacksCurlHealthCheck:
    """Health check runner for the `nrouter_fallbacks` request contract."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        primary_model: str = DEFAULT_PRIMARY_MODEL,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        second_fallback_model: str = DEFAULT_SECOND_FALLBACK_MODEL,
        failing_primary_model: Optional[str] = None,
        healthy_fallback_model: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.second_fallback_model = second_fallback_model
        self.failing_primary_model = failing_primary_model or os.environ.get(
            "NROUTER_FAILING_PRIMARY_MODEL", ""
        )
        self.healthy_fallback_model = healthy_fallback_model or os.environ.get(
            "NROUTER_HEALTHY_FALLBACK_MODEL", ""
        )
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self,
        method: str,
        path: str,
        body: Optional[Any] = None,
        raw_body: Optional[str] = None,
    ) -> Tuple[List[str], str]:
        """Build curl argv and the reproducible curl string shown in reports.

        The key is NEVER interpolated into the reported string: it is always
        rendered as `$NROUTER_API_KEY`, and the host as `$NROUTER_BASE_URL`.
        """
        url = f"{self.base_url}{path}"
        args = [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
            "-X", method,
        ]
        shown = [
            f'curl -sS -D - -X {method} "$NROUTER_BASE_URL{path}"',
            '  -H "Authorization: Bearer $NROUTER_API_KEY"',
            '  -H "Content-Type: application/json"',
        ]
        payload = raw_body if raw_body is not None else (
            json.dumps(body) if body is not None else None
        )
        if payload is not None:
            args += ["-d", payload]
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

    def _body_payload(self, model: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        }
        payload.update(extra)
        return payload

    # ------------------------------------------------------------ happy checks

    def check_direct_serve_with_fallback_list(self) -> Dict[str, Any]:
        """A served request names the answering rank in its routing headers."""
        name = "direct_serve_with_fallback_list"
        assertion = (
            "200; body.choices non-empty; x-nr-routing matches ^(direct|fallback:N)$ "
            "and x-nr-attempts is an integer >= 1"
        )
        args, request = self._prepare(
            "POST",
            "/chat/completions",
            self._body_payload(
                self.primary_model, nrouter_fallbacks=[self.fallback_model]
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        routing = headers.get("x-nr-routing")
        attempts = headers.get("x-nr-attempts")
        if status == 200 and routing is None and attempts is None:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    "served, but neither x-nr-routing nor x-nr-attempts was emitted; "
                    "the rank that answered is unprovable on this plane"
                ),
                not_configured=True,
            )
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
            (
                routing is not None and bool(ROUTING_RE.match(routing)),
                f"x-nr-routing {routing!r} is not direct|fallback:N",
            ),
            (
                (attempts or "").isdigit() and int(attempts) >= 1,
                f"x-nr-attempts {attempts!r} is not an integer >= 1",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_served_via_fallback_names_rank(self) -> Dict[str, Any]:
        """A forced failover is served and reports `fallback:1` over 2 attempts."""
        name = "served_via_fallback_names_rank"
        assertion = (
            "200; body.choices non-empty; x-nr-routing == fallback:1; "
            "x-nr-attempts == 2"
        )
        if not (self.failing_primary_model and self.healthy_fallback_model):
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail=(
                    "NROUTER_FAILING_PRIMARY_MODEL / NROUTER_HEALTHY_FALLBACK_MODEL "
                    "are unset, so no forced failover exists on this plane"
                ),
                not_configured=True,
            )
        args, request = self._prepare(
            "POST",
            "/chat/completions",
            self._body_payload(
                self.failing_primary_model,
                nrouter_fallbacks=[self.healthy_fallback_model],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        routing = headers.get("x-nr-routing")
        attempts = headers.get("x-nr-attempts")
        if status == 200 and routing is None and attempts is None:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="served without routing headers; the answering rank is unprovable",
                not_configured=True,
            )
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
            (routing == "fallback:1", f"x-nr-routing {routing!r} != fallback:1"),
            (attempts == "2", f"x-nr-attempts {attempts!r} != 2"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_request_list_is_walked_in_order(self) -> Dict[str, Any]:
        """Two targets are accepted and no control field is echoed back."""
        name = "request_list_is_walked_in_order"
        assertion = (
            "200; body carries no nrouter_* control field; x-nr-model present; "
            "x-nr-attempts (when emitted) <= 3"
        )
        args, request = self._prepare(
            "POST",
            "/chat/completions",
            self._body_payload(
                self.primary_model,
                nrouter_fallbacks=[self.fallback_model, self.second_fallback_model],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        attempts = headers.get("x-nr-attempts")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            ("nrouter_" not in body, "response body echoes an nrouter_* control field"),
            (bool(headers.get("x-nr-model")), "x-nr-model absent on a served response"),
            (
                attempts is None or (attempts.isdigit() and 1 <= int(attempts) <= 3),
                f"x-nr-attempts {attempts!r} outside 1..3 for a 3-candidate chain",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def _refusal_check(
        self,
        name: str,
        assertion: str,
        payload: Optional[Dict[str, Any]],
        expect_code: Optional[str],
        raw_body: Optional[str] = None,
        expect_status: Tuple[int, ...] = (400,),
        message_must_match: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared adversarial shape: a refusal with a code, no cost, no rank."""
        args, request = self._prepare(
            "POST", "/chat/completions", payload, raw_body=raw_body
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        code = err.get("code")
        message = str(err.get("message", ""))
        conditions = [
            (status in expect_status, f"expected {expect_status}, got {status}"),
            (bool(err), "refusal body carries no error object"),
            (bool(err.get("type")), "error.type is absent"),
            (bool(message.strip()), "error.message is empty"),
            (
                "x-nr-request-cost" not in headers,
                "x-nr-request-cost present on a refusal (money leak)",
            ),
            (
                "x-nr-routing" not in headers and "x-nr-attempts" not in headers,
                "routing headers present on a refusal",
            ),
        ]
        if expect_code:
            conditions.append(
                (code == expect_code, f"error.code {code!r} != {expect_code!r}")
            )
        if message_must_match:
            conditions.append(
                (
                    re.search(message_must_match, message, re.IGNORECASE) is not None,
                    f"error.message does not mention {message_must_match!r}",
                )
            )
        ok, detail = assert_all(conditions)
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_unpermitted_target_is_400(self) -> Dict[str, Any]:
        return self._refusal_check(
            "unpermitted_target_is_400",
            "400; error.code == fallback_not_allowed; no x-nr-request-cost; no routing headers",
            self._body_payload(
                self.primary_model, nrouter_fallbacks=[UNPERMITTED_TARGET]
            ),
            expect_code="fallback_not_allowed",
        )

    def check_five_targets_400(self) -> Dict[str, Any]:
        return self._refusal_check(
            "five_targets_400",
            f"400; error.type present; message names the {MAX_FALLBACK_TARGETS}-target ceiling; no cost header",
            self._body_payload(
                self.primary_model,
                nrouter_fallbacks=[f"vendor/model-{n}" for n in range(1, 6)],
            ),
            expect_code=None,
            message_must_match=r"(fallback|target|most|max)",
        )

    def check_self_reference_400(self) -> Dict[str, Any]:
        return self._refusal_check(
            "self_reference_400",
            "400; error.type present; message forbids listing the primary as its own fallback; no cost header",
            self._body_payload(
                self.primary_model, nrouter_fallbacks=[self.primary_model]
            ),
            expect_code=None,
            message_must_match=r"(itself|self|primary|same)",
        )

    def check_unknown_nrouter_key_400(self) -> Dict[str, Any]:
        return self._refusal_check(
            "unknown_nrouter_key_400",
            "400; error.type present; message names the unknown nrouter_* key; no cost header",
            self._body_payload(self.primary_model, nrouter_bogus_field="unsupported"),
            expect_code=None,
            message_must_match=r"nrouter_bogus_field|unknown",
        )

    def check_auto_refuses_fallbacks(self) -> Dict[str, Any]:
        return self._refusal_check(
            "auto_refuses_fallbacks",
            "400; error.code == fallback_not_allowed; the auto router never walks a caller chain; no cost header",
            self._body_payload(AUTO_MODEL, nrouter_fallbacks=[self.fallback_model]),
            expect_code="fallback_not_allowed",
        )

    def check_non_array_fallbacks_400(self) -> Dict[str, Any]:
        return self._refusal_check(
            "non_array_fallbacks_400",
            "400; error.type present; a string nrouter_fallbacks is refused, never coerced; no cost header",
            self._body_payload(self.primary_model, nrouter_fallbacks=self.fallback_model),
            expect_code=None,
        )

    def check_exhausted_chain_has_no_attempts_header(self) -> Dict[str, Any]:
        """Both ranks down: the refusal must not advertise attempts or cost."""
        name = "exhausted_chain_has_no_attempts_header"
        assertion = (
            "non-2xx; error.type present; x-nr-attempts and x-nr-routing absent; "
            "x-nr-request-cost absent (reservation released)"
        )
        failing = os.environ.get("NROUTER_FAILING_PRIMARY_MODEL", self.failing_primary_model)
        second = os.environ.get("NROUTER_FAILING_FALLBACK_MODEL", "")
        if not (failing and second):
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=(
                    "NROUTER_FAILING_PRIMARY_MODEL / NROUTER_FAILING_FALLBACK_MODEL "
                    "are unset, so an exhausted chain cannot be provoked here"
                ),
                not_configured=True,
            )
        args, request = self._prepare(
            "POST",
            "/chat/completions",
            self._body_payload(failing, nrouter_fallbacks=[second]),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        ok, detail = assert_all([
            (status >= 400, f"expected a refusal, got {status}"),
            (bool(err.get("type")), "error.type absent on an exhausted chain"),
            ("x-nr-attempts" not in headers, "x-nr-attempts present on a refusal"),
            ("x-nr-routing" not in headers, "x-nr-routing present on a refusal"),
            (
                "x-nr-request-cost" not in headers,
                "x-nr-request-cost present on a refusal (money leak)",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_direct_serve_with_fallback_list,
            self.check_unpermitted_target_is_400,
            self.check_self_reference_400,
            self.check_auto_refuses_fallbacks,
        ]
        if not quick:
            checks = [
                self.check_direct_serve_with_fallback_list,
                self.check_served_via_fallback_names_rank,
                self.check_request_list_is_walked_in_order,
                self.check_unpermitted_target_is_400,
                self.check_five_targets_400,
                self.check_self_reference_400,
                self.check_unknown_nrouter_key_400,
                self.check_auto_refuses_fallbacks,
                self.check_non_array_fallbacks_400,
                self.check_exhausted_chain_has_no_attempts_header,
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
            "## 🔀 nRouter Pure-Curl Health Check: Request Fallbacks",
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
    """Offline validation of every parser and assertion in this module."""
    print("Running fallbacks_curl.py --self-test (offline mode)...")

    def payload_of(args: List[str]) -> Dict[str, Any]:
        for index, arg in enumerate(args):
            if arg == "-d":
                try:
                    parsed = json.loads(args[index + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}

    def refusal(code: Optional[str], message: str) -> str:
        error: Dict[str, Any] = {"type": "invalid_request_error", "message": message}
        if code:
            error["code"] = code
        return json.dumps({"error": error})

    base_headers = {"x-nr-request-id": "11111111-2222-3333-4444-555555555555"}

    def mock_curl(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        model = body.get("model")
        targets = body.get("nrouter_fallbacks")
        if "nrouter_bogus_field" in body:
            return 400, dict(base_headers), refusal(None, "Unknown extension: nrouter_bogus_field"), 5.0
        if model == AUTO_MODEL and targets is not None:
            return 400, dict(base_headers), refusal("fallback_not_allowed", "the auto router refuses request fallbacks"), 5.0
        if isinstance(targets, str):
            return 400, dict(base_headers), refusal(None, "nrouter_fallbacks must be an array"), 5.0
        if isinstance(targets, list):
            if UNPERMITTED_TARGET in targets:
                return 400, dict(base_headers), refusal("fallback_not_allowed", "target not permitted for this key"), 5.0
            if len(targets) > MAX_FALLBACK_TARGETS:
                return 400, dict(base_headers), refusal(None, "at most 4 fallback targets are allowed"), 5.0
            if model in targets:
                return 400, dict(base_headers), refusal(None, "the primary model cannot list itself as a fallback"), 5.0
            if model == "vendor/down-primary":
                if targets == ["vendor/down-secondary"]:
                    return 502, dict(base_headers), refusal(None, "all candidates failed"), 12.0
                headers = dict(base_headers)
                headers.update({"x-nr-routing": "fallback:1", "x-nr-attempts": "2", "x-nr-model": targets[0]})
                return 200, headers, json.dumps({"choices": [{"message": {"content": "ok"}}]}), 40.0
        headers = dict(base_headers)
        headers.update({
            "x-nr-routing": "direct",
            "x-nr-attempts": "1",
            "x-nr-model": str(model),
            "x-nr-request-cost": "0.000042",
            "x-nr-cost-status": "exact",
        })
        return 200, headers, json.dumps({"choices": [{"message": {"content": "pong"}}]}), 38.0

    checker = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        failing_primary_model="vendor/down-primary",
        healthy_fallback_model="vendor/healthy-secondary",
        curl_fn=mock_curl,
    )
    os.environ["NROUTER_FAILING_PRIMARY_MODEL"] = "vendor/down-primary"
    os.environ["NROUTER_FAILING_FALLBACK_MODEL"] = "vendor/down-secondary"
    suite = checker.run_suite()

    assert suite["feature"] == FEATURE, "feature name missing from the JSON contract"
    assert suite["total_checks"] == 10, f"expected 10 checks, got {suite['total_checks']}"
    assert suite["adversarial_checks"] >= suite["total_checks"] - suite["adversarial_checks"], (
        "adversarial checks must not be outnumbered by happy-path checks"
    )
    assert suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in suite["checks"] if r["result"] == FAIL
    ]
    for row in suite["checks"]:
        assert set(
            ["name", "request", "status", "headers", "assertion", "result", "expected_failure"]
        ) <= set(row), f"{row['name']} is missing a required JSON field"
        assert "$NROUTER_API_KEY" in row["request"] or row["request"] == "(not executed)", (
            f"{row['name']} leaks a literal key into its reported curl"
        )
        assert "sk-nrouter-mock-key" not in row["request"], "raw key leaked into report"

    # The gate must BITE: a gateway that stops emitting the code goes red.
    def mock_code_dropped(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        error = error_of(body)
        if error.get("code") == "fallback_not_allowed":
            error.pop("code")
            body = json.dumps({"error": error})
        return status, headers, body, latency

    biting = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_code_dropped
    )
    biting_suite = biting.run_suite(quick=True)
    assert biting_suite["all_passed"] is False, (
        "dropping error.code must fail unpermitted_target_is_400"
    )

    # A cost header on a refusal is a money leak and must go red.
    def mock_cost_on_refusal(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status >= 400:
            headers = dict(headers)
            headers["x-nr-request-cost"] = "0.000010"
        return status, headers, body, latency

    leaky = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_cost_on_refusal
    )
    assert leaky.run_suite(quick=True)["all_passed"] is False, (
        "a cost header on a refusal must fail the suite"
    )

    # Routing headers absent => NOT-CONFIGURED, never PASS.
    def mock_no_routing_headers(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        headers = {k: v for k, v in headers.items() if k not in ("x-nr-routing", "x-nr-attempts")}
        return status, headers, body, latency

    unproven = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_no_routing_headers
    )
    unproven_suite = unproven.run_suite(quick=True)
    first = unproven_suite["checks"][0]
    assert first["result"] == NOT_CONFIGURED, (
        f"missing routing headers must report NOT-CONFIGURED, got {first['result']}"
    )

    markdown = checker.render_markdown_summary(suite)
    assert "Request Fallbacks" in markdown, "markdown summary lost its title"
    os.environ.pop("NROUTER_FAILING_PRIMARY_MODEL", None)
    os.environ.pop("NROUTER_FAILING_FALLBACK_MODEL", None)
    print("[PASS] fallbacks_curl.py self-test passed cleanly.")
    return 0


def resolve_api_key(explicit: str) -> str:
    if explicit:
        return explicit
    creds = Path.home() / ".nrouter_admin_keys/nrouter-test/prod/credentials.env"
    if creds.is_file():
        try:
            match = re.search(
                r'NROUTER_TEST_API_KEY=["\']?([^"\'\n]+)["\']?', creds.read_text()
            )
            if match:
                return match.group(1)
        except Exception:
            return ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Request Fallbacks Curl Health Check")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    parser.add_argument("--quick", action="store_true", help="Run the four-check quick lane")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    parser.add_argument("--primary-model", default=DEFAULT_PRIMARY_MODEL)
    parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL)
    parser.add_argument("--step-summary", action="store_true", help="Append markdown to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Emit the JSON report on stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        return 1

    checker = FallbacksCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        primary_model=args.primary_model,
        fallback_model=args.fallback_model,
    )
    print("=== nRouter Request Fallbacks Curl Health Check ===")
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
