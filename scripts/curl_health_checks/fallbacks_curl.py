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
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# The shared plumbing sits beside this file: ONE curl invocation, ONE response
# parser, ONE credential rule (`NROUTER_API_KEY` only — `_curl_common` explains
# why a public repository must not carry a credentials-file fallback).
# `run_curl` and `sanitize` are re-exported so this module keeps the shape every
# check module has.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import (  # noqa: E402
    DEFAULT_BASE_URL,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_UNRUNNABLE,
    FAIL,
    MISSING_KEY_MESSAGE,
    MODEL_ENV,
    NOT_CONFIGURED,
    PASS,
    add_wire_arguments,
    assert_all,
    auth_denial_note,
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

FEATURE = "fallbacks"
# There is deliberately NO `DEFAULT_PRIMARY_MODEL`. The primary IS the model
# under test (`NROUTER_HEALTH_MODEL` / `--model`); a second constant naming the
# same thing was never read, and a name that looks like configuration while
# changing nothing is a second place for the two to drift apart.
# These two are only a GUESS at a secondary this key can route to. A virtual key
# is commonly scoped to a handful of models, and a target outside that scope is
# refused 400 `fallback_not_allowed` — which is the gateway being RIGHT. So the
# healthy secondary is an override (`NROUTER_HEALTH_FALLBACK_MODEL`), and when it
# is unset and the default is refused for exactly that reason, the happy-path
# checks report NOT-CONFIGURED rather than blaming the gateway for correctness.
DEFAULT_FALLBACK_MODEL = "anthropic/claude-3-5-haiku"
DEFAULT_SECOND_FALLBACK_MODEL = "google/gemini-2.5-flash"
FALLBACK_MODEL_ENV = "NROUTER_HEALTH_FALLBACK_MODEL"
SECOND_FALLBACK_MODEL_ENV = "NROUTER_HEALTH_SECOND_FALLBACK_MODEL"
FALLBACK_NOT_ALLOWED = "fallback_not_allowed"
# Deliberately unroutable on every plane: the refused-target check needs a name
# no catalogue can serve, so its 400 is about the POLICY and not about which
# models this particular key happens to hold.
UNPERMITTED_TARGET = "private/unauthorized-enterprise-model"
AUTO_MODEL = "nrouter/auto"
MAX_FALLBACK_TARGETS = 4

ROUTING_RE = re.compile(r"^(direct|fallback:[0-9]+)$")


class FallbacksCurlHealthCheck:
    """Health check runner for the `nrouter_fallbacks` request contract."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        route: str = "",
        model: str = "",
        primary_model: str = "",
        fallback_model: str = "",
        second_fallback_model: str = "",
        failing_primary_model: Optional[str] = None,
        healthy_fallback_model: Optional[str] = None,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        # The route and model under test are a runtime choice: a virtual key is
        # commonly scoped to a subset of both.
        self.route = resolve_route(route)
        # `--primary-model` is a DEPRECATED alias for `--model`: they name the
        # same thing (the model the chain starts from), so an explicit `--model`
        # wins and the alias fills in behind it. Keeping them as two independent
        # values is how a run ends up asking about a model nobody chose.
        self.model = resolve_model(model or primary_model)
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.primary_model = self.model
        # A run with no model at all would post `"model": ""` on every probe and
        # read the gateway's complaint about THAT as a fallback finding. It is
        # an absent precondition, decided here, before anything is sent.
        self.unrunnable_detail: Optional[str] = None
        if not self.model.strip():
            self.unrunnable_detail = (
                f"no model under test: {MODEL_ENV} is unset or blank and no --model/--primary-model "
                "was given, so every probe would ask the gateway about an empty model name and "
                f"report its complaint as a fallback finding. Set {MODEL_ENV}=<a model this key "
                "may use>."
            )
        # A healthy SECONDARY is plane data, exactly like the route and the
        # primary model: this key may not be allowed to route the default. Track
        # whether each was actually named, because that is what tells a refusal
        # of the guess apart from a refusal of a configured target.
        configured_fallback = fallback_model or os.environ.get(FALLBACK_MODEL_ENV, "")
        configured_second = second_fallback_model or os.environ.get(
            SECOND_FALLBACK_MODEL_ENV, ""
        )
        self.fallback_model = configured_fallback or DEFAULT_FALLBACK_MODEL
        self.second_fallback_model = configured_second or DEFAULT_SECOND_FALLBACK_MODEL
        self.fallback_target_configured = {
            FALLBACK_MODEL_ENV: bool(configured_fallback),
            SECOND_FALLBACK_MODEL_ENV: bool(configured_second),
        }
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
        self._current_path = path
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
        # A 403 naming key_route_not_allowed means the request never reached the
        # behaviour under test, so it is NOT-CONFIGURED whatever the check wanted.
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

    def _body_payload(self, model: str, **extra: Any) -> Dict[str, Any]:
        return build_body(self.route, model, "ping", max_tokens=8, **extra)

    def _unconfigured_target_detail(
        self, status: int, body: str, needed: Tuple[str, ...]
    ) -> Optional[str]:
        """The NOT-CONFIGURED explanation for a refused GUESS, or None.

        Same shape as the route-scope short-circuit and just as narrow. A key is
        scoped to a set of models; a fallback target outside it is refused 400
        `fallback_not_allowed`, and that refusal is the gateway being CORRECT.
        Reporting it as a happy-path FAIL blames the gateway for a right answer
        and buries the one actionable fact — that nobody named a secondary this
        key can route to.

        Three narrowings, each pinned by the self-test:
          * it applies only while the variable is UNSET. A target someone
            explicitly named and the gateway refused is a REAL failure.
          * only status 400, and
          * only `error.code == fallback_not_allowed`. Any other code (an
            oversize request, a bad shape) is a real failure.

        Unlike the route guard this does NOT short-circuit the module: a target
        the key cannot route says nothing about the refusal checks, which are
        still meaningful and still run.
        """
        unset = [name for name in needed if not self.fallback_target_configured[name]]
        if not unset:
            return None
        if status != 400 or error_of(body).get("code") != FALLBACK_NOT_ALLOWED:
            return None
        current = {
            FALLBACK_MODEL_ENV: self.fallback_model,
            SECOND_FALLBACK_MODEL_ENV: self.second_fallback_model,
        }
        return (
            f"the gateway refused this chain 400 {FALLBACK_NOT_ALLOWED} — the CORRECT "
            "answer for a target this key may not route to, so nothing about the "
            "fallback walk was tested. Name a secondary the key allows: "
            + " ".join(f"{name}=<a model the key allows>" for name in unset)
            + " (currently the built-in guess: "
            + ", ".join(f"{name}={current[name]}" for name in unset)
            + ")"
        )

    # ------------------------------------------------------------ happy checks

    def check_direct_serve_with_fallback_list(self) -> Dict[str, Any]:
        """A served request names the answering rank in its routing headers."""
        name = "direct_serve_with_fallback_list"
        assertion = (
            "200; the wire's served body carries a completion; x-nr-routing matches ^(direct|fallback:N)$ "
            "and x-nr-attempts is an integer >= 1"
        )
        args, request = self._prepare(
            "POST",
            self.route,
            self._body_payload(
                self.primary_model, nrouter_fallbacks=[self.fallback_model]
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        unconfigured = self._unconfigured_target_detail(
            status, body, (FALLBACK_MODEL_ENV,)
        )
        if unconfigured:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=unconfigured, not_configured=True,
            )
        routing = headers.get("x-nr-routing")
        attempts = headers.get("x-nr-attempts")
        body_ok, body_detail = served_body_ok(self.route, body)
        # NOT-CONFIGURED only when the PRECONDITION is provably absent: the
        # request was served correctly and the plane emits NEITHER routing
        # header (they are planned, not released). A served response that is
        # itself broken, or one that emits one header and not the other, is a
        # FAIL and falls through to the assertions below.
        if (
            status == 200
            and body_ok
            and routing is None
            and attempts is None
        ):
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    "served correctly, but this plane emits neither x-nr-routing nor "
                    "x-nr-attempts, so the rank that answered is unprovable here"
                ),
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (body_ok, body_detail),
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
            "200; the wire's served body carries a completion; x-nr-routing == fallback:1; "
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
            self.route,
            self._body_payload(
                self.failing_primary_model,
                nrouter_fallbacks=[self.healthy_fallback_model],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        routing = headers.get("x-nr-routing")
        attempts = headers.get("x-nr-attempts")
        body_ok, body_detail = served_body_ok(self.route, body)
        if (
            status == 200
            and body_ok
            and routing is None
            and attempts is None
        ):
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    "the failover was served correctly, but this plane emits no routing "
                    "headers, so the answering rank is unprovable here"
                ),
                not_configured=True,
            )
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (body_ok, body_detail),
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
            self.route,
            self._body_payload(
                self.primary_model,
                nrouter_fallbacks=[self.fallback_model, self.second_fallback_model],
            ),
        )
        status, headers, body, _ = self.curl_fn(args)
        unconfigured = self._unconfigured_target_detail(
            status, body, (FALLBACK_MODEL_ENV, SECOND_FALLBACK_MODEL_ENV)
        )
        if unconfigured:
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=unconfigured, not_configured=True,
            )
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
        expect_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared adversarial shape: a refusal with a code, no cost, no rank."""
        args, request = self._prepare(
            "POST", self.route, payload, raw_body=raw_body
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
        if expect_type:
            conditions.append(
                (
                    err.get("type") == expect_type,
                    f"error.type {err.get('type')!r} != {expect_type!r}",
                )
            )
        if expect_code:
            conditions.append(
                (code == expect_code, f"error.code {code!r} != {expect_code!r}")
            )
        # An authentication/authorization denial is never the refusal under test,
        # and WHICH one it was is the evidence. Recorded as its own clause so the
        # transcript names the status and whether the gateway said why.
        auth_note = auth_denial_note(status, headers, expect_status)
        if auth_note:
            conditions.append((False, auth_note))
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
        """The primary listed as its own fallback is refused.

        ⚠️ THIS REFUSAL CARRIES NO MACHINE `code` TODAY — a known contract gap.
        The gateway raises it as an invalid-request-JSON refusal, which publishes
        `type: gateway_error` and omits `code` entirely (only the refusals the
        published spec can name, such as `fallback_not_allowed`, carry one). So
        the wording is the only handle a caller has, and the only handle this
        check has. Two consequences, both deliberate:

          * the message pattern is WIDE (`repeat` is the gateway's own word
            today, and the others cover the phrasings a rewrite would reach for),
            because a prose assertion that tracks one sentence is a false gate;
          * the SHAPE is what is really asserted — 400, `type: gateway_error`,
            no `x-nr-request-cost`, no `x-nr-routing` / `x-nr-attempts`. Those
            survive any rewording, and the money and rank clauses are the ones
            that matter.

        If the gateway ever names this refusal, pin the code here and the prose
        stops being load-bearing. Absence of `code` is NOT asserted: doing so
        would turn that improvement into a red test.
        """
        return self._refusal_check(
            "self_reference_400",
            "400; error.type == gateway_error; message forbids repeating the requested "
            "model as its own fallback (no machine code exists for this refusal today); "
            "no x-nr-request-cost; no routing headers",
            self._body_payload(
                self.primary_model, nrouter_fallbacks=[self.primary_model]
            ),
            expect_code=None,
            expect_type="gateway_error",
            message_must_match=r"(repeat|itself|self|primary|same)",
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
            self.route,
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

    def _checks_for(self, quick: bool) -> List[Callable[[], Dict[str, Any]]]:
        """The check list for this lane — ONE definition, so nothing drifts."""
        if quick:
            return [
                self.check_direct_serve_with_fallback_list,
                self.check_unpermitted_target_is_400,
                self.check_self_reference_400,
                self.check_auto_refuses_fallbacks,
            ]
        return [
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

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks = self._checks_for(quick)
        if self.unrunnable_detail:
            # Recorded per check, never silently skipped: a suite that could not
            # run must SAY so on every row it did not make, and the run is
            # PARTIAL rather than a clean green with nothing behind it.
            for check in checks:
                name = check.__name__
                if name.startswith("check_"):
                    name = name[len("check_"):]
                self._record(
                    name, "(not executed)", 0, {},
                    "(skipped: no model under test)",
                    False, False, detail=self.unrunnable_detail, not_configured=True,
                )
            return self.summarize()
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
            "## 🔀 nRouter Pure-Curl Health Check: Request Fallbacks",
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
    """Offline validation of every parser and assertion in this module."""
    print("Running fallbacks_curl.py --self-test (offline mode)...")

    # The shared transport contract: an SSE body survives intact, and a curl
    # rc 56 with a partial body on stdout is a transport failure, not a 200.
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

    def refusal(code: Optional[str], message: str) -> str:
        # `gateway_error` is the literal the gateway publishes as `type` for every
        # refusal on this path — the fixture matches the wire, or the assertions
        # are pinned to a shape no gateway ever sends.
        error: Dict[str, Any] = {"type": "gateway_error", "message": message}
        if code:
            error["code"] = code
        return json.dumps({"error": error})

    base_headers = {"x-nr-request-id": "11111111-2222-3333-4444-555555555555"}

    def served(args: List[str], text: str = "pong") -> str:
        """A served body in the shape of the wire the request was made on."""
        endpoint = args[-1]
        if endpoint.endswith("/messages"):
            return json.dumps({"content": [{"type": "text", "text": text}], "role": "assistant"})
        if endpoint.endswith("/responses"):
            return json.dumps({"output": [{"content": [{"type": "output_text", "text": text}]}]})
        if endpoint.endswith("/completions") and not endpoint.endswith("/chat/completions"):
            return json.dumps({"choices": [{"text": text}]})
        return json.dumps({"choices": [{"message": {"content": text}}]})

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
                return 200, headers, served(args, "ok"), 40.0
        headers = dict(base_headers)
        headers.update({
            "x-nr-routing": "direct",
            "x-nr-attempts": "1",
            "x-nr-model": str(model),
            "x-nr-request-cost": "0.000042",
            "x-nr-cost-status": "exact",
        })
        return 200, headers, served(args), 38.0

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

    # ...but NOT-CONFIGURED must not become a hiding place. A response that is
    # served WITHOUT routing headers AND without a usable body is a FAIL: the
    # precondition claim ("this plane does not emit them") is only honest when
    # the request itself was answered correctly.
    def mock_no_routing_and_empty_body(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_no_routing_headers(args, timeout_s, stdin_data)
        if status == 200:
            body = json.dumps({"choices": [], "content": []})  # served, but empty on every wire
        return status, headers, body, latency

    masked = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_no_routing_and_empty_body
    )
    masked_row = masked.run_suite(quick=True)["checks"][0]
    assert masked_row["result"] == FAIL, (
        "an empty completion must FAIL even when the routing headers are absent; "
        f"got {masked_row['result']}"
    )

    # A transport failure (status 0) can only ever FAIL a check, never pass one
    # and never be mistaken for an absent precondition.
    def mock_transport_failure(args, timeout_s=40, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 12.0

    broken = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_transport_failure
    )
    broken_suite = broken.run_suite(quick=True)
    assert broken_suite["all_passed"] is False, "a transport failure must fail the suite"
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # BOTH WIRES. The same suite must pass against the Anthropic-shaped wire,
    # where a served completion lives at content[0].text and there are no
    # `choices` at all — a chat-shaped assertion would fail a good response.
    messages_checker = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        failing_primary_model="vendor/down-primary",
        healthy_fallback_model="vendor/healthy-secondary",
        curl_fn=mock_curl,
    )
    messages_suite = messages_checker.run_suite()
    assert messages_suite["route"] == "/messages", messages_suite["route"]
    assert messages_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in messages_suite["checks"] if r["result"] == FAIL
    ]
    # The request really was built for that wire, and never carries chat fields.
    messages_request = messages_suite["checks"][0]["request"]
    assert "$NROUTER_BASE_URL/messages" in messages_request, messages_request
    assert '"max_tokens"' in messages_request, "max_tokens is required on the messages wire"

    # ...and a chat-shaped body must NOT satisfy the messages wire, or the
    # per-wire assertion is decorative.
    def mock_always_chat_shaped(args, timeout_s=40, stdin_data=None):
        status, headers, body, latency = mock_curl(args, timeout_s, stdin_data)
        if status == 200:
            body = json.dumps({"choices": [{"message": {"content": "pong"}}]})
        return status, headers, body, latency

    mismatched = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/messages",
        model="claude-haiku-4-5-20251001", curl_fn=mock_always_chat_shaped,
    )
    mismatched_row = mismatched.run_suite(quick=True)["checks"][0]
    assert mismatched_row["result"] == FAIL, (
        "a chat-shaped body on the messages wire must FAIL; got "
        f"{mismatched_row['result']}"
    )
    assert "content[0].text" in mismatched_row.get("detail", ""), mismatched_row.get("detail")

    # A route-scoped key short-circuits the module as NOT-CONFIGURED, rather
    # than reporting ten gateway failures that never happened.
    def mock_route_not_allowed(args, timeout_s=40, stdin_data=None):
        return 403, {
            "x-nr-request-id": "22222222-3333-4444-5555-666666666666",
            "x-nr-auth-reason": "key_route_not_allowed",
        }, refusal(None, "Forbidden"), 4.0

    scoped = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/chat/completions",
        curl_fn=mock_route_not_allowed,
    )
    scoped_suite = scoped.run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        "a route-scoped key must not read as gateway failures: "
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    assert scoped_suite["not_configured_checks"] == scoped_suite["total_checks"], (
        "every check should be NOT-CONFIGURED once the route is refused"
    )
    assert "key_route_not_allowed" in scoped_suite["checks"][0]["detail"]
    assert "NROUTER_HEALTH_ROUTE" in scoped_suite["checks"][0]["detail"], (
        "the message must name the override to set"
    )
    # Short-circuited: the guard stops after the first refusal rather than
    # firing every remaining request at a route the key cannot use.
    assert "(not executed)" in scoped_suite["checks"][-1]["request"], (
        "the suite kept running after the route refusal"
    )
    # ...and that suite proved NOTHING, so it must never read as passing. Under
    # `all_passed = failed == 0` this was green: zero failures, zero proof, and a
    # CI gate reading `all_passed` waved it through as release evidence.
    assert scoped_suite["all_passed"] is False, (
        "an all-NOT-CONFIGURED suite proved nothing and must not report all_passed"
    )
    assert scoped_suite["proved_nothing"] is True, scoped_suite["passed_checks"]

    # A 403 for a DIFFERENT reason is a real failure, not a scope refusal.
    def mock_key_blocked(args, timeout_s=40, stdin_data=None):
        return 403, {
            "x-nr-request-id": "33333333-4444-5555-6666-777777777777",
            "x-nr-auth-reason": "key_blocked",
        }, refusal(None, "Forbidden"), 4.0

    blocked = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_key_blocked
    )
    blocked_suite = blocked.run_suite(quick=True)
    assert blocked_suite["all_passed"] is False, (
        "a blocked key is a failure, not an absent precondition"
    )
    assert blocked_suite["not_configured_checks"] == 0, blocked_suite

    # ------------------------------------------------------------------ D1 --
    # A key scoped to two models cannot route the DEFAULT secondary, and the
    # gateway refuses it 400 `fallback_not_allowed`. That is the gateway being
    # CORRECT, so the happy-path checks must report NOT-CONFIGURED and name the
    # variable that would fix it — never FAIL the gateway for a right answer.
    routable = {
        "vendor/allowed-secondary",
        "vendor/allowed-tertiary",
        "vendor/healthy-secondary",
        "vendor/down-secondary",
    }

    def mock_only_scoped_targets_route(args, timeout_s=40, stdin_data=None):
        """Every rule of `mock_curl`, plus this key's narrow model scope."""
        body = payload_of(args)
        model, targets = body.get("model"), body.get("nrouter_fallbacks")
        if (
            isinstance(targets, list)
            and model not in targets                       # not a self-reference
            and UNPERMITTED_TARGET not in targets          # not the policy probe
            and len(targets) <= MAX_FALLBACK_TARGETS       # not the ceiling probe
            and any(target not in routable for target in targets)
        ):
            return 400, dict(base_headers), refusal(
                FALLBACK_NOT_ALLOWED, "fallback model is not available to this key"
            ), 6.0
        return mock_curl(args, timeout_s, stdin_data)

    unrouted = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        curl_fn=mock_only_scoped_targets_route,
    )
    unrouted_rows = {r["name"]: r for r in unrouted.run_suite()["checks"]}
    for check_name, needed in (
        ("direct_serve_with_fallback_list", FALLBACK_MODEL_ENV),
        ("request_list_is_walked_in_order", SECOND_FALLBACK_MODEL_ENV),
    ):
        row = unrouted_rows[check_name]
        assert row["result"] == NOT_CONFIGURED, (
            f"{check_name}: a refused DEFAULT fallback target is an absent "
            f"precondition, not a gateway failure; got {row['result']} "
            f"({row.get('detail')})"
        )
        assert needed in row.get("detail", ""), (
            f"{check_name}: NOT-CONFIGURED must name the variable to set; "
            f"got {row.get('detail')!r}"
        )
    assert unrouted.run_suite()["failed_checks"] == 0, "the gateway answered correctly throughout"

    # ...and once the variable NAMES a target this key can route, the same
    # checks assert for real again, with no other edit.
    configured = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        fallback_model="vendor/allowed-secondary",
        second_fallback_model="vendor/allowed-tertiary",
        curl_fn=mock_only_scoped_targets_route,
    )
    configured_suite = configured.run_suite()
    assert configured_suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in configured_suite["checks"] if r["result"] == FAIL
    ]
    configured_rows = {r["name"]: r for r in configured_suite["checks"]}
    for check_name in ("direct_serve_with_fallback_list", "request_list_is_walked_in_order"):
        assert configured_rows[check_name]["result"] == PASS, (
            f"{check_name} must assert for real once a routable secondary is named; "
            f"got {configured_rows[check_name]}"
        )
    # ...and the OTHER half, which is the one that makes the flag load-bearing:
    # a target somebody NAMED and the gateway still refused is a REAL failure.
    # The operator asserted this key can route it; the gateway disagreed, and
    # that disagreement is a finding, not an absent precondition. Without this
    # case the "configured" flag can be deleted and every test still passes —
    # measured: ignoring the flag entirely left the suite green until this case
    # existed, because a configured target is otherwise SERVED and never reaches
    # the 400 branch at all.
    def mock_refuses_every_target(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        if isinstance(body.get("nrouter_fallbacks"), list):
            return 400, dict(base_headers), refusal(
                FALLBACK_NOT_ALLOWED, "fallback model is not available to this key"
            ), 6.0
        return mock_curl(args, timeout_s, stdin_data)

    named_but_refused = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k",
        fallback_model="vendor/allowed-secondary",
        second_fallback_model="vendor/allowed-tertiary",
        curl_fn=mock_refuses_every_target,
    )
    named_row = {
        r["name"]: r for r in named_but_refused.run_suite(quick=True)["checks"]
    }["direct_serve_with_fallback_list"]
    assert named_row["result"] == FAIL, (
        f"a {FALLBACK_NOT_ALLOWED} refusal of an EXPLICITLY NAMED target is a real "
        f"failure, not an absent precondition; got {named_row['result']} "
        f"({named_row.get('detail')})"
    )

    # The override is honoured from the environment too, not only the flag.
    #
    # R11: the cleanup is in a `finally`. With the pops written after the
    # assertions, a FAILING assertion here skipped them and left both variables
    # set for every later section — so the next failure would be reported
    # against a configuration this block silently installed, and the real cause
    # would be two hundred lines upstream.
    os.environ[FALLBACK_MODEL_ENV] = "vendor/allowed-secondary"
    os.environ[SECOND_FALLBACK_MODEL_ENV] = "vendor/allowed-tertiary"
    try:
        from_env = FallbacksCurlHealthCheck(
            base_url="https://mock.invalid/v1", api_key="k",
            curl_fn=mock_only_scoped_targets_route,
        )
        from_env_rows = {r["name"]: r for r in from_env.run_suite()["checks"]}
        assert from_env_rows["direct_serve_with_fallback_list"]["result"] == PASS, (
            f"{FALLBACK_MODEL_ENV} must be read from the environment, not only the flag; "
            f"got {from_env_rows['direct_serve_with_fallback_list']}"
        )
        assert from_env_rows["request_list_is_walked_in_order"]["result"] == PASS, (
            f"{SECOND_FALLBACK_MODEL_ENV} must be read from the environment"
        )
    finally:
        os.environ.pop(FALLBACK_MODEL_ENV, None)
        os.environ.pop(SECOND_FALLBACK_MODEL_ENV, None)

    # THE NARROWING, both halves. NOT-CONFIGURED is reserved for a 400 that
    # names `fallback_not_allowed`: a 400 with any OTHER code, and any other
    # status, remain real failures.
    def mock_other_400_code(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        model, targets = body.get("model"), body.get("nrouter_fallbacks")
        if (
            isinstance(targets, list)
            and model not in targets
            and UNPERMITTED_TARGET not in targets
            and len(targets) <= MAX_FALLBACK_TARGETS
        ):
            return 400, dict(base_headers), refusal("input_too_large", "request too large"), 6.0
        return mock_curl(args, timeout_s, stdin_data)

    other_code = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_other_400_code
    )
    # R12: looked up BY NAME, like every other assertion here. `["checks"][0]`
    # silently follows whatever the quick lane happens to run first, so
    # reordering `_checks_for` would move this assertion onto a different check
    # and it would keep passing — asserting about something nobody chose.
    other_row = {
        r["name"]: r for r in other_code.run_suite(quick=True)["checks"]
    }["direct_serve_with_fallback_list"]
    assert other_row["result"] == FAIL, (
        "a 400 carrying a code other than fallback_not_allowed is a real failure; "
        f"got {other_row['result']} ({other_row.get('detail')})"
    )

    def mock_503(args, timeout_s=40, stdin_data=None):
        return 503, dict(base_headers), refusal(None, "upstream unavailable"), 9.0

    unavailable = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_503
    )
    unavailable_suite = unavailable.run_suite(quick=True)
    assert unavailable_suite["failed_checks"] == unavailable_suite["total_checks"], (
        "a 503 is never an absent precondition"
    )
    assert unavailable_suite["not_configured_checks"] == 0, unavailable_suite

    # ------------------------------------------------------------------ D2 --
    # The gateway's REAL self-reference refusal: 400, type `gateway_error`, the
    # word `repeat`, and — today — no machine `code` at all.
    def mock_real_self_reference(args, timeout_s=40, stdin_data=None):
        body = payload_of(args)
        targets = body.get("nrouter_fallbacks")
        if isinstance(targets, list) and body.get("model") in targets:
            return 400, dict(base_headers), json.dumps({"error": {
                "type": "gateway_error",
                "message": (
                    "invalid request json: nrouter_fallbacks must not repeat "
                    "the requested model"
                ),
            }}), 6.0
        return mock_curl(args, timeout_s, stdin_data)

    real_refusal = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", curl_fn=mock_real_self_reference
    )
    real_row = {
        r["name"]: r for r in real_refusal.run_suite(quick=True)["checks"]
    }["self_reference_400"]
    assert real_row["result"] == PASS, (
        "the gateway's real self-reference wording must PASS: "
        f"{real_row.get('detail')}"
    )

    # ...and the SHAPE is what is really being asserted, so each facet bites.
    def _self_reference_variant(mutate):
        def mocked(args, timeout_s=40, stdin_data=None):
            status, headers, body, latency = mock_real_self_reference(
                args, timeout_s, stdin_data
            )
            targets = payload_of(args).get("nrouter_fallbacks")
            if isinstance(targets, list) and payload_of(args).get("model") in targets:
                status, headers, body = mutate(status, dict(headers), body)
            return status, headers, body, latency

        checker_ = FallbacksCurlHealthCheck(
            base_url="https://mock.invalid/v1", api_key="k", curl_fn=mocked
        )
        return {
            r["name"]: r for r in checker_.run_suite(quick=True)["checks"]
        }["self_reference_400"]

    wrong_type = _self_reference_variant(
        lambda status, headers, body: (
            status,
            headers,
            json.dumps({"error": {"type": "invalid_request_error", "message": (
                "invalid request json: nrouter_fallbacks must not repeat the requested model"
            )}}),
        )
    )
    assert wrong_type["result"] == FAIL and "gateway_error" in wrong_type["detail"], (
        f"error.type must be asserted, not assumed: {wrong_type}"
    )

    billed = _self_reference_variant(
        lambda status, headers, body: (
            status, {**headers, "x-nr-request-cost": "0.000004"}, body
        )
    )
    assert billed["result"] == FAIL and "cost" in billed["detail"], (
        f"a billed refusal must go red: {billed}"
    )

    ranked = _self_reference_variant(
        lambda status, headers, body: (
            status, {**headers, "x-nr-attempts": "1"}, body
        )
    )
    assert ranked["result"] == FAIL and "routing" in ranked["detail"], (
        f"a refusal must not advertise a routing rank: {ranked}"
    )

    served_200 = _self_reference_variant(
        lambda status, headers, body: (200, headers, served([""]))
    )
    assert served_200["result"] == FAIL, (
        "a self-referencing chain that is SERVED must go red, not pass on prose"
    )

    # ---- R7: no dead constant, and no run with no model at all -------------
    # `DEFAULT_PRIMARY_MODEL` was never read: the primary IS the model under
    # test, and a second name for it is a second place to drift. A name that
    # looks like configuration but changes nothing is worse than no name.
    assert not hasattr(sys.modules[__name__], "DEFAULT_PRIMARY_MODEL"), (
        "DEFAULT_PRIMARY_MODEL is dead — the primary is the model under test"
    )
    # `--primary-model` stays as a DEPRECATED alias, because a caller may have
    # it in a script, and it must resolve to the same thing as `--model`.
    aliased = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/chat/completions",
        primary_model="vendor/aliased", curl_fn=lambda *a, **k: (200, {}, "{}", 1.0),
    )
    assert aliased.primary_model == "vendor/aliased", aliased.primary_model
    assert aliased.model == "vendor/aliased", (
        "--primary-model must alias the model under test, not shadow it"
    )
    # ...and an explicit --model still wins over the deprecated alias.
    both = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/chat/completions",
        model="vendor/explicit", primary_model="vendor/aliased",
        curl_fn=lambda *a, **k: (200, {}, "{}", 1.0),
    )
    assert both.model == "vendor/explicit" and both.primary_model == "vendor/explicit", (
        (both.model, both.primary_model)
    )

    # An EMPTY model is refused at a local precondition guard, before any
    # request is sent. Every probe would otherwise post `"model": ""` and read
    # the gateway's complaint about it as a fallback finding.
    empty_model_calls: List[Any] = []

    def must_not_be_called(*args, **kwargs):
        empty_model_calls.append(args)
        return 200, {}, "{}", 1.0

    blank = FallbacksCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", route="/chat/completions",
        model=" ", curl_fn=must_not_be_called,
    )
    blank_suite = blank.run_suite()
    assert blank_suite["failed_checks"] == 0, (
        "no model is an absent precondition, not a pile of gateway failures"
    )
    assert blank_suite["not_configured_checks"] == blank_suite["total_checks"], blank_suite
    assert not empty_model_calls, (
        f"a request was sent with no model at all: {empty_model_calls[:1]}"
    )
    assert any(
        "NROUTER_HEALTH_MODEL" in r.get("detail", "") for r in blank_suite["checks"]
    ), "the refusal must NAME the variable to set"

    markdown = checker.render_markdown_summary(suite)
    assert "Request Fallbacks" in markdown, "markdown summary lost its title"

    # --json must leave EXACTLY one JSON document on stdout.
    json_stdout_contract_self_test(suite, markdown)
    os.environ.pop("NROUTER_FAILING_PRIMARY_MODEL", None)
    os.environ.pop("NROUTER_FAILING_FALLBACK_MODEL", None)
    print("[PASS] fallbacks_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Request Fallbacks Curl Health Check")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    parser.add_argument("--quick", action="store_true", help="Run the four-check quick lane")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)
    # Empty by default on purpose: the constructor must be able to tell "nobody
    # named a secondary" from "someone named this one", because only the first
    # makes a `fallback_not_allowed` refusal an absent precondition.
    parser.add_argument(
        "--primary-model",
        default="",
        help=f"DEPRECATED alias for --model (env {MODEL_ENV}); --model wins",
    )
    parser.add_argument(
        "--fallback-model",
        default="",
        help=f"A healthy secondary this key can route to (env {FALLBACK_MODEL_ENV})",
    )
    parser.add_argument(
        "--second-fallback-model",
        default="",
        help=f"An optional third target for the ordered walk (env {SECOND_FALLBACK_MODEL_ENV})",
    )
    parser.add_argument("--step-summary", action="store_true", help="Append markdown to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Emit the JSON report on stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return EXIT_UNRUNNABLE

    try:
        checker = FallbacksCurlHealthCheck(
            base_url=args.base_url,
            api_key=api_key,
            route=args.route,
            model=args.model,
            primary_model=args.primary_model,
            fallback_model=args.fallback_model,
            second_fallback_model=args.second_fallback_model,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNRUNNABLE
    # With --json this banner goes to stderr, so stdout carries only the report.
    print(
        f"=== nRouter Request Fallbacks Curl Health Check ===\n"
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
