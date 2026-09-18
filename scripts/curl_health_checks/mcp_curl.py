#!/usr/bin/env python3
"""nRouter MCP Pure-Curl Health Check (`mcp_curl`).

`POST /mcp` speaks JSON-RPC 2.0 and is reached with the SAME customer virtual key
as inference — so the credential boundary is part of the contract, not an
afterthought.

⚠️ The MCP surface sits at the API **origin** (`/mcp`, and `/mcp/{server_id}` for
the path-addressed form), NOT under the inference base. `NROUTER_BASE_URL` names
the inference base and ends in `/v1`, so this module derives the origin from it
rather than joining `/mcp` onto it. Set `NROUTER_MCP_URL` to override outright.
A 404 from `<origin>/v1/mcp` is this module asking the wrong URL and says
nothing about the plane; a 404 from the real `/mcp` with a configured server
header means the plane names no such server, and reports NOT-CONFIGURED.

  Happy path
    1. `tools/list` with a configured server answers 200 with a JSON-RPC result.
    2. That answer is a well-formed envelope: `jsonrpc` 2.0, the id echoed back,
       plus the response-hygiene headers.

  Adversarial
    3. No credential at all answers 401.
    4. A control-plane-shaped key answers 401 — a management credential is never
       an inference credential.
    5. An unknown server name answers 404.
    6. A missing server header is refused, never silently defaulted.
    7. A body that is not JSON-RPC is refused 400 / JSON-RPC error.
    8. A refusal carries no cost header.
    9. A traversal-shaped server name is refused, never resolved.

When the plane configures no MCP server, the happy-path checks report
NOT-CONFIGURED. They never report PASS.

Usage:
  python3 scripts/curl_health_checks/mcp_curl.py --self-test
  python3 scripts/curl_health_checks/mcp_curl.py --quick
  python3 scripts/curl_health_checks/mcp_curl.py --step-summary
  python3 scripts/curl_health_checks/mcp_curl.py --json
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
    wire_contract_self_test,
)

FEATURE = "mcp"
MCP_PATH = "/mcp"

# The MCP surface lives at the API ORIGIN — `/mcp` and `/mcp/{server_id}` — NOT
# under the inference base. `NROUTER_BASE_URL` names the inference base and ends
# in `/v1`, so joining `/mcp` onto it asks `<origin>/v1/mcp`, which does not
# exist: every probe comes back 404 and the module reports its own bug nine
# times as a gateway result. Derive the origin instead, and let an operator whose
# MCP surface is somewhere else name it outright.
MCP_URL_ENV = "NROUTER_MCP_URL"
INFERENCE_PATH_SUFFIX = "/v1"


def mcp_url_for(base_url: str, explicit: str = "") -> str:
    """The MCP endpoint URL for an inference base URL.

    Strips one TRAILING `/v1` (case-insensitively, since a host may be written
    either way) and appends `/mcp`. A `/v1` in the middle of a path is part of
    that deployment's prefix and is left alone. `NROUTER_MCP_URL` wins outright.
    """
    override = (explicit or os.environ.get(MCP_URL_ENV, "")).strip()
    if override:
        return override.rstrip("/")
    origin = base_url.rstrip("/")
    if origin.lower().endswith(INFERENCE_PATH_SUFFIX):
        origin = origin[: -len(INFERENCE_PATH_SUFFIX)]
    return f"{origin.rstrip('/')}{MCP_PATH}"


def mcp_url_shell_form(explicit_override: bool) -> str:
    """How the reported curl command should SPELL that URL.

    A reported command is meant to be copy-pasteable, and this repository is
    public, so it must carry no host. The shell parameter expansion below IS the
    derivation above, so what a reader pastes is what the module asked.
    """
    if explicit_override:
        return f'"${MCP_URL_ENV}"'
    return '"${NROUTER_BASE_URL%/v1}/mcp"'


UNKNOWN_SERVER = "non-existent-server-xyz"
TRAVERSAL_SERVER = "../../api/providers"
# Shaped like a management credential, never issued to anyone. The real one, if
# the operator exports it, is read from the environment instead.
CONTROL_PLANE_SHAPED_KEY = "sk-nrouter-master-0000000000000000"

AUTH_REASON_VALUES = {
    "unauthorized",
    "key_blocked",
    "key_expired",
    "key_route_not_allowed",
    "key_ip_not_allowed",
    "key_network_policy_invalid",
    "auth_backend_unavailable",
}


class McpCurlHealthCheck:
    """Health check runner for the MCP JSON-RPC surface."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        server: Optional[str] = None,
        control_plane_key: Optional[str] = None,
        curl_fn: Callable = run_curl,
        mcp_url: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        # `/mcp` is at the API ORIGIN, not under the inference base's `/v1`.
        self.mcp_url = mcp_url_for(self.base_url, mcp_url)
        self._mcp_url_is_explicit = bool((mcp_url or os.environ.get(MCP_URL_ENV, "")).strip())
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        # The MCP surface has its own fixed path; the scope guard reports against
        # THAT, since a key scoped away from /mcp is the same absent precondition.
        self.route = MCP_PATH
        self.model = resolve_model("")
        self.scope_detail: Optional[str] = None
        self._current_path: Optional[str] = None
        self.server = server or os.environ.get("NROUTER_MCP_SERVER", "")
        self.control_plane_key = (
            control_plane_key
            or os.environ.get("NROUTER_CONTROL_PLANE_KEY", "")
            or CONTROL_PLANE_SHAPED_KEY
        )
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- plumbing

    def _prepare(
        self,
        body: Any,
        server: Optional[str] = None,
        key: Optional[str] = "",
        key_label: str = "$NROUTER_API_KEY",
        raw_body: Optional[str] = None,
    ) -> Tuple[List[str], str]:
        """`key=''` means the default customer key; `key=None` means send none."""
        self._current_path = MCP_PATH
        url = self.mcp_url
        payload = raw_body if raw_body is not None else json.dumps(body)
        args: List[str] = []
        shown = [f"curl -sS -D - -X POST {mcp_url_shell_form(self._mcp_url_is_explicit)}"]
        if key is not None:
            args += ["-H", f"Authorization: Bearer {key or self.api_key}"]
            shown.append(f'  -H "Authorization: Bearer {key_label}"')
        if server is not None:
            args += ["-H", f"x-nr-mcp-server: {server}"]
            shown.append(f'  -H "x-nr-mcp-server: {server}"')
        args += [
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
            "-X", "POST",
            "-d", payload,
            url,
        ]
        shown.append('  -H "Content-Type: application/json"')
        shown.append(f"  -d '{payload}'")
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

    @staticmethod
    def _tools_list(request_id: int = 1) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}

    # ------------------------------------------------------------ happy checks

    def check_tools_list_answers(self) -> Dict[str, Any]:
        name = "tools_list_answers"
        assertion = (
            "200; body.jsonrpc == 2.0; body.id echoes the request id; body.result.tools "
            "is an array; x-nr-request-id present; cache-control: no-store; "
            "x-content-type-options: nosniff"
        )
        if not self.server:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail="NROUTER_MCP_SERVER unset: this plane names no MCP server to reach",
                not_configured=True,
            )
        args, request = self._prepare(self._tools_list(1), server=self.server)
        status, headers, body, _ = self.curl_fn(args)
        if status in (404, 501):
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=(
                    f"the MCP surface answered {status} for server {self.server!r}; "
                    "no server is configured on this plane"
                ),
                not_configured=True,
            )
        parsed = parse_json(body)
        result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (parsed.get("jsonrpc") == "2.0", f"jsonrpc {parsed.get('jsonrpc')!r} != 2.0"),
            (parsed.get("id") == 1, f"id {parsed.get('id')!r} does not echo the request id"),
            (isinstance(result.get("tools"), list), "result.tools is not an array"),
            (bool(headers.get("x-nr-request-id")), "x-nr-request-id absent"),
            (
                "no-store" in headers.get("cache-control", ""),
                f"cache-control {headers.get('cache-control')!r} does not forbid storage",
            ),
            (
                headers.get("x-content-type-options") == "nosniff",
                f"x-content-type-options {headers.get('x-content-type-options')!r} != nosniff",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    def check_envelope_is_jsonrpc(self) -> Dict[str, Any]:
        name = "envelope_is_jsonrpc"
        assertion = (
            "200; the body is a JSON-RPC envelope carrying exactly one of result "
            "or error, never both; content-type is JSON"
        )
        if not self.server:
            return self._record(
                name, "(not executed)", 0, {}, assertion, False, False,
                detail="NROUTER_MCP_SERVER unset: no server to answer a JSON-RPC call",
                not_configured=True,
            )
        args, request = self._prepare(self._tools_list(7), server=self.server)
        status, headers, body, _ = self.curl_fn(args)
        if status in (404, 501):
            return self._record(
                name, request, status, headers, assertion, False, False,
                detail=f"the MCP surface answered {status}; no server configured",
                not_configured=True,
            )
        parsed = parse_json(body)
        has_result = "result" in parsed
        has_error = "error" in parsed
        ok, detail = assert_all([
            (status == 200, f"expected 200, got {status}"),
            (parsed.get("jsonrpc") == "2.0", "jsonrpc version missing or wrong"),
            (parsed.get("id") == 7, f"id {parsed.get('id')!r} does not echo the request id"),
            (has_result != has_error, "the envelope carries both result and error, or neither"),
            (
                "json" in headers.get("content-type", ""),
                f"content-type {headers.get('content-type')!r} is not JSON",
            ),
        ])
        return self._record(name, request, status, headers, assertion, ok, False, detail)

    # ------------------------------------------------------ adversarial checks

    def check_missing_credential_is_401(self) -> Dict[str, Any]:
        name = "missing_credential_is_401"
        assertion = (
            "401; error object present; x-nr-request-id present; no cost header; "
            "no tool list disclosed"
        )
        args, request = self._prepare(
            self._tools_list(), server=self.server or "example-server", key=None
        )
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 401, f"expected 401, got {status}"),
            (bool(error_of(body)) or bool(parse_json(body).get("error")), "no error object on a 401"),
            ("tools" not in body, "an unauthenticated caller was shown a tool list"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a 401"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_control_plane_key_is_401(self) -> Dict[str, Any]:
        name = "control_plane_key_is_401"
        assertion = (
            "401; a management-plane credential is refused on the customer MCP "
            "surface; x-nr-auth-reason present and in the spec enum; no tool list"
        )
        args, request = self._prepare(
            self._tools_list(),
            server=self.server or "example-server",
            key=self.control_plane_key,
            key_label="$NROUTER_CONTROL_PLANE_KEY",
        )
        status, headers, body, _ = self.curl_fn(args)
        reason = headers.get("x-nr-auth-reason")
        ok, detail = assert_all([
            (
                status == 401,
                f"expected 401, got {status} — a management credential reached the customer surface",
            ),
            (reason is None or reason in AUTH_REASON_VALUES, f"x-nr-auth-reason {reason!r} outside the spec enum"),
            ("tools" not in body, "a management credential was shown a tool list"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a 401"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_unknown_server_is_404(self) -> Dict[str, Any]:
        name = "unknown_server_is_404"
        assertion = (
            "404; an error object is returned; the body does NOT enumerate the "
            "servers that do exist; no cost header"
        )
        args, request = self._prepare(self._tools_list(), server=UNKNOWN_SERVER)
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status == 404, f"expected 404, got {status}"),
            (bool(parse_json(body).get("error")), "no error object on an unknown server"),
            ("tools" not in body, "an unknown server name returned a tool list"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_missing_server_header_is_refused(self) -> Dict[str, Any]:
        name = "missing_server_header_is_refused"
        assertion = (
            "400 or 404 (never 200); an omitted x-nr-mcp-server is refused, never "
            "defaulted to whichever server happens to be first; no cost header"
        )
        args, request = self._prepare(self._tools_list(), server=None)
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status != 200, "an omitted server header was silently defaulted and served"),
            (status in (400, 404), f"expected 400 or 404, got {status}"),
            (bool(parse_json(body).get("error")), "no error object on a refusal"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_non_jsonrpc_body_is_refused(self) -> Dict[str, Any]:
        name = "non_jsonrpc_body_is_refused"
        assertion = (
            "400, or 200 carrying a JSON-RPC error object; a body that is not "
            "JSON-RPC never reaches a tool; no cost header"
        )
        args, request = self._prepare(
            None,
            server=self.server or "example-server",
            raw_body=json.dumps({"not": "jsonrpc"}),
        )
        status, headers, body, _ = self.curl_fn(args)
        parsed = parse_json(body)
        ok, detail = assert_all([
            (status in (400, 200), f"expected 400 (or a 200 JSON-RPC error), got {status}"),
            (bool(parsed.get("error")), "no error object for a non-JSON-RPC body"),
            ("result" not in parsed, "a non-JSON-RPC body produced a result"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_refusal_carries_no_cost(self) -> Dict[str, Any]:
        name = "refusal_carries_no_cost"
        assertion = (
            "404; none of x-nr-request-cost, x-nr-cost-status, x-nr-input-tokens is "
            "present — an MCP refusal spends nothing"
        )
        args, request = self._prepare(self._tools_list(), server=UNKNOWN_SERVER)
        status, headers, _, _ = self.curl_fn(args)
        leaked = [
            header
            for header in ("x-nr-request-cost", "x-nr-cost-status", "x-nr-input-tokens")
            if header in headers
        ]
        ok, detail = assert_all([
            (status >= 400, f"expected a refusal, got {status}"),
            (not leaked, f"metering headers present on an MCP refusal: {leaked}"),
            (bool(headers.get("x-nr-request-id")), "x-nr-request-id absent on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    def check_traversal_server_name_is_refused(self) -> Dict[str, Any]:
        name = "traversal_server_name_is_refused"
        assertion = (
            "not 200; a traversal-shaped server name is refused, never resolved "
            "into another route; the body echoes no path"
        )
        args, request = self._prepare(self._tools_list(), server=TRAVERSAL_SERVER)
        status, headers, body, _ = self.curl_fn(args)
        ok, detail = assert_all([
            (status != 200, "a traversal-shaped server name resolved to something servable"),
            (status in (400, 404), f"expected 400 or 404, got {status}"),
            ("/api/providers" not in body, "the refusal echoed the traversal target back"),
            ("x-nr-request-cost" not in headers, "x-nr-request-cost present on a refusal"),
        ])
        return self._record(name, request, status, headers, assertion, ok, True, detail)

    # ----------------------------------------------------------------- driving

    def run_suite(self, quick: bool = False) -> Dict[str, Any]:
        self.results.clear()
        checks: List[Callable[[], Dict[str, Any]]] = [
            self.check_tools_list_answers,
            self.check_missing_credential_is_401,
            self.check_control_plane_key_is_401,
            self.check_unknown_server_is_404,
        ]
        if not quick:
            checks = [
                self.check_tools_list_answers,
                self.check_envelope_is_jsonrpc,
                self.check_missing_credential_is_401,
                self.check_control_plane_key_is_401,
                self.check_unknown_server_is_404,
                self.check_missing_server_header_is_refused,
                self.check_non_jsonrpc_body_is_refused,
                self.check_refusal_carries_no_cost,
                self.check_traversal_server_name_is_refused,
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
            "## 🔌 nRouter Pure-Curl Health Check: MCP",
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
    print("Running mcp_curl.py --self-test (offline mode)...")

    parser_contract_self_test()
    wire_contract_self_test()

    configured_server = "example-server"

    def header_of(args: List[str], name: str) -> Optional[str]:
        for index, arg in enumerate(args):
            if arg == "-H" and args[index + 1].lower().startswith(f"{name}:"):
                return args[index + 1].split(":", 1)[1].strip()
        return None

    def payload_of(args: List[str]) -> Dict[str, Any]:
        for index, arg in enumerate(args):
            if arg == "-d":
                try:
                    parsed = json.loads(args[index + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}

    hygiene = {
        "x-nr-request-id": "12341234-0000-1111-2222-333333333333",
        "content-type": "application/json",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
    }

    def mock_curl(args, timeout_s=40, stdin_data=None):
        auth = header_of(args, "authorization")
        server = header_of(args, "x-nr-mcp-server")
        body = payload_of(args)
        if auth is None:
            return 401, dict(hygiene), json.dumps(
                {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
            ), 3.0
        token = auth.split(" ", 1)[-1]
        if token.startswith(("sk-nrouter-master", "sk-admin-", "sk-master-")) or token == "control-plane":
            headers = dict(hygiene)
            headers["x-nr-auth-reason"] = "unauthorized"
            return 401, headers, json.dumps(
                {"error": {"type": "invalid_request_error", "message": "Unauthorized"}}
            ), 3.0
        if server is None:
            return 400, dict(hygiene), json.dumps(
                {"error": {"code": -32602, "message": "x-nr-mcp-server is required"}}
            ), 3.0
        if server != configured_server:
            return 404, dict(hygiene), json.dumps(
                {"error": {"code": -32601, "message": "unknown server"}}
            ), 3.0
        if body.get("jsonrpc") != "2.0" or "method" not in body:
            return 400, dict(hygiene), json.dumps(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
            ), 3.0
        return 200, dict(hygiene), json.dumps({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"tools": [{"name": "search", "description": "search the workspace"}]},
        }), 22.0

    checker = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1",
        api_key="sk-nrouter-mock-key",
        server=configured_server,
        control_plane_key="control-plane",
        curl_fn=mock_curl,
    )
    suite = checker.run_suite()
    assert suite["feature"] == FEATURE
    assert suite["total_checks"] == 9, suite["total_checks"]
    assert suite["adversarial_checks"] >= 7, suite["adversarial_checks"]
    assert suite["all_passed"] is True, [
        (r["name"], r.get("detail")) for r in suite["checks"] if r["result"] == FAIL
    ]
    for row in suite["checks"]:
        assert {"name", "request", "status", "headers", "assertion", "result", "expected_failure"} <= set(row)
        assert "sk-nrouter-mock-key" not in row["request"], "raw key leaked into report"

    # BITE 1: a control-plane key accepted on the customer surface must go red.
    def accepts_control_plane(args, timeout_s=40, stdin_data=None):
        auth = header_of(args, "authorization") or ""
        if auth.endswith("control-plane"):
            return 200, dict(hygiene), json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
            ), 20.0
        return mock_curl(args, timeout_s, stdin_data)

    permissive = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        control_plane_key="control-plane", curl_fn=accepts_control_plane,
    )
    cp_row = next(
        r for r in permissive.run_suite(quick=True)["checks"] if r["name"] == "control_plane_key_is_401"
    )
    assert cp_row["result"] == FAIL, "accepting a management credential must fail"

    # BITE 2: defaulting an omitted server header must go red.
    def defaults_server(args, timeout_s=40, stdin_data=None):
        if header_of(args, "x-nr-mcp-server") is None:
            args = args + ["-H", f"x-nr-mcp-server: {configured_server}"]
        return mock_curl(args, timeout_s, stdin_data)

    defaulting = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        control_plane_key="control-plane", curl_fn=defaults_server,
    )
    default_row = next(
        r for r in defaulting.run_suite()["checks"] if r["name"] == "missing_server_header_is_refused"
    )
    assert default_row["result"] == FAIL, "silently defaulting the server must fail"

    # BITE 3: an unauthenticated tool list must go red.
    def leaks_tools(args, timeout_s=40, stdin_data=None):
        if header_of(args, "authorization") is None:
            return 401, dict(hygiene), json.dumps(
                {"error": {"message": "Unauthorized", "tools": ["search"]}}
            ), 3.0
        return mock_curl(args, timeout_s, stdin_data)

    leaky = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        control_plane_key="control-plane", curl_fn=leaks_tools,
    )
    leak_row = next(
        r for r in leaky.run_suite(quick=True)["checks"] if r["name"] == "missing_credential_is_401"
    )
    assert leak_row["result"] == FAIL, "disclosing tools on a 401 must fail"

    # NOT-CONFIGURED, never PASS, when the plane has no MCP server.
    bare = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server="", curl_fn=mock_curl
    )
    bare_suite = bare.run_suite()
    bare_row = next(r for r in bare_suite["checks"] if r["name"] == "tools_list_answers")
    assert bare_row["result"] == NOT_CONFIGURED, bare_row["result"]
    assert bare_suite["partial"] is True

    # A plane that answers 404 for a named server is also NOT-CONFIGURED.
    def no_mcp(args, timeout_s=40, stdin_data=None):
        if header_of(args, "authorization") is None:
            return 401, dict(hygiene), json.dumps({"error": {"message": "Unauthorized"}}), 2.0
        return 404, dict(hygiene), json.dumps({"error": {"message": "not found"}}), 2.0

    absent = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server, curl_fn=no_mcp
    )
    absent_row = next(r for r in absent.run_suite()["checks"] if r["name"] == "tools_list_answers")
    assert absent_row["result"] == NOT_CONFIGURED, absent_row["result"]

    # A transport failure is NOT "no MCP server configured": the probe never
    # reached the plane, so nothing about it was established. It must FAIL.
    def transport_failure(args, timeout_s=40, stdin_data=None):
        return 0, {}, "curl exit code 56: Recv failure", 6.0

    broken = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        curl_fn=transport_failure,
    )
    broken_suite = broken.run_suite()
    broken_row = next(r for r in broken_suite["checks"] if r["name"] == "tools_list_answers")
    assert broken_row["result"] == FAIL, (
        f"a transport failure must FAIL, not look like an absent server; got {broken_row['result']}"
    )
    assert broken_suite["not_configured_checks"] == 0, (
        "a transport failure must never be reported as NOT-CONFIGURED"
    )

    # A key scoped away from /mcp is an absent precondition for THIS module, and
    # reports as NOT-CONFIGURED naming the header value — not as nine failures.
    def mock_route_not_allowed(args, timeout_s=40, stdin_data=None):
        return 403, {"x-nr-request-id": "r", "x-nr-auth-reason": "key_route_not_allowed"}, json.dumps(
            {"error": {"type": "invalid_request_error", "message": "Forbidden"}}
        ), 3.0

    scoped_suite = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        curl_fn=mock_route_not_allowed,
    ).run_suite()
    assert scoped_suite["failed_checks"] == 0, (
        f"{[r['name'] for r in scoped_suite['checks'] if r['result'] == FAIL]}"
    )
    scope_details = [
        r.get("detail", "") for r in scoped_suite["checks"]
        if "key_route_not_allowed" in r.get("detail", "")
    ]
    assert scope_details, "no check reported the route-scope refusal"
    assert "/mcp" in scope_details[0], (
        "the MCP module must name /mcp as the route it could not reach"
    )

    # ---------------------------------------------------------------- D9
    # THE MCP SURFACE IS AT THE API ORIGIN, NOT UNDER /v1.
    #
    # `NROUTER_BASE_URL` names the INFERENCE base and ends in `/v1`. Joining
    # `/mcp` onto it produced `<origin>/v1/mcp`, which does not exist, so every
    # MCP probe of 2026-09-17 came back 404 — the module's own bug reported nine
    # times as a gateway result. A 404 from `/v1/mcp` says nothing whatsoever
    # about the plane's MCP surface.
    assert mcp_url_for("https://mock.invalid/v1") == "https://mock.invalid/mcp", mcp_url_for("https://mock.invalid/v1")
    assert mcp_url_for("https://mock.invalid/v1/") == "https://mock.invalid/mcp"
    assert mcp_url_for("https://mock.invalid/V1") == "https://mock.invalid/mcp", (
        "the suffix match must not be case-sensitive"
    )
    # An origin that is already origin-only is left alone...
    assert mcp_url_for("https://mock.invalid") == "https://mock.invalid/mcp"
    # ...and only a TRAILING /v1 is stripped, never one in the middle of a path.
    assert mcp_url_for("https://mock.invalid/v1/gateway") == "https://mock.invalid/v1/gateway/mcp"

    saved_mcp_url = os.environ.pop(MCP_URL_ENV, None)
    try:
        os.environ[MCP_URL_ENV] = "https://mock.invalid/edge/mcp/"
        assert mcp_url_for("https://mock.invalid/v1") == "https://mock.invalid/edge/mcp", (
            f"{MCP_URL_ENV} must win over the derivation"
        )
    finally:
        os.environ.pop(MCP_URL_ENV, None)
        if saved_mcp_url is not None:
            os.environ[MCP_URL_ENV] = saved_mcp_url

    # ...and the checker ASKS that URL, which is the part a constant cannot fake.
    asked_urls: List[str] = []

    def record_url(args, timeout_s=40, stdin_data=None):
        asked_urls.append(args[-1])
        return mock_curl(args, timeout_s, stdin_data)

    url_checker = McpCurlHealthCheck(
        base_url="https://mock.invalid/v1", api_key="k", server=configured_server,
        curl_fn=record_url,
    )
    assert url_checker.mcp_url == "https://mock.invalid/mcp", url_checker.mcp_url
    url_checker.run_suite()
    assert asked_urls, "no MCP request was made at all"
    assert not any("/v1/mcp" in url for url in asked_urls), (
        f"a probe still asked the inference base's /v1/mcp, which does not exist: {asked_urls[:2]}"
    )
    assert all(url == "https://mock.invalid/mcp" for url in asked_urls), asked_urls[:3]
    # The reported command must be copy-pasteable and derive the same URL in
    # shell, rather than printing a host this public repository must not carry.
    shown = next(r["request"] for r in url_checker.results if r["request"] != "(not executed)")
    assert "NROUTER_BASE_URL%/v1" in shown or MCP_URL_ENV in shown, shown
    assert "mock.invalid" not in shown, "the reported command must not embed a host"

    assert "MCP" in checker.render_markdown_summary(suite)
    json_stdout_contract_self_test(suite, checker.render_markdown_summary(suite))
    print("[PASS] mcp_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter MCP Curl Health Check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""))
    add_wire_arguments(parser)  # accepted for symmetry; MCP has its own fixed path
    parser.add_argument("--server", default=os.environ.get("NROUTER_MCP_SERVER", ""))
    parser.add_argument(
        "--mcp-url",
        default="",
        help=(
            f"The MCP endpoint URL (env {MCP_URL_ENV}). Default: the API ORIGIN of "
            "--base-url with /mcp appended — /mcp does not live under the inference /v1."
        ),
    )
    parser.add_argument("--step-summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return EXIT_UNRUNNABLE

    checker = McpCurlHealthCheck(
        base_url=args.base_url, api_key=api_key, server=args.server, mcp_url=args.mcp_url
    )
    print(
        f"=== nRouter MCP Curl Health Check ===\n"
        f"Base URL: {args.base_url} | MCP URL: {checker.mcp_url} | route: {checker.route} | "
        f"server: {checker.server or '(none configured)'}",
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
