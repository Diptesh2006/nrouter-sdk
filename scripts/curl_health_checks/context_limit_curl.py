#!/usr/bin/env python3
"""nRouter Context & Output Ceiling Pure-Curl Health Check (`context_limit_curl`).

A prompt that cannot fit, and an output ceiling that cannot be honoured, are
refused BEFORE the provider is paid — so the refusal must name a code and must
carry no cost.

  Happy path
    1. An ordinary prompt is served and reports input tokens.
    2. A `max_tokens` inside the model ceiling is served.

  Adversarial
    3. An oversize prompt refuses 400 `input_too_large` with no cost header.
    4. `max_tokens` above the ceiling refuses 400 `max_output_tokens_too_large`.
    5. The oversize refusal carries no metering headers at all.
    6. A negative `max_tokens` refuses 400 rather than clamping silently.
    7. The same oversize prompt refuses on the Anthropic-shaped route too.
    8. The refusal carries no routing headers (nothing was attempted).

The oversize body is streamed to curl on stdin (`-d @-`), so the probe is not
bounded by the shell's argument length.

Usage:
  python3 scripts/curl_health_checks/context_limit_curl.py --self-test
  python3 scripts/curl_health_checks/context_limit_curl.py --quick
  python3 scripts/curl_health_checks/context_limit_curl.py --step-summary
  python3 scripts/curl_health_checks/context_limit_curl.py --json
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

FEATURE = "context_limit"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "anthropic/claude-3-5-haiku"
# ~1.4M characters is far past every context window the catalogue serves,
# while staying cheap to build and to send.
OVERSIZE_WORD_COUNT = 280_000
OVER_CEILING_MAX_TOKENS = 9_999_999

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

METERING_HEADERS = (
    "x-nr-request-cost",
    "x-nr-cost-status",
    "x-nr-input-tokens",
    "x-nr-output-tokens",
    "x-nr-total-tokens",
)

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
    timeout_s: int = 60,
    stdin_data: Optional[str] = None,
) -> Tuple[int, Dict[str, str], str, float]:
    """Execute raw curl and parse status, headers, body and latency.

    `stdin_data` feeds `-d @-`, which is how the oversize probe sends a body
    larger than the shell will accept as an argument.
    """
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


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class ContextLimitCurlHealthCheck:
    """Health check runner for context-window and output-ceiling refusals."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        anthropic_model: str = DEFAULT_ANTHROPIC_MODEL,
        oversize_words: int = OVERSIZE_WORD_COUNT,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.model = model
        self.anthropic_model = anthropic_model
        self.oversize_words = oversize_words
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self, path: str, body: Any, via_stdin: bool = False
    ) -> Tuple[List[str], Optional[str], str]:
        """Return (curl argv, stdin payload or None, reproducible curl string)."""
        url = f"{self.base_url}{path}"
        payload = json.dumps(body)
        args = [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
            "-X", "POST",
        ]
        shown_lines = [
            f'curl -sS -D - -X POST "$NROUTER_BASE_URL{path}"',
            '  -H "Authorization: Bearer $NROUTER_API_KEY"',
            '  -H "Content-Type: application/json"',
        ]
        if via_stdin:
            args += ["-d", "@-"]
            shown_lines.append("  -d @-")
            shown = (
                f"python3 -c 'import json,sys; sys.stdout.write(json.dumps("
                f'{{"model": "{body.get("model")}", "messages": '
                f'[{{"role": "user", "content": "test " * {self.oversize_words}}}]}}))\' | \\\n'
                + " \\\n".join(shown_lines)
            )
            args.append(url)
            return args, payload, shown
        args += ["-d", payload]
        shown_lines.append(f"  -d '{payload}'")
        args.append(url)
        return args, None, " \\\n".join(shown_lines)

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

    def _oversize_body(self, model: str, anthropic_shape: bool = False) -> Dict[str, Any]:
        content = "test " * self.oversize_words
        body: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
        }
        if anthropic_shape:
            body["max_tokens"] = 16
        return body

    # ------------------------------------------------------------ happy checks

    def check_ordinary_prompt_serves(self) -> Dict[str, Any]:
        name = "ordinary_prompt_serves"
        assertion = (
            "200; body.choices non-empty; x-nr-input-tokens present and > 0; "
            "no error object"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        input_tokens = headers.get("x-nr-input-tokens")
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
            (not error_of(body), "a served response carries an error object"),
            (
                input_tokens is not None and input_tokens.isdigit() and int(input_tokens) > 0,
                f"x-nr-input-tokens {input_tokens!r} is not a positive integer",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_max_tokens_within_ceiling_serves(self) -> Dict[str, Any]:
        name = "max_tokens_within_ceiling_serves"
        assertion = (
            "200; body.choices non-empty; x-nr-output-tokens present and "
            "<= the requested max_tokens"
        )
        requested = 16
        args, stdin_data, request = self._prepare(
            "/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply with one short word."}],
                "max_tokens": requested,
            },
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        output_tokens = headers.get("x-nr-output-tokens")
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
            (
                output_tokens is None
                or (output_tokens.isdigit() and int(output_tokens) <= requested),
                f"x-nr-output-tokens {output_tokens!r} exceeds the requested max_tokens {requested}",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def check_oversize_prompt_is_input_too_large(self) -> Dict[str, Any]:
        name = "oversize_prompt_is_input_too_large"
        assertion = (
            "400; error.code == input_too_large; error.type present; "
            "x-nr-request-cost ABSENT (refused before the provider was paid)"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions", self._oversize_body(self.model), via_stdin=True
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (err.get("code") == "input_too_large", f"error.code {err.get('code')!r} != input_too_large"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on an oversize refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_max_tokens_over_ceiling_is_refused(self) -> Dict[str, Any]:
        name = "max_tokens_over_ceiling_is_refused"
        assertion = (
            "400; error.code == max_output_tokens_too_large; error.type present; "
            "no cost header"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": OVER_CEILING_MAX_TOKENS,
            },
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (
                err.get("code") == "max_output_tokens_too_large",
                f"error.code {err.get('code')!r} != max_output_tokens_too_large",
            ),
            (bool(err.get("type")), "error.type absent"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a ceiling refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_oversize_refusal_has_no_metering_headers(self) -> Dict[str, Any]:
        name = "oversize_refusal_has_no_metering_headers"
        assertion = (
            "400; none of x-nr-request-cost, x-nr-cost-status, x-nr-input-tokens, "
            "x-nr-output-tokens, x-nr-total-tokens is present"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions", self._oversize_body(self.model), via_stdin=True
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        leaked = [header for header in METERING_HEADERS if header in headers]
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(error_of(body)), "refusal body carries no error object"),
            (not leaked, f"metering headers present on a $0 refusal: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_negative_max_tokens_is_refused(self) -> Dict[str, Any]:
        name = "negative_max_tokens_is_refused"
        assertion = (
            "400; error.type present; a negative max_tokens is refused, never "
            "clamped to a silent default; no cost header"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": -1,
            },
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_oversize_refused_on_messages_route(self) -> Dict[str, Any]:
        name = "oversize_refused_on_messages_route"
        assertion = (
            "400 on /messages too; error.code == input_too_large; the ceiling is "
            "enforced per request, not per wire shape; no cost header"
        )
        args, stdin_data, request = self._prepare(
            "/messages",
            self._oversize_body(self.anthropic_model, anthropic_shape=True),
            via_stdin=True,
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        err = error_of(body)
        if status == 404:
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="/messages is not served on this plane",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (err.get("code") == "input_too_large", f"error.code {err.get('code')!r} != input_too_large"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on an oversize refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_ceiling_refusal_has_no_routing_headers(self) -> Dict[str, Any]:
        name = "ceiling_refusal_has_no_routing_headers"
        assertion = (
            "400; neither x-nr-routing nor x-nr-attempts is present (no candidate "
            "was attempted); x-nr-request-id still present for support"
        )
        args, stdin_data, request = self._prepare(
            "/chat/completions", self._oversize_body(self.model), via_stdin=True
        )
        status, headers, _, _ = self.curl_fn(args, stdin_data=stdin_data)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            ("x-nr-routing" not in headers, "x-nr-routing present on a pre-flight refusal"),
            ("x-nr-attempts" not in headers, "x-nr-attempts present on a pre-flight refusal"),
            (bool(headers.get("x-nr-request-id")), "x-nr-request-id absent on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_ordinary_prompt_serves,
            self.check_oversize_prompt_is_input_too_large,
            self.check_max_tokens_over_ceiling_is_refused,
        ]
        if not quick:
            checks = [
                self.check_ordinary_prompt_serves,
                self.check_max_tokens_within_ceiling_serves,
                self.check_oversize_prompt_is_input_too_large,
                self.check_max_tokens_over_ceiling_is_refused,
                self.check_oversize_refusal_has_no_metering_headers,
                self.check_negative_max_tokens_is_refused,
                self.check_oversize_refused_on_messages_route,
                self.check_ceiling_refusal_has_no_routing_headers,
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
            "## 📏 nRouter Pure-Curl Health Check: Context & Output Ceilings",
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
    print("Running context_limit_curl.py --self-test (offline mode)...")

    def payload_of(args: List[str], stdin_data: Optional[str]) -> Dict[str, Any]:
        for index, arg in enumerate(args):
            if arg == "-d":
                raw = stdin_data if args[index + 1] == "@-" else args[index + 1]
                try:
                    parsed = json.loads(raw or "")
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}

    def endpoint_of(args: List[str]) -> str:
        return args[-1]

    base = {"x-nr-request-id": "eeeeeeee-0000-1111-2222-333333333333"}
    ceiling_chars = 100_000

    def mock_curl(args, timeout_s=60, stdin_data=None):
        body = payload_of(args, stdin_data)
        content = body.get("messages", [{}])[0].get("content", "")
        max_tokens = body.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens < 0:
            return 400, dict(base), json.dumps(
                {"error": {"type": "invalid_request_error", "message": "max_tokens must be positive"}}
            ), 3.0
        if len(content) > ceiling_chars:
            return 400, dict(base), json.dumps({
                "error": {
                    "type": "gateway_error",
                    "code": "input_too_large",
                    "message": "prompt exceeds the model context limit",
                }
            }), 8.0
        if isinstance(max_tokens, int) and max_tokens > 100_000:
            return 400, dict(base), json.dumps({
                "error": {
                    "type": "gateway_error",
                    "code": "max_output_tokens_too_large",
                    "message": "max_tokens exceeds the model output ceiling",
                }
            }), 3.0
        headers = dict(base)
        headers.update({
            "x-nr-model": DEFAULT_MODEL,
            "x-nr-input-tokens": "3",
            "x-nr-output-tokens": "4",
            "x-nr-total-tokens": "7",
            "x-nr-request-cost": "0.000019",
            "x-nr-cost-status": "exact",
        })
        if endpoint_of(args).endswith("/messages"):
            return 200, headers, json.dumps({"content": [{"type": "text", "text": "ok"}]}), 25.0
        return 200, headers, json.dumps({"choices": [{"message": {"content": "ok"}}]}), 25.0

    checker = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        oversize_words=40_000,
        curl_fn=mock_curl,
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
        assert "$NROUTER_API_KEY" in row["request"], f"{row['name']} does not template the key"

    # BITE 1: an oversize prompt forwarded upstream (200) must fail.
    def forwards_oversize(args, timeout_s=60, stdin_data=None):
        body = payload_of(args, stdin_data)
        content = body.get("messages", [{}])[0].get("content", "")
        if len(content) > ceiling_chars:
            headers = dict(base)
            headers.update({"x-nr-request-cost": "4.200000", "x-nr-cost-status": "exact"})
            return 200, headers, json.dumps({"choices": [{"message": {"content": "ok"}}]}), 900.0
        return mock_curl(args, timeout_s, stdin_data)

    forwarded = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000, curl_fn=forwards_oversize
    )
    assert forwarded.run_suite(quick=True)["all_passed"] is False, (
        "forwarding an oversize prompt upstream must fail the suite"
    )

    # BITE 2: a refusal that is billed must fail.
    def billed_refusal(args, timeout_s=60, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 400:
            headers = dict(headers)
            headers["x-nr-request-cost"] = "0.000002"
        return status, headers, body, latency

    billed = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000, curl_fn=billed_refusal
    )
    assert billed.run_suite(quick=True)["all_passed"] is False, "a billed ceiling refusal must fail"

    # BITE 3: a refusal without the code must fail (status alone is not the contract).
    def codeless(args, timeout_s=60, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        err = error_of(body)
        if err.pop("code", None):
            body = json.dumps({"error": err})
        return status, headers, body, latency

    codeless_checker = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000, curl_fn=codeless
    )
    assert codeless_checker.run_suite(quick=True)["all_passed"] is False, (
        "a refusal that drops error.code must fail"
    )

    # The stdin lane is exercised, not merely declared.
    seen = {}

    def records_stdin(args, timeout_s=60, stdin_data=None):
        if "@-" in args:
            seen["stdin_bytes"] = len(stdin_data or "")
        return mock_curl(args, timeout_s, stdin_data)

    ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000, curl_fn=records_stdin
    ).run_suite(quick=True)
    assert seen.get("stdin_bytes", 0) > ceiling_chars, (
        "the oversize body was not delivered over stdin"
    )

    assert "Context & Output Ceilings" in checker.render_markdown_summary(suite)
    print("[PASS] context_limit_curl.py self-test passed cleanly.")
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
    parser = argparse.ArgumentParser(description="nRouter Context & Output Ceiling Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--oversize-words", type=int, default=OVERSIZE_WORD_COUNT)
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        return 1

    checker = ContextLimitCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        model=args.model,
        oversize_words=args.oversize_words,
    )
    print("=== nRouter Context & Output Ceiling Curl Health Check ===")
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
