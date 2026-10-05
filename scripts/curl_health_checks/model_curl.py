#!/usr/bin/env python3
"""nRouter Model & Provider Pure-Curl Health Check (`model_curl`).

Consolidated health check verifying:
  1. Models Catalog (GET /v1/models):
     - Endpoint HTTP 200 OK
     - Catalog response SHAPE: at least one entry, every `id` a non-empty string
     - The count is REPORTED, not judged. A virtual key scoped to two models
       legitimately lists two, so there is no built-in floor; set
       `NROUTER_HEALTH_MIN_MODELS` to assert one for a plane you know.
  2. Provider Discovery & Coverage:
     - Extraction and grouping of active model providers
     - Model distribution across providers
  3. Live Model / Provider Inference Probe (POST the ROUTE UNDER TEST):
     - The route and model are a RUNTIME choice — `NROUTER_HEALTH_ROUTE` /
       `--route` and `NROUTER_HEALTH_MODEL` / `--model` (`--probe-model` is the
       historical alias). A module that hardcodes `/chat/completions` against a
       key scoped to `/messages` tests the KEY POLICY, not the gateway.
     - The body is built in that wire's shape and the completion is read where
       that wire puts it (`choices[0].message.content` vs `content[0].text`).
     - A 403 naming `key_route_not_allowed` is NOT-CONFIGURED, never a defect;
       any other 403, and any other status, is a real finding.

Usage:
  python3 scripts/curl_health_checks/model_curl.py --self-test
  python3 scripts/curl_health_checks/model_curl.py
  python3 scripts/curl_health_checks/model_curl.py --route /messages --model claude-...
  python3 scripts/curl_health_checks/model_curl.py --step-summary
  python3 scripts/curl_health_checks/model_curl.py --json
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

# This module keeps its own transport and its own report shape. What it borrows
# is the directory's shared CONTRACTS: `--json` puts exactly one JSON document
# on stdout, the route and model under test come from one pair of names, each
# wire builds the body it accepts and reads the body it returns, and a 403 that
# names `key_route_not_allowed` is an absent precondition rather than a defect.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import (  # noqa: E402
    ALLOWED_ROUTES,
    MODEL_ENV,
    ROUTE_ENV,
    build_body,
    fixed_route_scope_detail,
    main_json_stdout_contract_self_test,
    resolve_model,
    resolve_route,
    served_body_ok,
    served_location,
    served_text,
    suite_verdict,
    wire_of,
)

DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"

# Evaluated at import, exactly as an argparse `default=os.environ.get(...)` is:
# `run_all.py` passes `probe_model=model_curl.DEFAULT_PROBE_MODEL` as its own
# flag default, so a constant here would silently override the operator's
# NROUTER_HEALTH_MODEL on every consolidated run.
DEFAULT_PROBE_MODEL = resolve_model()

# The catalog size is a PLANE FACT, not a contract. A virtual key scoped to two
# models legitimately lists two, so a built-in floor of ten reported a correct
# gateway as broken. A floor now exists only when an operator asks for one.
MIN_MODELS_ENV = "NROUTER_HEALTH_MIN_MODELS"


def resolve_min_models() -> Optional[int]:
    """The operator's minimum catalog size, or None when they set none.

    Returns None for unset, empty, or unparseable — an unreadable value must not
    invent a threshold, and must not silently become zero either.
    """
    raw = os.environ.get(MIN_MODELS_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None

# Regex patterns for sanitizing credentials from output / logs
SECRET_PATTERNS = [
    re.compile(r"sk-nrouter-[A-Za-z0-9_-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]


def sanitize(text: str) -> str:
    """Redact sensitive tokens and auth headers."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def run_curl(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
    """Execute raw curl command and parse status, headers, body, and latency."""
    cmd = ["curl", "-sS", "-D", "-"] + args
    start_time = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
        latency_ms = round((time.monotonic() - start_time) * 1000.0, 1)
        raw_output = proc.stdout
    except subprocess.TimeoutExpired:
        return 0, {}, "Request timed out", round((time.monotonic() - start_time) * 1000.0, 1)
    except Exception as exc:
        return 0, {}, f"Subprocess error: {exc}", 0.0

    if proc.returncode != 0 and not raw_output:
        return 0, {}, f"curl exit code {proc.returncode}: {proc.stderr.strip()}", latency_ms

    parts = raw_output.split("\r\n\r\n")
    if len(parts) == 1:
        parts = raw_output.split("\n\n")

    header_block = ""
    body = ""
    for part in parts[:-1]:
        if part.startswith("HTTP/") or "\nHTTP/" in part or "\r\nHTTP/" in part:
            header_block = part
    body = parts[-1] if parts else ""

    headers: Dict[str, str] = {}
    status_code = 0

    for line in header_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("HTTP/"):
            match = re.match(r"^HTTP/[0-9.]+\s+(\d+)", line)
            if match:
                status_code = int(match.group(1))
        elif ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return status_code, headers, body, latency_ms


def extract_provider(model_id: str) -> str:
    """Derive provider name or prefix from model identifier."""
    if "/" in model_id:
        return model_id.split("/")[0].lower()
    # Normalize common prefix-based models (e.g., claude-*, gpt-*, gemini-*, llama-*)
    prefix = model_id.split("-")[0].lower()
    mapping = {
        "claude": "anthropic",
        "gpt": "openai",
        "o1": "openai",
        "o3": "openai",
        "o4": "openai",
        "gemini": "google",
        "llama": "meta",
        "mistral": "mistral",
        "deepseek": "deepseek",
        "qwen": "qwen",
        "qwq": "qwen",
        "phi": "microsoft",
        "grok": "xai",
    }
    return mapping.get(prefix, prefix)


class ModelCurlHealthCheck:
    """Health check runner for nRouter models and providers."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        probe_model: str = "",
        curl_fn: Callable = run_curl,
        route: str = "",
        model: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        # The route and model under test. `--probe-model` is this module's
        # historical name for the model; `--model` / NROUTER_HEALTH_MODEL is the
        # directory-wide one. They name the same thing, so the explicit one wins
        # and the pair resolves through the shared helpers — a module that
        # hardcodes the route tests the KEY POLICY, not the gateway.
        self.route = resolve_route(route)
        self.model = resolve_model(model or probe_model)
        # Kept as an alias because the report and `run_all.py` both read it.
        self.probe_model = self.model
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    def _auth_headers(self) -> List[str]:
        headers = [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
        ]
        # The Anthropic-shaped wire requires its version header; without it the
        # gateway answers 400 about the header rather than about the probe.
        if wire_of(self.route) == "messages":
            headers.extend(["-H", "anthropic-version: 2023-06-01"])
        return headers

    def check_models_catalog(self) -> Dict[str, Any]:
        """Verify GET /v1/models catalog endpoint and provider distribution."""
        endpoint = f"{self.base_url}/models"
        args = self._auth_headers() + [endpoint]
        status, headers, body, latency = self.curl_fn(args)

        passed = False
        error_msg = None
        models_count = 0
        providers_map: Dict[str, int] = {}
        sample_models: List[str] = []

        min_models = resolve_min_models()

        if status == 200:
            try:
                data = json.loads(body)
                model_list = data.get("data", [])
                if isinstance(model_list, list):
                    models_count = len(model_list)
                    sample_models = [m.get("id", "") for m in model_list[:10] if isinstance(m, dict)]
                    for m in model_list:
                        if isinstance(m, dict) and "id" in m:
                            prov = extract_provider(str(m["id"]))
                            providers_map[prov] = providers_map.get(prov, 0) + 1

                    # Every entry must NAME a model. An entry with a missing,
                    # non-string or empty id cannot be requested by any client,
                    # so it is a catalog defect however many siblings it has —
                    # and the old count-only gate could not see it at all.
                    unnamed = [
                        index
                        for index, entry in enumerate(model_list)
                        if not isinstance(entry, dict)
                        or not isinstance(entry.get("id"), str)
                        or not entry.get("id", "").strip()
                    ]

                    if models_count < 1:
                        error_msg = (
                            "the catalog is EMPTY: GET /v1/models returned zero entries, so this "
                            "key can reach no model at all"
                        )
                    elif unnamed:
                        error_msg = (
                            f"{len(unnamed)} of {models_count} catalog entries carry no usable "
                            f"string 'id' (positions {unnamed[:5]}) — a client cannot request them"
                        )
                    elif min_models is not None and models_count < min_models:
                        error_msg = (
                            f"the catalog lists {models_count} models, below the floor the operator "
                            f"set with {MIN_MODELS_ENV}={min_models}. This is a PLANE expectation, "
                            "not a gateway contract: a virtual key scoped to a few models "
                            "legitimately lists a few."
                        )
                    else:
                        passed = True
                else:
                    error_msg = "Field 'data' in response is not a list"
            except Exception as exc:
                error_msg = f"Failed to parse models JSON response: {exc}"
        else:
            error_msg = f"HTTP {status}: {sanitize(body)}"

        res = {
            "check": "models_catalog",
            "name": "Models Catalog (GET /v1/models)",
            "method": "GET",
            "endpoint": "/v1/models",
            "passed": passed,
            "not_configured": False,
            "http_status": status,
            "latency_ms": latency,
            "request_id": headers.get("x-nr-request-id", "N/A"),
            "models_count": models_count,
            # Reported, never judged, unless the operator set a floor.
            "min_models_required": min_models,
            "providers_count": len(providers_map),
            "providers_distribution": dict(sorted(providers_map.items(), key=lambda item: -item[1])),
            "sample_models": sample_models,
            "error": error_msg,
        }
        self.results.append(res)
        return res

    def check_provider_inference_probe(self) -> Dict[str, Any]:
        """Probe the ROUTE UNDER TEST to verify provider wire execution.

        The route and the model are a runtime choice, because a virtual key is
        commonly scoped to a subset of both. The body is built in the shape that
        route's wire accepts, and the completion is read where that wire puts it
        — asserting `choices[0].message.content` against the Anthropic-shaped
        wire asserts against a key that is never there.
        """
        endpoint = f"{self.base_url}{self.route}"
        payload = json.dumps(build_body(self.route, self.model, "ping", max_tokens=2))
        args = self._auth_headers() + [
            "-H", "Content-Type: application/json",
            "-d", payload,
            endpoint,
        ]
        status, headers, body, latency = self.curl_fn(args)

        passed = False
        error_msg = None
        not_configured = False
        model_served = headers.get("x-nr-model")
        request_id = headers.get("x-nr-request-id", "N/A")
        completion_content = None

        # A 403 that NAMES `key_route_not_allowed` means the request never
        # reached the gateway behaviour under test — an absent precondition, not
        # a defect. Deliberately as narrow as the shared guard: any other 403,
        # and any other status, falls through to the assertions below.
        scope_detail = fixed_route_scope_detail(self.route, status, headers)
        if scope_detail:
            not_configured = True
            error_msg = scope_detail
        elif status == 200:
            body_ok, why = served_body_ok(self.route, body)
            if body_ok:
                completion_content = (served_text(self.route, body) or "").strip() or None
                passed = True
            else:
                error_msg = why
        else:
            error_msg = f"HTTP {status}: {sanitize(body)}"

        res = {
            "check": "model_probe",
            "name": f"Provider Probe ({self.model} on {self.route})",
            "method": "POST",
            "endpoint": f"/v1{self.route}",
            "wire": wire_of(self.route),
            "served_location": served_location(self.route),
            "passed": passed,
            "not_configured": not_configured,
            "http_status": status,
            "latency_ms": latency,
            "request_id": request_id,
            "model_requested": self.model,
            "model_served": model_served or "N/A",
            "sample_response": completion_content,
            "error": error_msg,
        }
        self.results.append(res)
        return res

    def run_all(self) -> Dict[str, Any]:
        """Run full model and provider health check suite."""
        self.results.clear()
        catalog_res = self.check_models_catalog()
        probe_res = self.check_provider_inference_probe()

        # NOT-CONFIGURED is not a pass: it is recorded, counted and surfaced as
        # PARTIAL, so a run that proved nothing never reads as a run that did.
        #
        # This module used to keep its own arithmetic —
        # `all(c["passed"] or c.get("not_configured"))` — which is TRUE for a run
        # in which every check was NOT-CONFIGURED and nothing was proven. The ONE
        # verdict rule now lives in `_curl_common.suite_verdict` and is shared by
        # every module and by run_all.py: nothing failed AND something was
        # actually proven.
        not_configured = sum(1 for c in self.results if c.get("not_configured"))
        proven = sum(1 for c in self.results if c["passed"])
        failed = len(self.results) - proven - not_configured
        verdict = suite_verdict(proven, failed, not_configured)
        all_passed = verdict["all_passed"]
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": self.base_url,
            "route": self.route,
            "model": self.model,
            # This module's top-level verdict key is `passed`, not `all_passed`
            # (run_all.py reads `model_result["passed"]`); the rule behind it is
            # the shared one.
            "passed": all_passed,
            "partial": verdict["partial"],
            "proved_nothing": verdict["proved_nothing"],
            "not_configured_checks": not_configured,
            "checks": self.results,
            "summary": {
                "total_models": catalog_res.get("models_count", 0),
                "total_providers": catalog_res.get("providers_count", 0),
                "probe_latency_ms": probe_res.get("latency_ms", 0.0),
                "not_configured": not_configured,
                "all_passed": all_passed,
                "proved_nothing": verdict["proved_nothing"],
            },
        }

    def render_markdown_summary(self, suite_result: Dict[str, Any]) -> str:
        """Render markdown summary for GitHub Step Summary or PR comment."""
        if not suite_result["passed"]:
            status_badge = "🔴 **FAILED**"
        elif suite_result.get("partial"):
            status_badge = "🟡 **PARTIAL** (a precondition was absent)"
        else:
            status_badge = "🟢 **PASSED**"
        summary = suite_result["summary"]

        lines = [
            "## 🤖 nRouter Pure-Curl Health Check: Models & Providers",
            "",
            f"**Overall Status**: {status_badge} | **Base URL**: `{suite_result['base_url']}`"
            f" | **Route**: `{suite_result.get('route', '')}` | **Model**: `{suite_result.get('model', '')}`",
            f"- **Total Servable Models**: `{summary['total_models']}`"
            + (
                f" (operator floor `{MIN_MODELS_ENV}` not set — reported, not judged)"
                if resolve_min_models() is None
                else f" (operator floor `{MIN_MODELS_ENV}={resolve_min_models()}`)"
            ),
            f"- **Active Providers Discovered**: `{summary['total_providers']}`",
            f"- **Provider Inference Latency**: `{summary['probe_latency_ms']} ms`",
            "",
            "### Health Check Results",
            "",
            "| Check | Method & Endpoint | Status | HTTP | Latency | Request ID | Details |",
            "|---|---|---|---|---|---|---|",
        ]

        for c in suite_result["checks"]:
            if c.get("not_configured"):
                st_icon = "🟡 Not-Configured"
            else:
                st_icon = "✅ Pass" if c["passed"] else "❌ Fail"
            req_id = c.get("request_id", "N/A")
            details = c.get("error") if not c["passed"] else f"Count: {c.get('models_count', '')}"
            if c["check"] == "model_probe" and c["passed"]:
                details = f"Served: `{c.get('model_served')}`"
            lines.append(
                f"| {c['name']} | `{c['method']} {c['endpoint']}` | {st_icon} | {c['http_status']} | {c['latency_ms']}ms | `{req_id}` | {details} |"
            )

        catalog = next((c for c in suite_result["checks"] if c["check"] == "models_catalog"), None)
        if catalog and catalog.get("providers_distribution"):
            lines.extend([
                "",
                "### Provider Distribution",
                "",
                "| Provider | Models Registered |",
                "|---|---|",
            ])
            for prov, count in list(catalog["providers_distribution"].items())[:15]:
                lines.append(f"| **{prov}** | {count} |")

        return "\n".join(lines)


def run_self_test() -> int:
    """Validate model_curl health check offline using mock responses.

    Every checker below names its route and model EXPLICITLY, and the operator's
    catalog floor is cleared for the duration. A self-test that inherited
    NROUTER_HEALTH_ROUTE / NROUTER_HEALTH_MODEL / NROUTER_HEALTH_MIN_MODELS from
    the shell would pass or fail according to the terminal it was run in, which
    is not a gate.
    """
    print("Running model_curl.py --self-test (offline mode)...")
    _saved_floor = os.environ.pop(MIN_MODELS_ENV, None)
    try:
        return _run_self_test_body()
    finally:
        if _saved_floor is not None:
            os.environ[MIN_MODELS_ENV] = _saved_floor


def _run_self_test_body() -> int:
    """The self-test proper; `run_self_test` owns the environment isolation."""

    # Mock curl responses
    def mock_curl(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        endpoint = args[-1]
        if endpoint.endswith("/models"):
            mock_body = json.dumps({
                "object": "list",
                "data": [
                    {"id": "openai/gpt-4o", "object": "model", "owned_by": "openai"},
                    {"id": "openai/gpt-4o-mini", "object": "model", "owned_by": "openai"},
                    {"id": "anthropic/claude-3-5-sonnet", "object": "model", "owned_by": "anthropic"},
                    {"id": "anthropic/claude-3-haiku", "object": "model", "owned_by": "anthropic"},
                    {"id": "google/gemini-1.5-pro", "object": "model", "owned_by": "google"},
                    {"id": "google/gemini-1.5-flash", "object": "model", "owned_by": "google"},
                    {"id": "meta/llama-3.1-70b", "object": "model", "owned_by": "meta"},
                    {"id": "mistral/mistral-large", "object": "model", "owned_by": "mistral"},
                    {"id": "deepseek/deepseek-chat", "object": "model", "owned_by": "deepseek"},
                    {"id": "qwen/qwen-2.5-72b", "object": "model", "owned_by": "alibaba"},
                    {"id": "nrouter/auto", "object": "model", "owned_by": "nrouter"},
                ],
            })
            headers = {"x-nr-request-id": "req-mock-models-catalog", "content-type": "application/json"}
            return 200, headers, mock_body, 12.5
        elif endpoint.endswith("/chat/completions"):
            mock_body = json.dumps({
                "id": "chatcmpl-mock123",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}}],
                "usage": {"total_tokens": 5},
            })
            headers = {
                "x-nr-request-id": "req-mock-probe-123",
                "x-nr-model": "gpt-4o-mini",
                "content-type": "application/json",
            }
            return 200, headers, mock_body, 45.2
        return 404, {}, "Not Found", 5.0

    checker = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/chat/completions",
        model="openai/gpt-4o-mini",
        curl_fn=mock_curl,
    )
    result = checker.run_all()

    assert result["passed"] is True, "Self-test failed: expected suite to pass"
    assert result["summary"]["total_models"] == 11, f"Expected 11 entries, got {result['summary']['total_models']}"
    assert result["summary"]["total_providers"] >= 7, f"Expected >= 7 providers, got {result['summary']['total_providers']}"

    # Verify markdown rendering
    md = checker.render_markdown_summary(result)
    assert "nRouter Pure-Curl Health Check: Models & Providers" in md, "Missing title in markdown"
    assert "Provider Distribution" in md, "Missing provider distribution table"

    # Test failure branch
    def mock_failing_curl(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        return 500, {"x-nr-request-id": "req-mock-err"}, "Internal Server Error", 8.0

    failing_checker = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/chat/completions",
        model="openai/gpt-4o-mini",
        curl_fn=mock_failing_curl,
    )
    failing_result = failing_checker.run_all()
    assert failing_result["passed"] is False, "Failing checker should report passed=False"

    # ---------------------------------------------------------------- D6
    # THE ROUTE AND MODEL UNDER TEST REACH THE PROBE.
    #
    # A virtual key is commonly scoped to a subset of routes and models. Before
    # this, the probe posted a hardcoded `openai/gpt-4o-mini` to a hardcoded
    # `/chat/completions` whatever the operator asked for, so a key scoped to
    # `/messages` produced `403 key_route_not_allowed` — a fact about the KEY
    # POLICY reported as a gateway failure. The probe must ask the route under
    # test, on that wire's body shape, and read that wire's completion location.
    seen_paths: List[str] = []
    seen_bodies: List[str] = []

    def mock_scoped_curl(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        endpoint = args[-1]
        seen_paths.append(endpoint)
        for index, arg in enumerate(args):
            if arg == "-d" and index + 1 < len(args):
                seen_bodies.append(args[index + 1])
        if endpoint.endswith("/models"):
            return 200, {"x-nr-request-id": "req-scoped-catalog"}, json.dumps({
                "object": "list",
                "data": [
                    {"id": "claude-haiku-4-5-20251001", "object": "model"},
                    {"id": "claude-sonnet-4-5-20250929", "object": "model"},
                ],
            }), 11.0
        if endpoint.endswith("/messages"):
            # The Anthropic-shaped wire puts the completion at content[0].text,
            # NOT at choices[0].message.content.
            return 200, {
                "x-nr-request-id": "req-scoped-probe",
                "x-nr-model": "claude-haiku-4-5-20251001",
            }, json.dumps({
                "id": "msg_scoped",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "pong"}],
            }), 30.0
        # Every other route is refused by this key's route policy.
        return 403, {"x-nr-auth-reason": "key_route_not_allowed"}, json.dumps({
            "error": {"message": "this API key is not allowed to use this route", "type": "gateway_error"}
        }), 9.0

    scoped = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_scoped_curl,
    )
    scoped_result = scoped.run_all()
    probe = next(c for c in scoped_result["checks"] if c["check"] == "model_probe")
    assert probe["passed"] is True, (
        "the probe must ask the ROUTE UNDER TEST: a key scoped to /messages is not a "
        f"gateway failure; got {probe.get('error')!r}"
    )
    assert probe["endpoint"] == "/v1/messages", (
        f"the reported endpoint must name the route actually asked: {probe['endpoint']!r}"
    )
    assert any(path.endswith("/messages") for path in seen_paths), (
        f"no request reached /messages at all: {seen_paths!r}"
    )
    assert not any(path.endswith("/chat/completions") for path in seen_paths), (
        f"the probe still posted to the hardcoded route: {seen_paths!r}"
    )
    assert seen_bodies and '"claude-haiku-4-5-20251001"' in seen_bodies[0], (
        f"the probe sent a model the operator did not name: {seen_bodies!r}"
    )
    assert scoped_result["passed"] is True, (
        "the scoped run must be green end to end; these rows are the module's own "
        "assumptions reported as gateway defects: "
        + repr([(c["check"], c.get("error")) for c in scoped_result["checks"] if not c["passed"]])
    )

    # ...and a 403 that names a DIFFERENT reason is a REAL failure, never an
    # absent precondition. Without this the scope guard would swallow every
    # denial, which is the opposite of what it is for.
    def mock_model_denied(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        if args[-1].endswith("/models"):
            return 200, {}, json.dumps({"data": [{"id": "m-1", "object": "model"}]}), 5.0
        return 403, {"x-nr-auth-reason": "key_model_not_allowed"}, json.dumps({
            "error": {"message": "this API key is not allowed to use this model", "type": "gateway_error"}
        }), 6.0

    denied = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_model_denied,
    )
    # A run in which EVERY check was NOT-CONFIGURED proved NOTHING, and must never
    # read as passing. Under this module's old arithmetic —
    # `all(c["passed"] or c.get("not_configured"))` — that run reported
    # `passed: true`, and a CI gate reading it waved through a suite that had not
    # reached the gateway once.
    absent = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_scoped_curl,
    )

    def absent_check(name: str):
        def record() -> Dict[str, Any]:
            row = {
                "check": name,
                "name": name,
                "passed": False,
                "not_configured": True,
                "error": "precondition absent on this plane",
            }
            absent.results.append(row)
            return row
        return record

    absent.check_models_catalog = absent_check("models_catalog")  # type: ignore[method-assign]
    absent.check_provider_inference_probe = absent_check("model_probe")  # type: ignore[method-assign]
    absent_result = absent.run_all()
    assert absent_result["not_configured_checks"] == len(absent_result["checks"]), absent_result
    assert absent_result["passed"] is False, (
        "an all-NOT-CONFIGURED run proved nothing and must not report passed"
    )
    assert absent_result["proved_nothing"] is True, absent_result
    assert absent_result["summary"]["all_passed"] is False, absent_result["summary"]

    denied_probe = next(c for c in denied.run_all()["checks"] if c["check"] == "model_probe")
    assert denied_probe["passed"] is False, "a model-policy denial is a failure"
    assert denied_probe.get("not_configured") is not True, (
        "only key_route_not_allowed is an absent precondition; key_model_not_allowed "
        "is a real finding and must not be downgraded"
    )

    # ---------------------------------------------------------------- D7
    # A SCOPED KEY LEGITIMATELY SEES FEW MODELS.
    #
    # `Models count (2) below threshold (10)` was a hardcoded plane assumption
    # reported as a gateway defect. The catalog assertion is now about SHAPE —
    # at least one entry, every id a non-empty string — and the count is
    # reported, not judged, unless the operator sets a threshold themselves.
    catalog = next(c for c in scoped_result["checks"] if c["check"] == "models_catalog")
    assert catalog["passed"] is True, (
        f"a two-model scoped catalog is not a failure: {catalog.get('error')!r}"
    )
    assert catalog["models_count"] == 2, catalog["models_count"]

    def mock_empty_catalog(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        if args[-1].endswith("/models"):
            return 200, {}, json.dumps({"object": "list", "data": []}), 4.0
        return 200, {}, json.dumps({"content": [{"type": "text", "text": "ok"}]}), 4.0

    empty_catalog = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/messages",
        curl_fn=mock_empty_catalog,
    ).run_all()
    empty_row = next(c for c in empty_catalog["checks"] if c["check"] == "models_catalog")
    assert empty_row["passed"] is False, "an EMPTY catalog is a real failure — this key can reach no model"

    def mock_unnamed_model(args: List[str], timeout_s: int = 25) -> Tuple[int, Dict[str, str], str, float]:
        if args[-1].endswith("/models"):
            return 200, {}, json.dumps({"data": [{"id": "ok-1"}, {"id": 7}]}), 4.0
        return 200, {}, json.dumps({"content": [{"type": "text", "text": "ok"}]}), 4.0

    unnamed = ModelCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-key-for-test",
        route="/messages",
        curl_fn=mock_unnamed_model,
    ).run_all()
    unnamed_row = next(c for c in unnamed["checks"] if c["check"] == "models_catalog")
    assert unnamed_row["passed"] is False, "a catalog entry whose id is not a string must FAIL"
    assert "id" in (unnamed_row.get("error") or ""), unnamed_row.get("error")

    # The strict threshold still exists — behind an EXPLICIT operator opt-in.
    saved_min = os.environ.get(MIN_MODELS_ENV)
    os.environ[MIN_MODELS_ENV] = "10"
    try:
        thresholded = ModelCurlHealthCheck(
            base_url="https://mock.api.nrouter.ai/v1",
            api_key="sk-nrouter-mock-key-for-test",
            route="/messages",
            curl_fn=mock_scoped_curl,
        ).run_all()
        row = next(c for c in thresholded["checks"] if c["check"] == "models_catalog")
        assert row["passed"] is False, "an operator-set floor of 10 must bite on a 2-model catalog"
        assert MIN_MODELS_ENV in (row.get("error") or ""), (
            f"the detail must name the variable the operator set: {row.get('error')!r}"
        )
    finally:
        if saved_min is None:
            os.environ.pop(MIN_MODELS_ENV, None)
        else:
            os.environ[MIN_MODELS_ENV] = saved_min

    # THE `--json` CONTRACT, driven through the REAL main(). A banner on stdout
    # above the document is what makes `model_curl.py --json > model.json`
    # unparseable, so the only honest test runs main() and parses what it wrote.
    # The checker is substituted for a double, so nothing touches the network.
    class _StubChecker:
        def __init__(self, **_kwargs):
            self.route = "/chat/completions"
            self.model = DEFAULT_PROBE_MODEL

        def run_all(self):
            return result

        def render_markdown_summary(self, _result):
            return "## stub"

    saved_class = globals()["ModelCurlHealthCheck"]
    globals()["ModelCurlHealthCheck"] = _StubChecker
    try:
        for argv in (
            ["model_curl.py", "--json"],
            ["model_curl.py"],
        ):
            main_json_stdout_contract_self_test(
                main,
                argv,
                "=== Starting nRouter Model & Provider Curl Health Check ===",
                ("passed", "checks", "summary"),
            )
    finally:
        globals()["ModelCurlHealthCheck"] = saved_class

    print("[PASS] model_curl.py self-test passed cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Model & Provider Pure-Curl Health Check")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL), help="Gateway Base URL")
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""), help="nRouter API key")
    # `--probe-model` is this module's historical name for the model under test.
    # `--route` / `--model` are the directory-wide pair every other module uses;
    # they default to "" so an explicit `--probe-model` still wins.
    parser.add_argument("--probe-model", default="", help=f"Alias for --model (env {MODEL_ENV})")
    parser.add_argument(
        "--route",
        default="",
        help=f"Route under test, one of: {', '.join(ALLOWED_ROUTES)} (env {ROUTE_ENV})",
    )
    parser.add_argument("--model", default="", help=f"Model under test (env {MODEL_ENV})")
    parser.add_argument("--step-summary", action="store_true", help="Write markdown summary to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Output JSON results to stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    # The key comes from --api-key or NROUTER_API_KEY, and nowhere else. There
    # is deliberately no credentials-file fallback: this repository is public, a
    # hardcoded path leaks an internal convention, and a fallback would send
    # whatever key it found to whatever --base-url the caller passed.
    api_key = args.api_key
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live health check.", file=sys.stderr)
        print("Set NROUTER_API_KEY or use --self-test for offline validation.", file=sys.stderr)
        return 1

    try:
        checker = ModelCurlHealthCheck(
            base_url=args.base_url,
            api_key=api_key,
            probe_model=args.probe_model,
            route=args.route,
            model=args.model,
        )
    except ValueError as exc:  # an unsupported --route names itself
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # THE `--json` CONTRACT: with --json, stdout carries EXACTLY ONE JSON
    # document and nothing else, so `model_curl.py --json > model.json` produces
    # a parseable file. The human report is not discarded — it moves to stderr,
    # so a person watching the terminal still sees it. Matches `emit_results`.
    report = sys.stderr if args.json else sys.stdout

    print(f"=== Starting nRouter Model & Provider Curl Health Check ===", file=report)
    print(f"Base URL:    {args.base_url}", file=report)
    print(f"Route:       {checker.route}  (wire: {wire_of(checker.route)})", file=report)
    print(f"Probe Model: {checker.model}", file=report)
    print("------------------------------------------------------------", file=report)

    result = checker.run_all()

    for check in result["checks"]:
        st = "NOT-CONFIGURED" if check.get("not_configured") else ("PASS" if check["passed"] else "FAIL")
        print(f"[{st}] {check['name']} - HTTP {check['http_status']} ({check['latency_ms']}ms)", file=report)
        if not check["passed"] and check.get("error"):
            label = "Absent:" if check.get("not_configured") else "Error: "
            print(f"       {label} {check['error']}", file=report)

    print("------------------------------------------------------------", file=report)
    min_models = resolve_min_models()
    floor_note = f"(floor {MIN_MODELS_ENV}={min_models})" if min_models else f"({MIN_MODELS_ENV} unset — reported, not judged)"
    print(f"Catalog Models:    {result['summary']['total_models']} {floor_note}", file=report)
    print(f"Active Providers:  {result['summary']['total_providers']}", file=report)
    print(f"Not-Configured:    {result['summary']['not_configured']}", file=report)
    overall = "PASS" if result["passed"] else "FAIL"
    if result["passed"] and result["partial"]:
        overall = "PARTIAL (a precondition was absent — this is not release evidence)"
    print(f"Overall Result:    {overall}", file=report)

    if args.step_summary:
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            md_content = checker.render_markdown_summary(result)
            try:
                with open(step_summary_path, "a") as f:
                    f.write("\n" + md_content + "\n")
                print(f"Appended markdown summary to GITHUB_STEP_SUMMARY ({step_summary_path})", file=report)
            except Exception as exc:
                print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {exc}", file=sys.stderr)

    if args.json:
        # The one and only thing this function writes to stdout.
        print(json.dumps(result, indent=2))

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
