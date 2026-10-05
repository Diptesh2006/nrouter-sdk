#!/usr/bin/env python3
"""nRouter Per-Request Guardrails Pure-Curl Health Check (`guardrails_request_curl`).

`nrouter_guardrails` is ADD-ONLY: a request may ADD guardrails of its own
organization to the chain the platform and the tenant already impose. It can
never remove, downgrade or displace one.

  Happy path
    1. A keyword blocked by an ADDED guardrail refuses 400 with
       `x-nr-guardrails: blocked` and no cost header.
    2. A benign prompt carrying the same addition is still SERVED.
    3. A tenant block rule survives an unrelated addition.

  Adversarial
    4. An unknown guardrail id refuses 400 `guardrail_not_found`.
    5. A foreign organization's id returns the SAME message as an unknown id
       (no cross-tenant existence oracle).
    6. More than eight requested guardrails refuses 400.
    7. A non-array `nrouter_guardrails` refuses 400.
    8. An empty-string id refuses 400.
    9. A guardrail refusal carries no cost and no token headers.
   10. The platform floor still blocks when an addition is present.

Usage:
  python3 scripts/curl_health_checks/guardrails_request_curl.py --self-test
  python3 scripts/curl_health_checks/guardrails_request_curl.py --quick
  python3 scripts/curl_health_checks/guardrails_request_curl.py --step-summary
  python3 scripts/curl_health_checks/guardrails_request_curl.py --json
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
    suite_verdict,
    wire_contract_self_test,
)

FEATURE = "guardrails_request"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_REQUEST_GUARDRAILS = 8
UNKNOWN_GUARDRAIL_ID = "00000000-0000-0000-0000-000000000000"
EXPLICIT_FLOOR_PROMPT = "sex porn"
BENIGN_PROMPT = "What is the capital of France?"

GUARDRAIL_HEADER_VALUES = {"none", "monitor", "redacted", "pass", "partial", "blocked", "unavailable"}


def is_guardrail_block(status: int, headers: Dict[str, str], body: str) -> bool:
    """Spec detection order: code, then type, then the compatibility message."""
    if status != 400:
        return False
    err = error_of(body)
    if err.get("code") == "guardrail_blocked" or err.get("type") == "guardrail_blocked":
        return True
    if headers.get("x-nr-guardrails") == "blocked":
        return True
    return "guardrail" in str(err.get("message", "")).lower()


class GuardrailsRequestCurlHealthCheck:
    """Health check runner for the add-only `nrouter_guardrails` contract."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        guardrail_id: Optional[str] = None,
        blocked_keyword: Optional[str] = None,
        tenant_block_keyword: Optional[str] = None,
        foreign_guardrail_id: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.guardrail_id = guardrail_id or os.environ.get("NROUTER_GUARDRAIL_ID", "")
        self.blocked_keyword = blocked_keyword or os.environ.get(
            "NROUTER_GUARDRAIL_BLOCK_KEYWORD", ""
        )
        self.tenant_block_keyword = tenant_block_keyword or os.environ.get(
            "NROUTER_TENANT_BLOCK_KEYWORD", ""
        )
        self.foreign_guardrail_id = foreign_guardrail_id or os.environ.get(
            "NROUTER_FOREIGN_GUARDRAIL_ID", ""
        )
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(self, path: str, body: Any) -> Tuple[List[str], str]:
        self._current_path = path
        url = f"{self.base_url}{path}"
        payload = json.dumps(body)
        args = [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
            "-X", "POST",
            "-d", payload,
            url,
        ]
        shown = " \\\n".join([
            f'curl -sS -D - -X POST "$NROUTER_BASE_URL{path}"',
            '  -H "Authorization: Bearer $NROUTER_API_KEY"',
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

    def _payload(self, prompt: str, **extra: Any) -> Dict[str, Any]:
        return build_body(self.route, self.model, prompt, max_tokens=16, **extra)

    # ------------------------------------------------------------ happy checks

    def check_added_guardrail_blocks_keyword(self) -> Dict[str, Any]:
        name = "added_guardrail_blocks_keyword"
        assertion = (
            "400; x-nr-guardrails == blocked; error.code or error.type == "
            "guardrail_blocked; x-nr-request-cost absent"
        )
        if not (self.guardrail_id and self.blocked_keyword):
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=(
                    "NROUTER_GUARDRAIL_ID / NROUTER_GUARDRAIL_BLOCK_KEYWORD unset: "
                    "this plane exposes no org-owned pre-call guardrail to add"
                ),
                not_configured=True,
            )
        args, request = self._prepare(
            self.route,
            self._payload(
                f"Tell me about {self.blocked_keyword}",
                nrouter_guardrails=[self.guardrail_id],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (
                headers.get("x-nr-guardrails") == "blocked",
                f"x-nr-guardrails {headers.get('x-nr-guardrails')!r} != blocked",
            ),
            (
                is_guardrail_block(status, headers, body),
                "body does not classify as guardrail_blocked",
            ),
            (
                "x-nr-request-cost" not in headers,
                "x-nr-request-cost present on a blocked prompt (money leak)",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_addition_is_add_only_benign_served(self) -> Dict[str, Any]:
        name = "addition_is_add_only_benign_served"
        assertion = (
            "200; x-nr-guardrails present, in the spec enum and != blocked; "
            "the wire's served body carries a completion"
        )
        if not self.guardrail_id:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail="NROUTER_GUARDRAIL_ID unset: no addition to send",
                not_configured=True,
            )
        args, request = self._prepare(
            self.route,
            self._payload(BENIGN_PROMPT, nrouter_guardrails=[self.guardrail_id]),
        )
        status, headers, body, _ = self.curl_fn(args)
        posture = headers.get("x-nr-guardrails")
        body_ok, body_detail = served_body_ok(self.route, body)
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (posture in GUARDRAIL_HEADER_VALUES, f"x-nr-guardrails {posture!r} outside the spec enum"),
            (posture != "blocked", "a benign prompt was blocked by an add-only guardrail"),
            (body_ok, body_detail),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_tenant_rule_survives_additions(self) -> Dict[str, Any]:
        name = "tenant_rule_survives_additions"
        assertion = (
            "400; x-nr-guardrails == blocked; an unrelated addition cannot "
            "displace the tenant block rule; no cost header"
        )
        if not (self.tenant_block_keyword and self.guardrail_id):
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=(
                    "NROUTER_TENANT_BLOCK_KEYWORD / NROUTER_GUARDRAIL_ID unset: "
                    "no tenant block rule to defend"
                ),
                not_configured=True,
            )
        args, request = self._prepare(
            self.route,
            self._payload(
                f"Please discuss {self.tenant_block_keyword} in detail",
                nrouter_guardrails=[self.guardrail_id],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (headers.get("x-nr-guardrails") == "blocked", "tenant block rule did not fire"),
            (is_guardrail_block(status, headers, body), "body does not classify as a guardrail block"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a blocked prompt"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ------------------------------------------------------ adversarial checks

    def _unknown_id_response(self, guardrail_id: str) -> Tuple[str, int, Dict[str, str], str]:
        args, request = self._prepare(
            self.route,
            self._payload(BENIGN_PROMPT, nrouter_guardrails=[guardrail_id]),
        )
        status, headers, body, _ = self.curl_fn(args)
        return request, status, headers, body

    def check_unknown_guardrail_id_400(self) -> Dict[str, Any]:
        name = "unknown_guardrail_id_400"
        assertion = (
            "400; error.code == guardrail_not_found; error.message non-empty; "
            "no cost header; x-nr-guardrails != blocked (this is a request error)"
        )
        request, status, headers, body = self._unknown_id_response(UNKNOWN_GUARDRAIL_ID)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (err.get("code") == "guardrail_not_found", f"error.code {err.get('code')!r} != guardrail_not_found"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_foreign_guardrail_id_is_indistinguishable(self) -> Dict[str, Any]:
        name = "foreign_guardrail_id_is_indistinguishable"
        assertion = (
            "400 for both; a foreign organization's real id returns byte-identical "
            "error.code and error.message to an id that does not exist anywhere "
            "(no cross-tenant existence oracle)"
        )
        if not self.foreign_guardrail_id:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=(
                    "NROUTER_FOREIGN_GUARDRAIL_ID unset: without a real id owned by "
                    "another organization this check cannot prove the absence of an oracle"
                ),
                not_configured=True,
            )
        _, unknown_status, _, unknown_body = self._unknown_id_response(UNKNOWN_GUARDRAIL_ID)
        request, status, headers, body = self._unknown_id_response(self.foreign_guardrail_id)
        unknown_err, foreign_err = error_of(unknown_body), error_of(body)
        normalize = lambda text, ident: str(text).replace(ident, "<id>")
        ok, detail = assert_all([
            (status == 400, f"expected 400 for the foreign id, got {status}"),
            (unknown_status == 400, f"expected 400 for the unknown id, got {unknown_status}"),
            (
                foreign_err.get("code") == unknown_err.get("code"),
                f"error.code differs: {foreign_err.get('code')!r} vs {unknown_err.get('code')!r}",
            ),
            (
                normalize(foreign_err.get("message"), self.foreign_guardrail_id)
                == normalize(unknown_err.get("message"), UNKNOWN_GUARDRAIL_ID),
                "error.message differs between a foreign id and a nonexistent id",
            ),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_more_than_eight_guardrails_400(self) -> Dict[str, Any]:
        name = "more_than_eight_guardrails_400"
        assertion = (
            f"400; error.type present; message names the {MAX_REQUEST_GUARDRAILS}-guardrail "
            "ceiling; no cost header"
        )
        args, request = self._prepare(
            self.route,
            self._payload(
                BENIGN_PROMPT,
                nrouter_guardrails=[
                    f"{UNKNOWN_GUARDRAIL_ID[:-1]}{n}" for n in range(MAX_REQUEST_GUARDRAILS + 1)
                ],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        message = str(err.get("message", ""))
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (
                re.search(r"(8|eight|most|max)", message, re.IGNORECASE) is not None,
                "error.message does not name the request-guardrail ceiling",
            ),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_non_array_guardrails_400(self) -> Dict[str, Any]:
        name = "non_array_guardrails_400"
        assertion = "400; error.type present; a string is refused, never coerced; no cost header"
        args, request = self._prepare(
            self.route,
            self._payload(BENIGN_PROMPT, nrouter_guardrails=UNKNOWN_GUARDRAIL_ID),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_empty_guardrail_id_400(self) -> Dict[str, Any]:
        name = "empty_guardrail_id_400"
        assertion = "400; error.type present; an empty id never resolves to 'all guardrails'; no cost header"
        args, request = self._prepare(
            self.route, self._payload(BENIGN_PROMPT, nrouter_guardrails=[""])
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_block_carries_no_token_headers(self) -> Dict[str, Any]:
        name = "block_carries_no_token_headers"
        assertion = (
            "400; x-nr-guardrails == blocked; none of x-nr-request-cost, "
            "x-nr-cost-status, x-nr-input-tokens, x-nr-output-tokens is present"
        )
        args, request = self._prepare(self.route, self._payload(EXPLICIT_FLOOR_PROMPT))
        status, headers, body, _ = self.curl_fn(args)
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
            (status == 400, f"expected 400, got {status}"),
            (headers.get("x-nr-guardrails") == "blocked", "x-nr-guardrails != blocked"),
            (is_guardrail_block(status, headers, body), "body does not classify as a guardrail block"),
            (not leaked, f"metering headers present on a $0 block: {leaked}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_floor_survives_addition(self) -> Dict[str, Any]:
        name = "floor_survives_addition"
        assertion = (
            "400; x-nr-guardrails == blocked; adding an unrelated guardrail cannot "
            "displace the platform floor; no cost header"
        )
        additions = [self.guardrail_id] if self.guardrail_id else [UNKNOWN_GUARDRAIL_ID]
        args, request = self._prepare(
            self.route,
            self._payload(EXPLICIT_FLOOR_PROMPT, nrouter_guardrails=additions),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        # The filler id is refused before the floor ever scores, which proves
        # nothing about the floor: the precondition (a real org guardrail) is
        # provably absent, so NOT-CONFIGURED.
        #
        # But if the operator DID supply NROUTER_GUARDRAIL_ID and the gateway
        # still says guardrail_not_found, their configured guardrail does not
        # resolve — that is a real defect and a FAIL, not a missing fixture.
        if err.get("code") == "guardrail_not_found":
            if self.guardrail_id:
                return self._record(
                    name, request, status, headers, assertion, False, True,
                    detail=(
                        "the configured NROUTER_GUARDRAIL_ID was rejected as "
                        "guardrail_not_found: the supplied guardrail does not resolve "
                        "for this key's organization"
                    ),
                )
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail=(
                    "no NROUTER_GUARDRAIL_ID was supplied, so the filler id was refused "
                    "before the floor ran; set it to a real org guardrail to exercise this"
                ),
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (headers.get("x-nr-guardrails") == "blocked", "the platform floor did not block"),
            (is_guardrail_block(status, headers, body), "body does not classify as a guardrail block"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a blocked prompt"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_unknown_guardrail_id_400,
            self.check_non_array_guardrails_400,
            self.check_block_carries_no_token_headers,
            self.check_addition_is_add_only_benign_served,
        ]
        if not quick:
            checks = [
                self.check_added_guardrail_blocks_keyword,
                self.check_addition_is_add_only_benign_served,
                self.check_tenant_rule_survives_additions,
                self.check_unknown_guardrail_id_400,
                self.check_foreign_guardrail_id_is_indistinguishable,
                self.check_more_than_eight_guardrails_400,
                self.check_non_array_guardrails_400,
                self.check_empty_guardrail_id_400,
                self.check_block_carries_no_token_headers,
                self.check_floor_survives_addition,
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
            "## 🛡️ nRouter Pure-Curl Health Check: Per-Request Guardrails",
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
    print("Running guardrails_request_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

    known_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    foreign_id = "ffffffff-1111-2222-3333-444444444444"

    def payload_of(args: List[str]) -> Dict[str, Any]:
        for index, arg in enumerate(args):
            if arg == "-d":
                try:
                    parsed = json.loads(args[index + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}

    base = {"x-nr-request-id": "99999999-8888-7777-6666-555555555555"}

    def mock_curl(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        prompt = body.get("messages", [{}])[0].get("content", "")
        additions = body.get("nrouter_guardrails")
        if isinstance(additions, str):
            return 400, dict(base), json.dumps(
                {"error": {"type": "invalid_request_error", "message": "nrouter_guardrails must be an array"}}
            ), 4.0
        if isinstance(additions, list):
            if len(additions) > MAX_REQUEST_GUARDRAILS:
                return 400, dict(base), json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "at most 8 request guardrails are allowed"}}
                ), 4.0
            for ident in additions:
                if ident != known_id:
                    return 400, dict(base), json.dumps({
                        "error": {
                            "type": "invalid_request_error",
                            "code": "guardrail_not_found",
                            "message": f'guardrail "{ident}" is not a pre-call guardrail of this organization',
                        }
                    }), 4.0
        if prompt.strip() == EXPLICIT_FLOOR_PROMPT or "tenant-forbidden" in prompt:
            headers = dict(base)
            headers["x-nr-guardrails"] = "blocked"
            return 400, headers, json.dumps({
                "error": {
                    "type": "guardrail_blocked",
                    "code": "guardrail_blocked",
                    "message": "request blocked by a guardrail",
                }
            }), 6.0
        if "forbidden_keyword" in prompt:
            headers = dict(base)
            headers["x-nr-guardrails"] = "blocked"
            return 400, headers, json.dumps({
                "error": {"type": "guardrail_blocked", "code": "guardrail_blocked", "message": "blocked term"}
            }), 6.0
        headers = dict(base)
        headers.update({
            "x-nr-guardrails": "pass",
            "x-nr-request-cost": "0.000031",
            "x-nr-cost-status": "exact",
            "x-nr-model": DEFAULT_MODEL,
        })
        if args[-1].endswith("/messages"):
            return 200, headers, json.dumps(
                {"content": [{"type": "text", "text": "Paris"}], "role": "assistant"}
            ), 30.0
        return 200, headers, json.dumps({"choices": [{"message": {"content": "Paris"}}]}), 30.0

    checker = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        guardrail_id=known_id,
        blocked_keyword="forbidden_keyword",
        tenant_block_keyword="tenant-forbidden",
        foreign_guardrail_id=foreign_id,
        curl_fn=mock_curl,
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

    # BITE 1: a foreign id that leaks its existence must fail.
    def mock_oracle(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        additions = body.get("nrouter_guardrails")
        if isinstance(additions, list) and foreign_id in additions:
            return 400, dict(base), json.dumps({
                "error": {
                    "type": "invalid_request_error",
                    "code": "guardrail_forbidden",
                    "message": "guardrail belongs to another organization",
                }
            }), 4.0
        return mock_curl(args, timeout_s, stdin_data)

    oracle = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        tenant_block_keyword="tenant-forbidden", foreign_guardrail_id=foreign_id,
        curl_fn=mock_oracle,
    )
    oracle_suite = oracle.run_suite()
    oracle_row = next(
        r for r in oracle_suite["checks"] if r["name"] == "foreign_guardrail_id_is_indistinguishable"
    )
    assert oracle_row["result"] == FAIL, "a cross-tenant existence oracle must go red"

    # BITE 2: a block that carries a cost header must fail.
    def mock_billed_block(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 400 and headers.get("x-nr-guardrails") == "blocked":
            headers = dict(headers)
            headers["x-nr-request-cost"] = "0.000004"
        return status, headers, body, latency

    billed = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        curl_fn=mock_billed_block,
    )
    assert billed.run_suite(quick=True)["all_passed"] is False, (
        "a billed guardrail block must fail the suite"
    )

    # NOT-CONFIGURED, never PASS, when the plane exposes no org guardrail.
    bare = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_curl
    )
    bare_suite = bare.run_suite()
    bare_row = next(r for r in bare_suite["checks"] if r["name"] == "added_guardrail_blocks_keyword")
    assert bare_row["result"] == NOT_CONFIGURED, bare_row["result"]

    # NOT-CONFIGURED must not mask a real defect: when an id WAS supplied and the
    # gateway cannot resolve it, that is a FAIL, not a missing fixture.
    def mock_rejects_configured_id(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        additions = body.get("nrouter_guardrails")
        if isinstance(additions, list) and known_id in additions:
            return 400, dict(base), json.dumps({
                "error": {
                    "type": "invalid_request_error",
                    "code": "guardrail_not_found",
                    "message": f'guardrail "{known_id}" is not a pre-call guardrail of this organization',
                }
            }), 4.0
        return mock_curl(args, timeout_s, stdin_data)

    unresolvable = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        curl_fn=mock_rejects_configured_id,
    )
    unresolvable_row = next(
        r for r in unresolvable.run_suite()["checks"] if r["name"] == "floor_survives_addition"
    )
    assert unresolvable_row["result"] == FAIL, (
        "a CONFIGURED guardrail id the gateway cannot resolve must FAIL, not report "
        f"NOT-CONFIGURED; got {unresolvable_row['result']}"
    )

    # A transport failure can only FAIL; it is never an absent precondition.
    def mock_transport_failure(args, timeout_s=40, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 9.0

    broken = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        curl_fn=mock_transport_failure,
    )
    broken_suite = broken.run_suite(quick=True)
    assert broken_suite["all_passed"] is False, "a transport failure must fail the suite"
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # BOTH WIRES: the same suite on the Anthropic-shaped wire, where a served
    # completion lives at content[0].text and there are no `choices` at all.
    messages_checker = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        tenant_block_keyword="tenant-forbidden", foreign_guardrail_id=foreign_id,
        curl_fn=mock_curl,
    )
    messages_suite = messages_checker.run_suite()
    assert messages_suite["route"] == "/messages"
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]
    assert "$NROUTER_BASE_URL/messages" in messages_suite["checks"][0]["request"]

    # A route-scoped key short-circuits as NOT-CONFIGURED, not as failures.
    def mock_route_not_allowed(args, timeout_s=40, stdin_data=None):
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = GuardrailsRequestCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        guardrail_id=known_id, blocked_keyword="forbidden_keyword",
        curl_fn=mock_route_not_allowed,
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        "a route-scoped key must not read as gateway failures: "
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert scoped_suite["not_configured_checks"] == scoped_suite["total_checks"]
    # ...and that suite proved NOTHING, so it must never read as passing. Under
    # `all_passed = failed == 0` this was green: zero failures, zero proof, and a
    # CI gate reading `all_passed` waved it through as release evidence.
    assert scoped_suite["all_passed"] is False, (
        "an all-NOT-CONFIGURED suite proved nothing and must not report all_passed"
    )
    assert scoped_suite["proved_nothing"] is True, scoped_suite["passed_checks"]
    scope_details = [
        row.get("detail", "") for row in scoped_suite["checks"]
        if "key_route_not_allowed" in row.get("detail", "")
    ]
    assert scope_details, "no check reported the route-scope refusal"
    assert "NROUTER_HEALTH_ROUTE" in scope_details[0], (
        "the message must name the override to set"
    )

    assert "Per-Request Guardrails" in checker.render_markdown_summary(suite)
    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] guardrails_request_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Per-Request Guardrails Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)
    parser.add_argument("--guardrail-id", default=os.environ.get("NROUTER_GUARDRAIL_ID", ""))
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
        checker = GuardrailsRequestCurlHealthCheck(
            base_url=args.base_url,
            api_key=api_key,
            route=args.route,
            model=args.model,
            guardrail_id=args.guardrail_id,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Per-Request Guardrails Curl Health Check ===\n"
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
