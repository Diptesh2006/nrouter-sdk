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
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Shared plumbing: ONE curl invocation, ONE response parser, ONE credential rule.
# `run_curl` here also carries the stdin lane (`-d @-`) this module depends on.
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
    ALLOWED_ROUTES,
    add_wire_arguments,
    assert_all,
    build_body,
    build_multiturn_body,
    emit_results,
    error_of,
    json_stdout_contract_self_test,
    max_tokens_field,
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
    served_body_for,
    served_body_ok,
    suite_verdict,
    wire_contract_self_test,
)

FEATURE = "context_limit"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "anthropic/claude-3-5-haiku"
# ~1.4M characters is far past every context window the catalogue serves,
# while staying cheap to build and to send.
OVERSIZE_WORD_COUNT = 280_000
OVER_CEILING_MAX_TOKENS = 9_999_999

def wire_of_route_label(path: str) -> str:
    """A short human label for the wire a path speaks, for report prose."""
    return {
        "/chat/completions": "chat-completions",
        "/messages": "messages",
        "/responses": "responses",
        "/completions": "completions",
    }.get(path, "chat-completions")


METERING_HEADERS = (
    "x-nr-request-cost",
    "x-nr-cost-status",
    "x-nr-input-tokens",
    "x-nr-output-tokens",
    "x-nr-total-tokens",
)


class ContextLimitCurlHealthCheck:
    """Health check runner for context-window and output-ceiling refusals."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        oversize_words: int = OVERSIZE_WORD_COUNT,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.oversize_words = oversize_words
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self, path: str, body: Any, via_stdin: bool = False
    ) -> Tuple[List[str], Optional[str], str]:
        """Return (curl argv, stdin payload or None, reproducible curl string)."""
        self._current_path = path
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
                "python3 -c 'import json,sys; sys.stdout.write(json.dumps(BODY))' | \\\n"
                f"  # BODY = a {wire_of_route_label(path)} request for "
                f'"{body.get("model")}" carrying "test " * {self.oversize_words}\n'
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

    def _oversize_body(self, model: str) -> Dict[str, Any]:
        return build_body(self.route, model, "test " * self.oversize_words, max_tokens=16)

    def _oversize_multiturn_body(self, model: str) -> Dict[str, Any]:
        """The same volume of text spread across a conversation.

        The ceiling counts the WHOLE request, not the last turn, so this must be
        refused exactly as the single-turn version is. On the single-field wires
        the turns are joined, which is the same bytes by another name.
        """
        chunk = "test " * max(1, self.oversize_words // 4)
        return build_multiturn_body(self.route, model, [chunk] * 4, max_tokens=16)

    # ------------------------------------------------------------ happy checks

    def check_ordinary_prompt_serves(self) -> Dict[str, Any]:
        name = "ordinary_prompt_serves"
        assertion = (
            "200; the wire's served body carries a completion; x-nr-input-tokens "
            "present and > 0; no error object"
        )
        args, stdin_data, request = self._prepare(
            self.route, build_body(self.route, self.model, "ping", max_tokens=8)
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        input_tokens = headers.get("x-nr-input-tokens")
        body_ok, body_detail = served_body_ok(self.route, body)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (body_ok, body_detail),
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
            f"200; the wire's served body carries a completion; x-nr-output-tokens "
            f"present and <= the requested {max_tokens_field(self.route)}"
        )
        requested = 16
        args, stdin_data, request = self._prepare(
            self.route,
            build_body(
                self.route, self.model, "Reply with one short word.", max_tokens=requested
            ),
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        output_tokens = headers.get("x-nr-output-tokens")
        body_ok, body_detail = served_body_ok(self.route, body)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (body_ok, body_detail),
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
            self.route, self._oversize_body(self.model), via_stdin=True
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
            self.route,
            build_body(self.route, self.model, "ping", max_tokens=OVER_CEILING_MAX_TOKENS),
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
            self.route, self._oversize_body(self.model), via_stdin=True
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
            self.route, build_body(self.route, self.model, "ping", max_tokens=-1)
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

    def check_oversize_multiturn_is_input_too_large(self) -> Dict[str, Any]:
        name = "oversize_multiturn_is_input_too_large"
        assertion = (
            "400; error.code == input_too_large; the ceiling counts the WHOLE "
            "request, not just the last turn, so the same volume split across a "
            "conversation is refused identically; no cost header"
        )
        args, stdin_data, request = self._prepare(
            self.route, self._oversize_multiturn_body(self.model), via_stdin=True
        )
        status, headers, body, _ = self.curl_fn(args, stdin_data=stdin_data)
        err = error_of(body)
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
            self.route, self._oversize_body(self.model), via_stdin=True
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
                self.check_oversize_multiturn_is_input_too_large,
                self.check_ceiling_refusal_has_no_routing_headers,
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
            "## 📏 nRouter Pure-Curl Health Check: Context & Output Ceilings",
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
    print("Running context_limit_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

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

    def route_of(args: List[str]) -> str:
        """Which wire this request was made on, read back from the URL it asked.

        The mock must answer in that wire's shape, so it has to recover the
        route rather than assume one.
        """
        url = endpoint_of(args)
        for candidate in ALLOWED_ROUTES:
            if url.endswith(candidate):
                return candidate
        return "/chat/completions"

    base = {"x-nr-request-id": "eeeeeeee-0000-1111-2222-333333333333"}
    ceiling_chars = 100_000

    def request_text(body: Dict[str, Any]) -> str:
        """Every byte of prompt in the request, on whichever wire it arrived.

        The ceiling counts the WHOLE request, so the double models that: the
        multi-turn probe must be refused even though no single turn is oversize.
        """
        if isinstance(body.get("messages"), list):
            return "".join(
                str(turn.get("content", ""))
                for turn in body["messages"]
                if isinstance(turn, dict)
            )
        return str(body.get("input") or body.get("prompt") or "")

    def mock_curl(args, timeout_s=60, stdin_data=None):
        body = payload_of(args, stdin_data)
        content = request_text(body)
        max_tokens = body.get("max_tokens", body.get("max_output_tokens"))
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
        # The upstream answers in the shape of the wire it was ASKED on. A mock
        # that always returns `choices` makes three wires out of four fail
        # against the mock rather than against the gateway.
        return 200, headers, json.dumps(served_body_for(route_of(args), "ok")), 25.0

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

    # A transport failure while sending a multi-megabyte body is a FAIL, never a
    # quiet pass and never an absent precondition: curl 55/56 on a large upload
    # is exactly the case where a partial read used to look like a clean 400.
    def upload_truncated(args, timeout_s=60, stdin_data=None):
        return 0, {}, "curl exit code 55: Send failure", 40.0

    truncated = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000,
        curl_fn=upload_truncated,
    )
    truncated_suite = truncated.run_suite()
    assert truncated_suite["all_passed"] is False, "a failed upload must fail the suite"
    assert truncated_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # A gateway that measures only the LAST turn lets the same volume of text
    # through when it is split across a conversation. That must FAIL.
    def counts_only_last_turn(args, timeout_s=60, stdin_data=None):
        body = payload_of(args, stdin_data)
        turns = body.get("messages")
        if isinstance(turns, list) and len(turns) > 1:
            last = str(turns[-1].get("content", ""))
            if len(last) <= ceiling_chars:
                headers = dict(base)
                headers.update({"x-nr-request-cost": "3.100000", "x-nr-cost-status": "exact"})
                return 200, headers, json.dumps({"choices": [{"message": {"content": "ok"}}]}), 800.0
        return mock_curl(args, timeout_s, stdin_data)

    partial_counter = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=40_000,
        curl_fn=counts_only_last_turn,
    )
    partial_row = next(
        r for r in partial_counter.run_suite()["checks"]
        if r["name"] == "oversize_multiturn_is_input_too_large"
    )
    assert partial_row["result"] == FAIL, (
        "a ceiling that counts only the last turn must FAIL; got "
        f"{partial_row['result']}"
    )

    # BOTH WIRES: the ceiling is the same on the Anthropic-shaped wire, where
    # the served body has no `choices` and max_tokens is mandatory.
    messages_suite = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001", oversize_words=40_000, curl_fn=mock_curl,
    ).run_suite()
    assert messages_suite["route"] == "/messages"
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]

    # The /responses wire names its ceiling `max_output_tokens`, and the probe
    # must send THAT field or it is testing nothing.
    responses_checker = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/responses",
        model="openai/gpt-4o-mini", oversize_words=40_000, curl_fn=mock_curl,
    )
    responses_suite = responses_checker.run_suite()
    ceiling_request = next(
        r["request"] for r in responses_suite["checks"]
        if r["name"] == "max_tokens_over_ceiling_is_refused"
    )
    assert "max_output_tokens" in ceiling_request, ceiling_request
    assert '"max_tokens"' not in ceiling_request, (
        "the responses wire was sent a chat-shaped ceiling field"
    )
    # ---- R6: the mock must answer in THIS wire's shape ---------------------
    # Asserting the request field and stopping there left the SERVED side
    # untested: the mock answered `choices` on every wire, so the suite was red
    # against the mock rather than green against the gateway. A ceiling suite
    # that cannot go green on a wire proves nothing about that wire.
    assert responses_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in responses_suite["checks"] if r["result"] == FAIL
    ]
    completions_suite = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/completions",
        model="openai/gpt-4o-mini", oversize_words=40_000, curl_fn=mock_curl,
    ).run_suite()
    assert completions_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in completions_suite["checks"] if r["result"] == FAIL
    ]

    # ...and at least one oversize probe still sends NO output ceiling at all,
    # so the INPUT ceiling is proven on its own rather than only in company with
    # an output-ceiling refusal that would mask it.
    oversize_requests = [
        r["request"] for r in suite["checks"]
        if "oversize" in r["name"] and r["request"] != "(not executed)"
    ]
    assert oversize_requests, "no oversize probe in the suite"
    assert any(
        '"max_tokens"' not in req and '"max_output_tokens"' not in req
        for req in oversize_requests
    ), "every oversize probe now names an output ceiling; the input ceiling is no longer isolated"

    # A route-scoped key short-circuits as NOT-CONFIGURED, not as failures.
    def mock_route_not_allowed(args, timeout_s=60, stdin_data=None):
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = ContextLimitCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", oversize_words=1_000,
        curl_fn=mock_route_not_allowed,
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

    assert "Context & Output Ceilings" in checker.render_markdown_summary(suite)
    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] context_limit_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Context & Output Ceiling Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)
    parser.add_argument("--oversize-words", type=int, default=OVERSIZE_WORD_COUNT)
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
        checker = ContextLimitCurlHealthCheck(
            base_url=args.base_url,
            api_key=api_key,
            route=args.route,
            model=args.model,
            oversize_words=args.oversize_words,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Context & Output Ceiling Curl Health Check ===\n"
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
