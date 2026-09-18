#!/usr/bin/env python3
"""nRouter Response Cache Pure-Curl Health Check (`cache_curl`).

The response cache is ON by default. It is tenant-isolated, it never serves a
stream, and a hit is BILLED — a $0 hit is a billing leak, not a saving.

  Happy path
    1. Two identical buffered requests: `miss` then `hit`.
    2. The hit carries `x-nr-request-cost` > 0 at `x-nr-cost-status: exact`.
    3. `x-nr-response-cache` only ever takes a value the spec lists.

  Adversarial
    4. `nrouter_cache: false` bypasses, and carries no cache-age header.
    5. A streamed call bypasses — never `hit`, never `miss`.
    6. A second key / organization reading the same body MISSES.
    7. An altered sampling parameter misses (the key covers the body).
    8. A non-boolean `nrouter_cache` refuses 400.
    9. Adding `nrouter_guardrails` changes the fingerprint and misses.
   10. A hit carries no routing headers (nothing was routed).

Usage:
  python3 scripts/curl_health_checks/cache_curl.py --self-test
  python3 scripts/curl_health_checks/cache_curl.py --quick
  python3 scripts/curl_health_checks/cache_curl.py --step-summary
  python3 scripts/curl_health_checks/cache_curl.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FEATURE = "cache"
DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
CACHE_VALUES = {"hit", "miss", "bypass"}

PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

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
    timeout_s: int = 45,
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


def header_float(headers: Dict[str, str], name: str) -> Optional[float]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


class CacheCurlHealthCheck:
    """Health check runner for the tenant-isolated response cache."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        second_api_key: Optional[str] = None,
        guardrail_id: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.model = model
        self.second_api_key = second_api_key or os.environ.get("NROUTER_API_KEY_B", "")
        self.guardrail_id = guardrail_id or os.environ.get("NROUTER_GUARDRAIL_ID", "")
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []
        # One salt per run keeps a rerun from hitting the previous run's entry.
        self.salt = f"cache-probe-{uuid.uuid4().hex[:12]}"

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self, body: Any, key: Optional[str] = None, key_label: str = "$NROUTER_API_KEY"
    ) -> Tuple[List[str], str]:
        path = "/chat/completions"
        url = f"{self.base_url}{path}"
        payload = json.dumps(body)
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

    def _payload(self, suffix: str = "", **extra: Any) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": f"{self.salt}{suffix}"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        body.update(extra)
        return body

    # ------------------------------------------------------------ happy checks

    def check_miss_then_hit(self) -> Dict[str, Any]:
        """The canonical proof: seed the entry, then read it back."""
        name = "miss_then_hit"
        assertion = (
            "both 200; first x-nr-response-cache == miss; second == hit; "
            "both bodies carry choices; hit carries x-nr-response-cache-age when emitted"
        )
        first_args, _ = self._prepare(self._payload())
        first_status, first_headers, _, _ = self.curl_fn(first_args)
        second_args, request = self._prepare(self._payload())
        status, headers, body, _ = self.curl_fn(second_args)

        if "x-nr-response-cache" not in first_headers and "x-nr-response-cache" not in headers:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="x-nr-response-cache is not emitted on this plane; cache state is unprovable",
                not_configured=True,
            )
        age = headers.get("x-nr-response-cache-age")
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (first_status == 200, f"seed request expected 200, got {first_status}"),
            (status == 200, f"replay request expected 200, got {status}"),
            (
                first_headers.get("x-nr-response-cache") == "miss",
                f"seed x-nr-response-cache {first_headers.get('x-nr-response-cache')!r} != miss",
            ),
            (
                headers.get("x-nr-response-cache") == "hit",
                f"replay x-nr-response-cache {headers.get('x-nr-response-cache')!r} != hit",
            ),
            (isinstance(choices, list) and len(choices) > 0, "replayed body carries no choices"),
            (
                age is None or (age.isdigit() and int(age) >= 0),
                f"x-nr-response-cache-age {age!r} is not a non-negative integer",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_hit_is_billed_never_zero(self) -> Dict[str, Any]:
        """A hit is charged at the cache-read rate — never $0, never unpriced."""
        name = "hit_is_billed_never_zero"
        assertion = (
            "200; x-nr-response-cache == hit; x-nr-request-cost present and "
            "strictly > 0; x-nr-cost-status == exact"
        )
        self.curl_fn(self._prepare(self._payload("-billing"))[0])
        args, request = self._prepare(self._payload("-billing"))
        status, headers, _, _ = self.curl_fn(args)
        if headers.get("x-nr-response-cache") != "hit":
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    f"the replay reported {headers.get('x-nr-response-cache')!r}, not a hit, "
                    "so hit billing was never exercised"
                ),
                not_configured=True,
            )
        cost = header_float(headers, "x-nr-request-cost")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            ("x-nr-request-cost" in headers, "x-nr-request-cost absent on a cache hit"),
            (cost is not None and cost > 0.0, f"cache hit billed {headers.get('x-nr-request-cost')!r} (must be > 0)"),
            (
                headers.get("x-nr-cost-status") == "exact",
                f"x-nr-cost-status {headers.get('x-nr-cost-status')!r} != exact on a billed hit",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_cache_header_value_in_spec_enum(self) -> Dict[str, Any]:
        name = "cache_header_value_in_spec_enum"
        assertion = "200; x-nr-response-cache value is one of hit|miss|bypass"
        args, request = self._prepare(self._payload("-enum"))
        status, headers, _, _ = self.curl_fn(args)
        value = headers.get("x-nr-response-cache")
        if value is None:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="x-nr-response-cache absent; the enum cannot be checked",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (value in CACHE_VALUES, f"x-nr-response-cache {value!r} outside {sorted(CACHE_VALUES)}"),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def check_cache_false_bypasses(self) -> Dict[str, Any]:
        name = "cache_false_bypasses"
        assertion = (
            "200; x-nr-response-cache == bypass; x-nr-response-cache-age ABSENT; "
            "body carries choices"
        )
        self.curl_fn(self._prepare(self._payload("-bypass"))[0])
        args, request = self._prepare(self._payload("-bypass", nrouter_cache=False))
        status, headers, body, _ = self.curl_fn(args)
        choices = parse_json(body).get("choices")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (
                headers.get("x-nr-response-cache") == "bypass",
                f"x-nr-response-cache {headers.get('x-nr-response-cache')!r} != bypass",
            ),
            (
                "x-nr-response-cache-age" not in headers,
                "x-nr-response-cache-age present on a bypass (it replayed an entry)",
            ),
            (isinstance(choices, list) and len(choices) > 0, "body carries no choices"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_stream_bypasses(self) -> Dict[str, Any]:
        name = "stream_bypasses"
        assertion = (
            "200; content-type is text/event-stream; x-nr-response-cache == bypass "
            "(never hit or miss); no cache-age header"
        )
        args, request = self._prepare(self._payload("-stream", stream=True))
        status, headers, _, _ = self.curl_fn(args)
        cache_state = headers.get("x-nr-response-cache")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (
                "text/event-stream" in headers.get("content-type", ""),
                f"content-type {headers.get('content-type')!r} is not an SSE stream",
            ),
            (cache_state == "bypass", f"x-nr-response-cache {cache_state!r} != bypass on a stream"),
            ("x-nr-response-cache-age" not in headers, "a stream reported a cache age"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_second_key_misses(self) -> Dict[str, Any]:
        """Tenant isolation: another key must never read this entry."""
        name = "second_key_misses"
        assertion = (
            "200; x-nr-response-cache == miss for the second key on a body the "
            "first key already cached (never hit); no cache-age header"
        )
        if not self.second_api_key:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail="NROUTER_API_KEY_B unset: no second tenant to prove isolation against",
                not_configured=True,
            )
        self.curl_fn(self._prepare(self._payload("-tenant"))[0])
        self.curl_fn(self._prepare(self._payload("-tenant"))[0])
        args, request = self._prepare(
            self._payload("-tenant"), key=self.second_api_key, key_label="$NROUTER_API_KEY_B"
        )
        status, headers, _, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (state != "hit", "CROSS-TENANT CACHE READ: a second key was served another tenant's entry"),
            (state == "miss", f"x-nr-response-cache {state!r} != miss"),
            ("x-nr-response-cache-age" not in headers, "a cross-tenant request reported a cache age"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_altered_sampling_param_misses(self) -> Dict[str, Any]:
        name = "altered_sampling_param_misses"
        assertion = (
            "200; changing temperature on an otherwise identical body yields "
            "x-nr-response-cache == miss (the key covers the whole body)"
        )
        self.curl_fn(self._prepare(self._payload("-sampling"))[0])
        self.curl_fn(self._prepare(self._payload("-sampling"))[0])
        args, request = self._prepare(self._payload("-sampling", temperature=0.8))
        status, headers, _, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (state != "hit", "a different temperature replayed a cached completion"),
            (state == "miss", f"x-nr-response-cache {state!r} != miss"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_invalid_cache_type_400(self) -> Dict[str, Any]:
        name = "invalid_cache_type_400"
        assertion = (
            '400; error.type present; a string "false" is refused, never coerced '
            "to a boolean; no cost header"
        )
        args, request = self._prepare(self._payload("-typed", nrouter_cache="false"))
        status, headers, body, _ = self.curl_fn(args)
        err = error_of(body)
        ok, detail = assert_all([
            (status == 400, f"expected 400, got {status}"),
            (bool(err.get("type")), "error.type absent"),
            (bool(str(err.get("message", "")).strip()), "error.message empty"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_guardrail_addition_misses(self) -> Dict[str, Any]:
        name = "guardrail_addition_misses"
        assertion = (
            "200; adding nrouter_guardrails to a cached body changes the guardrail "
            "fingerprint and yields miss, never a hit admitted under a weaker chain"
        )
        if not self.guardrail_id:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail="NROUTER_GUARDRAIL_ID unset: no addition available to alter the fingerprint",
                not_configured=True,
            )
        self.curl_fn(self._prepare(self._payload("-fingerprint"))[0])
        self.curl_fn(self._prepare(self._payload("-fingerprint"))[0])
        args, request = self._prepare(
            self._payload("-fingerprint", nrouter_guardrails=[self.guardrail_id])
        )
        status, headers, _, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (state != "hit", "CACHE BLEED: an entry admitted under a weaker guardrail chain was replayed"),
            (state == "miss", f"x-nr-response-cache {state!r} != miss"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_hit_carries_no_routing_headers(self) -> Dict[str, Any]:
        name = "hit_carries_no_routing_headers"
        assertion = (
            "200; on x-nr-response-cache == hit neither x-nr-routing nor "
            "x-nr-attempts is present (nothing was routed)"
        )
        self.curl_fn(self._prepare(self._payload("-routing"))[0])
        args, request = self._prepare(self._payload("-routing"))
        status, headers, _, _ = self.curl_fn(args)
        if headers.get("x-nr-response-cache") != "hit":
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail=f"the replay reported {headers.get('x-nr-response-cache')!r}, not a hit",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            ("x-nr-routing" not in headers, "x-nr-routing present on a cache hit"),
            ("x-nr-attempts" not in headers, "x-nr-attempts present on a cache hit"),
            (bool(headers.get("x-nr-guardrails")), "a served hit carries no x-nr-guardrails token"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_miss_then_hit,
            self.check_cache_false_bypasses,
            self.check_stream_bypasses,
            self.check_invalid_cache_type_400,
        ]
        if not quick:
            checks = [
                self.check_miss_then_hit,
                self.check_hit_is_billed_never_zero,
                self.check_cache_header_value_in_spec_enum,
                self.check_cache_false_bypasses,
                self.check_stream_bypasses,
                self.check_second_key_misses,
                self.check_altered_sampling_param_misses,
                self.check_invalid_cache_type_400,
                self.check_guardrail_addition_misses,
                self.check_hit_carries_no_routing_headers,
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
            "## 💾 nRouter Pure-Curl Health Check: Response Cache",
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
    print("Running cache_curl.py --self-test (offline mode)...")

    def payload_of(args: List[str]) -> Dict[str, Any]:
        for index, arg in enumerate(args):
            if arg == "-d":
                try:
                    parsed = json.loads(args[index + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}

    def auth_of(args: List[str]) -> str:
        for index, arg in enumerate(args):
            if arg == "-H" and args[index + 1].lower().startswith("authorization:"):
                return args[index + 1].split(" ", 2)[-1]
        return ""

    def make_backend() -> Callable:
        store: Dict[Tuple[str, str], int] = {}

        def mock_curl(args, timeout_s=45, stdin_data=None):
            body = payload_of(args)
            key = auth_of(args)
            base = {"x-nr-request-id": "aaaaaaaa-0000-1111-2222-333333333333", "x-nr-model": DEFAULT_MODEL}
            if not isinstance(body.get("nrouter_cache", True), bool):
                return 400, dict(base), json.dumps(
                    {"error": {"type": "invalid_request_error", "message": "nrouter_cache must be a boolean"}}
                ), 3.0
            served = json.dumps({"choices": [{"message": {"content": "cached answer"}}]})
            if body.get("stream"):
                headers = dict(base)
                headers.update({
                    "content-type": "text/event-stream",
                    "x-nr-response-cache": "bypass",
                    "x-nr-guardrails": "pass",
                    "x-nr-request-cost": "0.000030",
                    "x-nr-cost-status": "exact",
                })
                return 200, headers, "data: [DONE]\n", 50.0
            if body.get("nrouter_cache") is False:
                headers = dict(base)
                headers.update({
                    "x-nr-response-cache": "bypass",
                    "x-nr-guardrails": "pass",
                    "x-nr-request-cost": "0.000030",
                    "x-nr-cost-status": "exact",
                })
                return 200, headers, served, 48.0
            fingerprint = json.dumps(
                {k: v for k, v in sorted(body.items()) if k != "nrouter_cache"}, sort_keys=True
            )
            entry = (key, fingerprint)
            headers = dict(base)
            headers["x-nr-guardrails"] = "pass"
            headers["x-nr-cost-status"] = "exact"
            if entry in store:
                store[entry] += 1
                headers.update({
                    "x-nr-response-cache": "hit",
                    "x-nr-response-cache-age": "4",
                    "x-nr-request-cost": "0.000003",
                })
                return 200, headers, served, 6.0
            store[entry] = 1
            headers.update({
                "x-nr-response-cache": "miss",
                "x-nr-routing": "direct",
                "x-nr-attempts": "1",
                "x-nr-request-cost": "0.000030",
            })
            return 200, headers, served, 47.0

        return mock_curl

    checker = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key-a",
        second_api_key="sk-nrouter-mock-key-b",
        guardrail_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        curl_fn=make_backend(),
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

    # BITE 1: a $0 hit is a billing leak and must go red.
    def zero_cost_backend() -> Callable:
        inner = make_backend()

        def mock(args, timeout_s=45, stdin_data=None):
            status, headers, body, latency = inner(args, timeout_s, stdin_data)
            if headers.get("x-nr-response-cache") == "hit":
                headers = dict(headers)
                headers["x-nr-request-cost"] = "0.000000"
            return status, headers, body, latency

        return mock

    zero = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=zero_cost_backend()
    )
    zero_suite = zero.run_suite()
    billing_row = next(r for r in zero_suite["checks"] if r["name"] == "hit_is_billed_never_zero")
    assert billing_row["result"] == FAIL, "a $0 cache hit must fail"

    # BITE 2: a cross-tenant hit must go red.
    def leaky_backend() -> Callable:
        store: Dict[str, bool] = {}

        def mock(args, timeout_s=45, stdin_data=None):
            body = payload_of(args)
            fingerprint = json.dumps(body, sort_keys=True)
            base = {"x-nr-request-id": "bbbbbbbb-0000-1111-2222-333333333333", "x-nr-guardrails": "pass"}
            if fingerprint in store:
                base.update({
                    "x-nr-response-cache": "hit",
                    "x-nr-request-cost": "0.000003",
                    "x-nr-cost-status": "exact",
                })
                return 200, base, json.dumps({"choices": [{"message": {"content": "x"}}]}), 5.0
            store[fingerprint] = True
            base.update({
                "x-nr-response-cache": "miss",
                "x-nr-request-cost": "0.000030",
                "x-nr-cost-status": "exact",
            })
            return 200, base, json.dumps({"choices": [{"message": {"content": "x"}}]}), 40.0

        return mock

    leaky = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="key-a",
        second_api_key="key-b",
        curl_fn=leaky_backend(),
    )
    leaky_suite = leaky.run_suite()
    tenant_row = next(r for r in leaky_suite["checks"] if r["name"] == "second_key_misses")
    assert tenant_row["result"] == FAIL, "a cross-tenant cache read must fail"
    assert "CROSS-TENANT" in tenant_row.get("detail", ""), tenant_row.get("detail")

    # NOT-CONFIGURED when the plane emits no cache header at all.
    def headerless(args, timeout_s=45, stdin_data=None):
        return 200, {"x-nr-request-id": "cccccccc-0000-1111-2222-333333333333"}, json.dumps(
            {"choices": [{"message": {"content": "x"}}]}
        ), 30.0

    silent = CacheCurlHealthCheck(base_url="https://mock.invalid/v1", api_key="k", curl_fn=headerless)
    silent_row = silent.run_suite(quick=True)["checks"][0]
    assert silent_row["result"] == NOT_CONFIGURED, silent_row["result"]

    assert "Response Cache" in checker.render_markdown_summary(suite)
    print("[PASS] cache_curl.py self-test passed cleanly.")
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
    parser = argparse.ArgumentParser(description="nRouter Response Cache Curl Health Check")
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

    checker = CacheCurlHealthCheck(base_url=args.base_url, api_key=api_key, model=args.model)
    print("=== nRouter Response Cache Curl Health Check ===")
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
