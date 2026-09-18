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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FEATURE = "guardrails_request"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_REQUEST_GUARDRAILS = 8
UNKNOWN_GUARDRAIL_ID = "00000000-0000-0000-0000-000000000000"
EXPLICIT_FLOOR_PROMPT = "sex porn"
BENIGN_PROMPT = "What is the capital of France?"

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

GUARDRAIL_HEADER_VALUES = {"none", "monitor", "pass", "partial", "blocked", "unavailable"}

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


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class GuardrailsRequestCurlHealthCheck:
    """Health check runner for the add-only `nrouter_guardrails` contract."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        guardrail_id: Optional[str] = None,
        blocked_keyword: Optional[str] = None,
        tenant_block_keyword: Optional[str] = None,
        foreign_guardrail_id: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.model = model
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

    def _payload(self, prompt: str, **extra: Any) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 16,
        }
        body.update(extra)
        return body

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
            "/chat/completions",
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
            "body.choices non-empty"
        )
        if not self.guardrail_id:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail="NROUTER_GUARDRAIL_ID unset: no addition to send",
                not_configured=True,
            )
        args, request = self._prepare(
            "/chat/completions",
            self._payload(BENIGN_PROMPT, nrouter_guardrails=[self.guardrail_id]),
        )
        status, headers, body, _ = self.curl_fn(args)
        posture = headers.get("x-nr-guardrails")
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (posture in GUARDRAIL_HEADER_VALUES, f"x-nr-guardrails {posture!r} outside the spec enum"),
            (posture != "blocked", "a benign prompt was blocked by an add-only guardrail"),
            (isinstance(choices, list) and len(choices) > 0, "body.choices missing or empty"),
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
            "/chat/completions",
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
            "/chat/completions",
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
            "/chat/completions",
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
            "/chat/completions",
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
            "/chat/completions", self._payload(BENIGN_PROMPT, nrouter_guardrails=[""])
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
        args, request = self._prepare("/chat/completions", self._payload(EXPLICIT_FLOOR_PROMPT))
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
            "/chat/completions",
            self._payload(EXPLICIT_FLOOR_PROMPT, nrouter_guardrails=additions),
        )
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        # An unknown id is refused before the floor scores, which proves nothing
        # about the floor: that is NOT-CONFIGURED, never PASS.
        if err.get("code") == "guardrail_not_found":
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail=(
                    "the addition was rejected as unknown before the floor ran; set "
                    "NROUTER_GUARDRAIL_ID to a real org guardrail to exercise this"
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
            "## 🛡️ nRouter Pure-Curl Health Check: Per-Request Guardrails",
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
    print("Running guardrails_request_curl.py --self-test (offline mode)...")

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

    assert "Per-Request Guardrails" in checker.render_markdown_summary(suite)
    print("[PASS] guardrails_request_curl.py self-test passed cleanly.")
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
    parser = argparse.ArgumentParser(description="nRouter Per-Request Guardrails Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--guardrail-id", default=os.environ.get("NROUTER_GUARDRAIL_ID", ""))
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health checks.", file=sys.stderr)
        return 1

    checker = GuardrailsRequestCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        model=args.model,
        guardrail_id=args.guardrail_id,
    )
    print("=== nRouter Per-Request Guardrails Curl Health Check ===")
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
