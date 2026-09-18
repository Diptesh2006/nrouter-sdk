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
import sys
import time
import uuid
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
    header_float,
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
    served_body_ok,
    served_text,
    wire_contract_self_test,
)

FEATURE = "cache"
DEFAULT_MODEL = "openai/gpt-4o-mini"
CACHE_VALUES = {"hit", "miss", "bypass"}

# Outcomes of a priming call. A prime is a real request whose result the check
# that follows DEPENDS on, so it is asserted like any other: if the seed never
# landed, the check that reads it back proves nothing and must not pass.
PRIME_OK = "ok"
PRIME_ABSENT = "absent"  # the precondition is provably missing (caching is off)
PRIME_FAILED = "failed"  # the prime itself went wrong -> the check FAILS


class CacheCurlHealthCheck:
    """Health check runner for the tenant-isolated response cache."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        second_api_key: Optional[str] = None,
        guardrail_id: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.route = resolve_route(route)
        self.model = resolve_model(model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
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
        path = self.route
        self._current_path = path
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

    def _payload(self, suffix: str = "", **extra: Any) -> Dict[str, Any]:
        # `temperature` is a default a caller may deliberately override (the
        # altered-sampling check does exactly that), so it must not be passed
        # twice into the builder.
        fields: Dict[str, Any] = {"temperature": 0}
        fields.update(extra)
        # The OUTPUT CEILING is the same hazard one level down: it is passed
        # explicitly below AND could arrive in `**extra`, which raised
        # `TypeError: got multiple values for keyword argument` inside the
        # request builder — a crash in this script, not a gateway result. A
        # caller may name it either wire-neutrally (`max_tokens`) or by this
        # wire's own field, and their value wins over the default.
        ceiling_field = max_tokens_field(self.route)
        ceiling = fields.pop("max_tokens", None)
        if ceiling_field != "max_tokens":
            ceiling = fields.pop(ceiling_field, ceiling)
        return build_body(
            self.route,
            self.model,
            f"{self.salt}{suffix}",
            max_tokens=16 if ceiling is None else ceiling,
            **fields,
        )

    def _prime(
        self,
        suffix: str,
        expect_cache: Optional[str] = None,
        key: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Run a setup call and ASSERT it did what the check depends on.

        Returns (outcome, detail). A discarded priming call is how a check
        "passes" without ever having been set up: the seed 500s, the replay
        misses, and the miss is then read as "no cache on this plane". So every
        prime states its own verdict:

          PRIME_OK      the seed landed, with the cache state the check needs
          PRIME_ABSENT  caching is provably off here (bypass, or no header) ->
                        the caller reports NOT-CONFIGURED
          PRIME_FAILED  the seed itself went wrong -> the caller reports FAIL
        """
        args, _ = self._prepare(self._payload(suffix), key=key)
        status, headers, body, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")

        if status != 200:
            return PRIME_FAILED, f"priming call returned HTTP {status}, not 200"
        if served_text(self.route, body) is None:
            return PRIME_FAILED, "priming call returned no completion to cache"
        if state is None:
            return PRIME_ABSENT, "this plane emits no x-nr-response-cache header"
        if state == "bypass" and expect_cache != "bypass":
            return PRIME_ABSENT, (
                "the priming call reported x-nr-response-cache: bypass, so caching is "
                "switched off for this organization and there is nothing to read back"
            )
        if expect_cache is not None and state != expect_cache:
            return PRIME_FAILED, (
                f"priming call reported x-nr-response-cache {state!r}, expected "
                f"{expect_cache!r}"
            )
        return PRIME_OK, ""

    def _prime_seed_and_replay(self, suffix: str) -> Tuple[str, str]:
        """Prime an entry (miss) and confirm it reads back (hit)."""
        outcome, detail = self._prime(suffix, expect_cache="miss")
        if outcome != PRIME_OK:
            return outcome, detail
        return self._prime(suffix, expect_cache="hit")

    # ------------------------------------------------------------ happy checks

    def check_miss_then_hit(self) -> Dict[str, Any]:
        """The canonical proof: seed the entry, then read it back."""
        name = "miss_then_hit"
        assertion = (
            "both 200; first x-nr-response-cache == miss; second == hit; "
            "both bodies carry a completion at this wire's location; hit carries x-nr-response-cache-age when emitted"
        )
        first_args, _ = self._prepare(self._payload())
        first_status, first_headers, first_body, _ = self.curl_fn(first_args)
        second_args, request = self._prepare(self._payload())
        status, headers, body, _ = self.curl_fn(second_args)

        # NOT-CONFIGURED only when the capability is PROVABLY absent: both calls
        # were served correctly and neither carried the header at all. A call
        # that failed, or a body with no completion, is a FAIL below.
        both_served = (
            first_status == 200
            and status == 200
            and served_text(self.route, first_body) is not None
            and served_text(self.route, body) is not None
        )
        if (
            both_served
            and "x-nr-response-cache" not in first_headers
            and "x-nr-response-cache" not in headers
        ):
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    "both calls were served correctly but neither carried "
                    "x-nr-response-cache, so cache state is unobservable on this plane"
                ),
                not_configured=True,
            )
        if both_served and first_headers.get("x-nr-response-cache") == "bypass":
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    "the first call reported bypass: caching is switched off for this "
                    "organization, so there is no miss-then-hit to observe"
                ),
                not_configured=True,
            )
        age = headers.get("x-nr-response-cache-age")
        body_ok, body_detail = served_body_ok(self.route, body)
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
            (body_ok, f"replayed {body_detail}" if body_detail else ""),
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
        outcome, why = self._prime("-billing", expect_cache="miss")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, False,
                detail=f"the entry was never seeded, so hit billing could not be read: {why}",
            )
        args, request = self._prepare(self._payload("-billing"))
        status, headers, _, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")
        # A seeded entry that replays as `miss` is a REAL failure — the cache
        # did not retain what it just stored. Only `bypass` (the organization
        # opted out between the two calls) is an absent precondition.
        if state == "bypass":
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail="the replay reported bypass: caching is off for this organization",
                not_configured=True,
            )
        cost = header_float(headers, "x-nr-request-cost")
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (
                state == "hit",
                f"the replay of a freshly seeded entry reported {state!r}, not hit — "
                "the cache did not retain what it had just stored",
            ),
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
            "the wire's served body carries a completion"
        )
        # Seed the entry first, so `bypass` on the next call is demonstrably the
        # opt-out taking effect and not simply a cold cache.
        outcome, why = self._prime("-bypass", expect_cache="miss")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, True,
                detail=f"the entry was never seeded, so bypass proves nothing: {why}",
            )
        args, request = self._prepare(self._payload("-bypass", nrouter_cache=False))
        status, headers, body, _ = self.curl_fn(args)
        body_ok, body_detail = served_body_ok(self.route, body)
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
            (body_ok, body_detail),
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
        # The isolation claim is only meaningful once tenant A's entry PROVABLY
        # exists: seed it, then prove it reads back as a hit for A, and only
        # then ask B for the same body.
        outcome, why = self._prime_seed_and_replay("-tenant")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, True,
                detail=(
                    "tenant A's entry was never established, so a miss for tenant B "
                    f"would prove nothing about isolation: {why}"
                ),
            )
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
        outcome, why = self._prime_seed_and_replay("-sampling")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, True,
                detail=(
                    "the baseline entry was never established, so a miss on the altered "
                    f"body would prove nothing: {why}"
                ),
            )
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
        outcome, why = self._prime_seed_and_replay("-fingerprint")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, True,
                detail=(
                    "the entry admitted under the weaker chain was never established, "
                    f"so a miss with the addition would prove nothing: {why}"
                ),
            )
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
        outcome, why = self._prime("-routing", expect_cache="miss")
        if outcome == PRIME_ABSENT:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, True,
                detail=why, not_configured=True,
            )
        if outcome == PRIME_FAILED:
            return self._record(
                name, "(prime failed)", 0, {}, assertion, False, True,
                detail=f"the entry was never seeded, so no hit could be inspected: {why}",
            )
        args, request = self._prepare(self._payload("-routing"))
        status, headers, _, _ = self.curl_fn(args)
        state = headers.get("x-nr-response-cache")
        if state == "bypass":
            return self._record(
                name, request, status, headers, assertion, False, True,
                detail="the replay reported bypass: caching is off for this organization",
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (
                state == "hit",
                f"the replay of a freshly seeded entry reported {state!r}, not hit",
            ),
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
            "## 💾 nRouter Pure-Curl Health Check: Response Cache",
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
    print("Running cache_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

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
            served = (
                json.dumps({"content": [{"type": "text", "text": "cached answer"}]})
                if args[-1].endswith("/messages")
                else json.dumps({"choices": [{"message": {"content": "cached answer"}}]})
            )
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

    # BITE 3 — A MASKED MISS. A seeded entry that replays as `miss` is the cache
    # failing to retain what it stored. It must FAIL, never be excused as
    # "this plane is not configured for caching".
    def never_retains(args, timeout_s=45, stdin_data=None):
        base = {
            "x-nr-request-id": "dddddddd-0000-1111-2222-333333333333",
            "x-nr-guardrails": "pass",
            "x-nr-response-cache": "miss",
            "x-nr-request-cost": "0.000030",
            "x-nr-cost-status": "exact",
        }
        return 200, base, json.dumps({"choices": [{"message": {"content": "x"}}]}), 40.0

    forgetful = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=never_retains
    )
    forgetful_suite = forgetful.run_suite()
    billing_miss = next(
        r for r in forgetful_suite["checks"] if r["name"] == "hit_is_billed_never_zero"
    )
    assert billing_miss["result"] == FAIL, (
        "a seeded entry replaying as `miss` must FAIL, not report NOT-CONFIGURED; "
        f"got {billing_miss['result']}"
    )
    routing_miss = next(
        r for r in forgetful_suite["checks"] if r["name"] == "hit_carries_no_routing_headers"
    )
    assert routing_miss["result"] == FAIL, (
        f"a permanent miss must FAIL the hit-header check; got {routing_miss['result']}"
    )
    # ...while a genuine opt-out (bypass everywhere) IS an absent precondition.
    def always_bypass(args, timeout_s=45, stdin_data=None):
        base = {
            "x-nr-request-id": "eeeeeeee-0000-1111-2222-333333333333",
            "x-nr-guardrails": "pass",
            "x-nr-response-cache": "bypass",
            "x-nr-request-cost": "0.000030",
            "x-nr-cost-status": "exact",
        }
        return 200, base, json.dumps({"choices": [{"message": {"content": "x"}}]}), 40.0

    opted_out = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=always_bypass
    )
    opted_row = next(
        r for r in opted_out.run_suite()["checks"] if r["name"] == "hit_is_billed_never_zero"
    )
    assert opted_row["result"] == NOT_CONFIGURED, (
        f"an organization that opted out of caching IS an absent precondition; got {opted_row['result']}"
    )

    # BITE 4 — A DISCARDED PRIME. When the seeding call fails, every check that
    # reads it back must FAIL rather than quietly pass on the replay's shape.
    def prime_fails(args, timeout_s=45, stdin_data=None):
        body = payload_of(args)
        content = body.get("messages", [{}])[0].get("content", "")
        if content.endswith(("-billing", "-tenant", "-routing", "-sampling", "-fingerprint", "-bypass")):
            return 500, {"x-nr-request-id": "ffffffff-0000-1111-2222-333333333333"}, json.dumps(
                {"error": {"type": "gateway_error", "message": "upstream unavailable"}}
            ), 15.0
        return make_backend()(args, timeout_s, stdin_data)

    unprimed = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="k",
        second_api_key="key-b",
        guardrail_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        curl_fn=prime_fails,
    )
    unprimed_suite = unprimed.run_suite()
    for check_name in (
        "hit_is_billed_never_zero",
        "second_key_misses",
        "altered_sampling_param_misses",
        "guardrail_addition_misses",
        "hit_carries_no_routing_headers",
        "cache_false_bypasses",
    ):
        row = next(r for r in unprimed_suite["checks"] if r["name"] == check_name)
        assert row["result"] == FAIL, (
            f"{check_name} depends on a priming call that returned 500; it must FAIL, "
            f"got {row['result']}"
        )
        assert "never seeded" in row.get("detail", "") or "prove nothing" in row.get("detail", ""), (
            f"{check_name} does not say its prime failed: {row.get('detail')!r}"
        )

    # A transport failure can only FAIL; it is never an absent precondition.
    def transport_failure(args, timeout_s=45, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 11.0

    broken = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=transport_failure
    )
    broken_suite = broken.run_suite(quick=True)
    assert broken_suite["all_passed"] is False, "a transport failure must fail the suite"
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # BOTH WIRES: miss/hit/bypass are wire-independent, but the served-body
    # assertion is not — on /messages there are no `choices` to find.
    messages_checker = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key-a",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        second_api_key="sk-nrouter-mock-key-b",
        guardrail_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        curl_fn=make_backend(),
    )
    messages_suite = messages_checker.run_suite()
    assert messages_suite["route"] == "/messages"
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]
    assert "$NROUTER_BASE_URL/messages" in messages_suite["checks"][0]["request"]

    # A route-scoped key short-circuits as NOT-CONFIGURED, not as failures.
    def mock_route_not_allowed(args, timeout_s=45, stdin_data=None):
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = CacheCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_route_not_allowed
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert scoped_suite["not_configured_checks"] == scoped_suite["total_checks"]
    assert any(
        "NROUTER_HEALTH_ROUTE" in r.get("detail", "") for r in scoped_suite["checks"]
    ), "the scope refusal must name the override to set"

    assert "Response Cache" in checker.render_markdown_summary(suite)
    # ---- R5: `_payload` must not collide on the output-ceiling field --------
    # It passes `max_tokens=16` to the builder AND forwards `**extra`, so a
    # caller naming its own ceiling raised `TypeError: got multiple values for
    # keyword argument`. A check crashing inside its own request builder is not
    # a gateway result, and the caller's value is the one that was meant.
    for route, field in (
        ("/chat/completions", "max_tokens"),
        ("/messages", "max_tokens"),
        ("/responses", "max_output_tokens"),
        ("/completions", "max_tokens"),
    ):
        payload_checker = CacheCurlHealthCheck(
            base_url="https://mock.invalid/v1", api_key="k", route=route, model="m",
            curl_fn=lambda *a, **k: (200, {}, "{}", 1.0),
        )
        assert payload_checker._payload("-default")[field] == 16, route
        # named under the wire-neutral name...
        assert payload_checker._payload("-explicit", max_tokens=4)[field] == 4, route
        # ...and under this wire's own name.
        assert payload_checker._payload("-wire", **{field: 7})[field] == 7, route
        # The default temperature override is unaffected.
        assert payload_checker._payload("-t", temperature=0.8)["temperature"] == 0.8, route

    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] cache_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Response Cache Curl Health Check")
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
        checker = CacheCurlHealthCheck(
            base_url=args.base_url, api_key=api_key, route=args.route, model=args.model
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    print(
        f"=== nRouter Response Cache Curl Health Check ===\n"
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
