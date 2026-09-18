#!/usr/bin/env python3
"""nRouter Feature-by-Feature Pure-Curl Health Check (`feature_curl`).

Executes 40 comprehensive feature-specific curl checks covering Gateway endpoints
and exercising supported request parameters, headers, and refusal contracts.
Supports filtering by feature prefix via `--feature <prefix>` (e.g. `fallback_`, `ratelimit_`).

⚠️ TWO KINDS OF PROBE, and the difference is load-bearing.

  **Route-under-test** probes (`chat_`, `fallback_`, `ratelimit_`, `cache_`,
  `context_limit_`, `guardrail_`, `routing_`, `metering_`, `waf_malformed_json`)
  exercise behaviour that belongs to no single path. They ask the route named by
  `NROUTER_HEALTH_ROUTE` / `--route` with the model named by
  `NROUTER_HEALTH_MODEL` / `--model` (`--chat-model` is the historical alias),
  building the body in that wire's shape and reading the completion where that
  wire puts it. A probe whose PARAMETER does not exist on that wire —
  `response_format` on the Anthropic-shaped wire, say — reports NOT-CONFIGURED
  naming the wire instead of earning a 400 about its own request.

  **Fixed-route** probes (`messages_`, `tokens_`, `embed_`, `completions_`,
  `models_`, `waf_unauthorized_token`, `waf_unknown_model_not_found`) are pinned
  by their own nature. They keep their route and carry the fixed-route scope
  guard: a 403 naming `key_route_not_allowed` on THAT path marks THAT probe
  NOT-CONFIGURED and lets the other thirty-nine run.

A key scoped to a subset of routes and models is the normal case, not an edge
case. Before this, all 40 probes carried their own hardcoded route and model, so
such a key produced 30 × `403 key_route_not_allowed` — facts about the key
policy reported as gateway defects.

Feature Suites & Prefixes:
  1. Core inference parameters, on the ROUTE UNDER TEST (`chat_`):
     - #1  `chat_basic` (model, messages, max_tokens)
     - #2  `chat_system_multiturn` (system, user, assistant roles)
     - #3  `chat_sampling_params` (temperature, top_p)
     - #4  `chat_stop_sequences` (stop array)
     - #5  `chat_penalties` (presence_penalty, frequency_penalty)
     - #6  `chat_deterministic_seed` (seed, temperature)
     - #7  `chat_json_mode` (response_format: json_object)
     - #8  `chat_tool_calling` (tools, tool_choice: auto)
     - #9  `chat_streaming_sse` (stream: true)
     - #10 `chat_logprobs` (logprobs, top_logprobs)
     - #11 `chat_user_identifier` (user)

  2. Anthropic Messages Wire (`messages_`):
     - #12 `messages_basic` (anthropic-version, model, messages)
     - #13 `messages_system_prompt` (top-level system parameter)
     - #14 `messages_streaming_sse` (stream: true, SSE events)
     - #15 `messages_content_blocks` (content: [{type: text}])
     - #16 `messages_stop_sequences` (stop_sequences array)
     - #17 `messages_temperature` (temperature sampling)

  3. Token Counting (`tokens_`):
     - #18 `tokens_messages` (model, messages -> input_tokens)
     - #19 `tokens_with_system` (model, system, messages -> input_tokens)

  4. Text Embeddings (`embed_`):
     - #20 `embed_single_input` (model, input: string)
     - #21 `embed_batch_array` (model, input: list)
     - #22 `embed_dimensions` (dimensions: 256)
     - #23 `embed_encoding_format` (encoding_format: float)

  5. Legacy Text Completions (`completions_`):
     - #24 `completions_basic` (model, prompt, max_tokens)
     - #25 `completions_stop_sequence` (model, prompt, stop)

  6. Models Catalog & Retrieval (`models_`):
     - #26 `models_list` (GET /v1/models catalog listing)
     - #27 `models_detail_retrieve` (GET /v1/models/{model_id})

  7. Fallback Routing (`fallback_`):
     - #28 `fallback_refused_target` (unauthorized target model -> HTTP 400) (V2)

  8. Rate Limiting (`ratelimit_`):
     - #29 `ratelimit_preflight_slot` (tenant RPM/TPM slot verification) (V6)
     - #30 `ratelimit_concurrency_burst` (burst concurrency slot limit) (V6)

  9. Response Cache (`cache_`):
     - #31 `cache_ttl_control` (header: x-nr-cache-ttl: 60)
     - #32 `cache_bypass` (payload: nrouter_cache: false -> header: x-nr-response-cache: bypass) (V5)

  10. Context Ceilings (`context_limit_`):
     - #33 `context_limit_output` (payload: max_tokens > ceiling -> HTTP 400) (V7)

  11. Guardrail Controls (`guardrail_`):
     - #34 `guardrail_foreign_id` (foreign/invalid guardrail UUID -> HTTP 400) (V4)

  12. Gateway Routing & Tracing (`routing_`):
     - #35 `routing_strategy_header` (header: x-nr-routing-strategy: fallback)
     - #36 `routing_client_request_id` (header: x-nr-client-request-id)

  13. Metering & FinOps (`metering_`):
     - #37 `metering_cost_headers` (headers: x-nr-request-cost, x-nr-total-tokens) (V8)

  14. Edge WAF, Security & Contract Refusals (`waf_`):
     - #38 `waf_unauthorized_token` (Missing auth -> HTTP 401 Unauthorized)
     - #39 `waf_unknown_model_not_found` (Unknown model route -> HTTP 404 Not Found)
     - #40 `waf_malformed_json` (Malformed JSON body syntax -> HTTP 400 Bad Request)

Usage:
  python3 scripts/curl_health_checks/feature_curl.py --self-test
  python3 scripts/curl_health_checks/feature_curl.py --quick
  python3 scripts/curl_health_checks/feature_curl.py --feature fallback_
  python3 scripts/curl_health_checks/feature_curl.py --feature ratelimit_
  python3 scripts/curl_health_checks/feature_curl.py --feature cache_
  python3 scripts/curl_health_checks/feature_curl.py
  python3 scripts/curl_health_checks/feature_curl.py --step-summary
  python3 scripts/curl_health_checks/feature_curl.py --json
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
    build_multiturn_body,
    fixed_route_scope_detail,
    main_json_stdout_contract_self_test,
    max_tokens_field,
    resolve_model,
    resolve_route,
    served_body_ok,
    served_location,
    suite_verdict,
    wire_of,
)

DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"

def __getattr__(name: str) -> Any:
    if name == "DEFAULT_CHAT_MODEL":
        val = resolve_model()
        globals()["DEFAULT_CHAT_MODEL"] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Every wire this directory knows. A feature declares which of them its
# PARAMETERS exist on; on any other wire the parameter is not a gateway defect,
# it is simply not part of that wire's request shape.
ALL_WIRES = ("chat", "messages", "responses", "completions")

# Routes some probes are pinned to BY NATURE: an embeddings body has nowhere
# else to go, token counting is an Anthropic-wire endpoint, and legacy
# completions is its own path. These keep their own route whatever is under
# test, and carry the fixed-route scope guard instead.
FIXED_MESSAGES_ROUTE = "/v1/messages"
FIXED_COUNT_TOKENS_ROUTE = "/v1/messages/count_tokens"
FIXED_EMBEDDINGS_ROUTE = "/v1/embeddings"
FIXED_COMPLETIONS_ROUTE = "/v1/completions"


def _default_messages_model() -> str:
    """The model for the pinned `/v1/messages` probes.

    When the route under test IS the Anthropic-shaped wire, the operator has
    already named the model those probes must use — reaching past it to a
    constant is how 30 probes ended up asking for a model the key never had.
    Otherwise fall back to a known small Anthropic model.
    """
    try:
        if resolve_route() == "/messages":
            return resolve_model()
    except ValueError:
        pass
    return os.environ.get("NROUTER_HEALTH_MESSAGES_MODEL", "") or "claude-haiku-4-5-20251001"


DEFAULT_MESSAGES_MODEL = _default_messages_model()
DEFAULT_EMBED_MODEL = "text-embedding-3-small"

# Credential sanitization
SECRET_PATTERNS = [
    re.compile(r"sk-nrouter-[A-Za-z0-9_-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]


def sanitize(text: str) -> str:
    """Redact sensitive tokens and auth headers."""
    if not text:
        return ""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def run_curl(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
    """Execute raw curl command and parse status code, response headers, body, and latency."""
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


def parse_request_cost(headers: Dict[str, str]) -> Optional[float]:
    """Parse x-nr-request-cost header, returning None if unpriced or refused."""
    raw = headers.get("x-nr-request-cost")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class FeatureCurlHealthCheck:
    """Feature-by-feature pure curl health check runner."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        chat_model: Optional[str] = None,
        messages_model: str = DEFAULT_MESSAGES_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        curl_fn: Callable = run_curl,
        route: str = "",
        model: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        # The key comes from the caller or NROUTER_API_KEY, and nowhere else.
        # There is deliberately no credentials-file fallback: this repository is
        # public, a hardcoded path leaks an internal convention, and a silent
        # fallback here would send whatever key it found to whatever base_url
        # this object was constructed with.
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        # The route and model UNDER TEST. Every inference-path probe asks this
        # route on this model; `chat_model` survives as the historical name for
        # the same thing, so an explicit `--model` wins over it.
        self.route = resolve_route(route)
        self.model = resolve_model(model or chat_model or "")
        self.chat_model = self.model
        self.messages_model = messages_model
        self.embed_model = embed_model
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    def _auth_headers(self) -> List[str]:
        return [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "User-Agent: nrouter-feature-curl-health-check/1.0",
        ]

    # ------------------------------------------------------------------ wires
    def _wire(self) -> str:
        return wire_of(self.route)

    def _under_test_endpoint(self) -> str:
        return f"/v1{self.route}"

    def _wire_headers(self) -> Dict[str, str]:
        """Headers the route under test requires, beyond Content-Type."""
        headers = {"Content-Type": "application/json"}
        if self._wire() == "messages":
            headers["anthropic-version"] = "2023-06-01"
        return headers

    def _served_ok(self, body: str) -> bool:
        """A 200 on the route under test must carry a completion where THIS wire puts one."""
        return served_body_ok(self.route, body)[0]

    def _under_test(
        self,
        feature_id: str,
        category: str,
        name: str,
        parameters_tested: List[str],
        payload: Optional[Dict[str, Any]],
        wires: Tuple[str, ...] = ALL_WIRES,
        expected_status: int = 200,
        validate: Optional[Callable] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        raw_payload: Optional[str] = None,
    ) -> Dict[str, Any]:
        """A probe that asks the ROUTE UNDER TEST rather than a hardcoded path."""
        feature: Dict[str, Any] = {
            "id": feature_id,
            "category": category,
            "name": name,
            "method": "POST",
            "endpoint": self._under_test_endpoint(),
            "route_under_test": True,
            "wires": wires,
            "extra_headers": {**self._wire_headers(), **(extra_headers or {})},
            "payload": payload,
            "parameters_tested": parameters_tested,
            "expected_status": expected_status,
            "validate": validate or (lambda s, h, b: s == 200 and self._served_ok(b) and bool(h.get("x-nr-request-id"))),
        }
        if raw_payload is not None:
            feature["raw_payload"] = raw_payload
        return feature

    def define_features(self) -> List[Dict[str, Any]]:
        """Construct the 40 feature-specific curl definitions.

        Two kinds of probe live here, and the difference is the whole point:

        * **Route-under-test** probes exercise gateway behaviour that is not
          specific to any one path — sampling, streaming, fallbacks, ceilings,
          cache, metering, tracing. They ask `self.route` on that wire's body
          shape. A probe whose PARAMETER does not exist on that wire declares so
          in `wires` and reports NOT-CONFIGURED rather than inventing a 400.
        * **Fixed-route** probes are pinned by their own nature — an embeddings
          body has nowhere else to go, token counting is an Anthropic-wire
          endpoint, legacy completions is its own path. They keep their route
          and carry the fixed-route scope guard, so a key scoped away from that
          ONE path marks that ONE probe and never the other thirty-nine.
        """
        features: List[Dict[str, Any]] = []
        wire = self._wire()

        # ---------------------------------------------------------------------
        # 1. Core inference parameters, on the ROUTE UNDER TEST
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "chat_basic", "Chat Completions", "Basic Completion",
            ["model", "messages|input|prompt", max_tokens_field(self.route)],
            build_body(self.route, self.model, "Reply OK", max_tokens=5),
        ))

        multiturn = build_multiturn_body(
            self.route, self.model, ["What is 2+2?", "4", "Add 3 more."], max_tokens=5,
        )
        # The system prompt lives in a different place on each wire: a `system`
        # ROLE on the chat wire, a TOP-LEVEL `system` field on the Anthropic one.
        if wire == "messages":
            multiturn["system"] = "You are a concise arithmetic calculator."
        elif wire == "chat":
            multiturn["messages"].insert(
                0, {"role": "system", "content": "You are a concise arithmetic calculator."}
            )
        features.append(self._under_test(
            "chat_system_multiturn", "Chat Completions", "System Prompt & Multi-Turn History",
            ["system prompt", "multi-turn user/assistant history"],
            multiturn,
            wires=("chat", "messages"),
        ))

        features.append(self._under_test(
            "chat_temperature", "Chat Completions", "Sampling Temperature",
            ["temperature"],
            build_body(self.route, self.model, "Name a color", max_tokens=5, temperature=0.7),
        ))

        features.append(self._under_test(
            "chat_top_p", "Chat Completions", "Sampling Top-P",
            ["top_p"],
            build_body(self.route, self.model, "Name a color", max_tokens=5, top_p=0.95),
        ))

        features.append(self._under_test(
            "chat_sampling_params", "Chat Completions", "Sampling Temperature & Top-P",
            ["temperature", "top_p"],
            build_body(self.route, self.model, "Name a color", max_tokens=5, temperature=0.7, top_p=0.95),
            wires=("chat",),
        ))

        # `stop` on the chat/legacy wires, `stop_sequences` on the Anthropic one.
        stop_field = "stop_sequences" if wire == "messages" else "stop"
        features.append(self._under_test(
            "chat_stop_sequences", "Chat Completions", "Stop Sequences",
            [stop_field],
            build_body(self.route, self.model, "Count from 1 to 5: 1 2 3 4 5",
                       max_tokens=10, **{stop_field: ["3", "STOP"]}),
            wires=("chat", "messages", "completions"),
        ))

        features.append(self._under_test(
            "chat_penalties", "Chat Completions", "Presence & Frequency Penalties",
            ["presence_penalty", "frequency_penalty"],
            build_body(self.route, self.model, "List 3 words", max_tokens=10,
                       presence_penalty=0.5, frequency_penalty=0.5),
            wires=("chat", "completions"),
        ))

        features.append(self._under_test(
            "chat_deterministic_seed", "Chat Completions", "Deterministic Seed",
            ["seed", "temperature: 0.0"],
            build_body(self.route, self.model, "1+1=", max_tokens=4, seed=42, temperature=0.0),
            wires=("chat", "completions"),
        ))

        features.append(self._under_test(
            "chat_json_mode", "Chat Completions", "Structured JSON Object Mode",
            ["response_format.type: json_object"],
            build_body(self.route, self.model,
                       "Return a JSON object with key status set to ok",
                       max_tokens=20, response_format={"type": "json_object"}),
            wires=("chat",),
            validate=lambda s, h, b: s == 200 and "status" in b and "{" in b,
        ))

        # The two wires that carry tools describe them differently.
        if wire == "messages":
            tool_extras: Dict[str, Any] = {
                "tools": [{
                    "name": "get_weather",
                    "description": "Get current weather for location",
                    "input_schema": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                }],
            }
        else:
            tool_extras = {
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather for location",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                            "required": ["location"],
                        },
                    },
                }],
                "tool_choice": "auto",
            }
        features.append(self._under_test(
            "chat_tool_calling", "Chat Completions", "Tools & Function Calling",
            ["tools", "tool_choice"],
            build_body(self.route, self.model, "What is the weather in Tokyo?",
                       max_tokens=30, **tool_extras),
            wires=("chat", "messages"),
            validate=lambda s, h, b: s == 200 and ("tool_calls" in b or "tool_use" in b or "get_weather" in b),
        ))

        features.append(self._under_test(
            "chat_streaming_sse", "Chat Completions", "Server-Sent Events (SSE) Streaming",
            ["stream: true"],
            build_body(self.route, self.model, "Say hi", max_tokens=4, stream=True),
            validate=lambda s, h, b: s == 200 and (
                "text/event-stream" in h.get("content-type", "") or "data:" in b or "event:" in b
            ),
        ))

        features.append(self._under_test(
            "chat_logprobs", "Chat Completions", "Logprobs & Top-Logprobs",
            ["logprobs: true", "top_logprobs: 2"],
            build_body(self.route, self.model, "1+1=", max_tokens=2, logprobs=True, top_logprobs=2),
            wires=("chat",),
            validate=lambda s, h, b: s == 200 and "logprobs" in b,
        ))

        features.append(self._under_test(
            "chat_user_identifier", "Chat Completions", "Client End-User ID Tracking",
            ["user: string"],
            build_body(self.route, self.model, "Ping", max_tokens=3,
                       user="usr_tenant_audit_client_99"),
            wires=("chat", "completions"),
        ))

        # ---------------------------------------------------------------------
        # 2. Anthropic Messages Wire (/v1/messages)
        # ---------------------------------------------------------------------
        features.append({
            "id": "messages_basic",
            "category": "Anthropic Messages",
            "name": "Basic Messages Request",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "max_tokens": 5,
            },
            "parameters_tested": ["anthropic-version", "model", "messages", "max_tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "content" in b and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "messages_system_prompt",
            "category": "Anthropic Messages",
            "name": "Top-Level System Prompt",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "system": "You are a concise mathematics assistant.",
                "messages": [{"role": "user", "content": "What is 3*3?"}],
                "max_tokens": 5,
            },
            "parameters_tested": ["system: string"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "content" in b,
        })

        features.append({
            "id": "messages_streaming_sse",
            "category": "Anthropic Messages",
            "name": "Anthropic SSE Event Streaming",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
                "max_tokens": 5,
            },
            "parameters_tested": ["stream: true"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and ("event:" in b or "text/event-stream" in h.get("content-type", "")),
        })

        features.append({
            "id": "messages_content_blocks",
            "category": "Anthropic Messages",
            "name": "Content Block Array Structure",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": [{"type": "text", "text": "2+2="}]}],
                "max_tokens": 5,
            },
            "parameters_tested": ["messages.content[type: text]"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "content" in b,
        })

        features.append({
            "id": "messages_stop_sequences",
            "category": "Anthropic Messages",
            "name": "Stop Sequences Control",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": "Count to 5: 1 2 3 4 5"}],
                "stop_sequences": ["3"],
                "max_tokens": 10,
            },
            "parameters_tested": ["stop_sequences: array"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "content" in b,
        })

        features.append({
            "id": "messages_temperature",
            "category": "Anthropic Messages",
            "name": "Temperature Sampling",
            "method": "POST",
            "endpoint": "/v1/messages",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": "Pick a letter"}],
                "temperature": 0.2,
                "max_tokens": 5,
            },
            "parameters_tested": ["temperature: float"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "content" in b,
        })

        # ---------------------------------------------------------------------
        # 3. Token Counting (/v1/messages/count_tokens)
        # ---------------------------------------------------------------------
        features.append({
            "id": "tokens_messages",
            "category": "Token Counting",
            "name": "Token Calculation for Messages",
            "method": "POST",
            "endpoint": "/v1/messages/count_tokens",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "messages": [{"role": "user", "content": "The quick brown fox jumps over the lazy dog."}],
            },
            "parameters_tested": ["model", "messages -> input_tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "input_tokens" in b and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "tokens_with_system",
            "category": "Token Counting",
            "name": "Token Calculation with System Prompt",
            "method": "POST",
            "endpoint": "/v1/messages/count_tokens",
            "extra_headers": {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            "payload": {
                "model": self.messages_model,
                "system": "You are an enterprise support triage agent.",
                "messages": [{"role": "user", "content": "Help me reset password."}],
            },
            "parameters_tested": ["system", "messages -> input_tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "input_tokens" in b,
        })

        # ---------------------------------------------------------------------
        # 4. Text Embeddings (/v1/embeddings)
        # ---------------------------------------------------------------------
        features.append({
            "id": "embed_single_input",
            "category": "Text Embeddings",
            "name": "Single String Vector Embedding",
            "method": "POST",
            "endpoint": "/v1/embeddings",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.embed_model,
                "input": "nRouter high-performance AI inference gateway",
            },
            "parameters_tested": ["model", "input: string"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "embedding" in b and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "embed_batch_array",
            "category": "Text Embeddings",
            "name": "Batch Array Multi-Text Embedding",
            "method": "POST",
            "endpoint": "/v1/embeddings",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.embed_model,
                "input": ["First sentence vector", "Second sentence vector"],
            },
            "parameters_tested": ["input: array of strings"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "data" in b and len(json.loads(b).get("data", [])) == 2,
        })

        features.append({
            "id": "embed_dimensions",
            "category": "Text Embeddings",
            "name": "Custom Vector Dimension Truncation",
            "method": "POST",
            "endpoint": "/v1/embeddings",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.embed_model,
                "input": "Dimension truncation test vector",
                "dimensions": 256,
            },
            "parameters_tested": ["dimensions: 256"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and len(json.loads(b).get("data", [{}])[0].get("embedding", [])) == 256,
        })

        features.append({
            "id": "embed_encoding_format",
            "category": "Text Embeddings",
            "name": "Explicit Encoding Format",
            "method": "POST",
            "endpoint": "/v1/embeddings",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.embed_model,
                "input": "Encoding format validation",
                "encoding_format": "float",
            },
            "parameters_tested": ["encoding_format: float"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "embedding" in b,
        })

        # ---------------------------------------------------------------------
        # 5. Legacy Text Completions (/v1/completions)
        # ---------------------------------------------------------------------
        features.append({
            "id": "completions_basic",
            "category": "Legacy Completions",
            "name": "Legacy Prompt Text Completion",
            "method": "POST",
            "endpoint": "/v1/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "prompt": "1+1=",
                "max_tokens": 2,
            },
            "parameters_tested": ["model", "prompt: string", "max_tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "completions_stop_sequence",
            "category": "Legacy Completions",
            "name": "Completion Stop Sequences",
            "method": "POST",
            "endpoint": "/v1/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "prompt": "Count to 5: 1 2 3 4 5",
                "stop": ["4"],
                "max_tokens": 6,
            },
            "parameters_tested": ["stop: array"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        # ---------------------------------------------------------------------
        # 6. Models Catalog & Retrieval (/v1/models*)
        # ---------------------------------------------------------------------
        features.append({
            "id": "models_list",
            "category": "Models Catalog",
            "name": "Full Catalog List Retrieval",
            "method": "GET",
            "endpoint": "/v1/models",
            "extra_headers": {},
            "payload": None,
            "parameters_tested": ["GET /v1/models"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "data" in b and bool(h.get("x-nr-request-id")),
        })

        # The model id is URL-PATH-EMBEDDED here. A provider-prefixed id such as
        # `vendor/model-name` carries a `/`, and the wire contract names no
        # encoding for it, so the path would be ambiguous rather than wrong —
        # report that honestly instead of manufacturing a 404.
        detail_model = self.model
        detail_feature: Dict[str, Any] = {
            "id": "models_detail_retrieve",
            "category": "Models Catalog",
            "name": "Individual Model Detail Retrieval",
            "method": "GET",
            "endpoint": f"/v1/models/{detail_model}",
            "extra_headers": {},
            "payload": None,
            "parameters_tested": ["GET /v1/models/{model_id}"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and detail_model in b and bool(h.get("x-nr-request-id")),
        }
        if "/" in detail_model:
            detail_feature["unconfigured_detail"] = (
                f"the model under test is {detail_model!r}, whose id contains a '/'. It is embedded "
                "in the URL PATH here, and the wire contract names no encoding for a slashed model "
                "id, so the request would be ambiguous rather than a real retrieval. Point "
                f"{MODEL_ENV} at a model whose id carries no '/' to exercise this probe."
            )
        features.append(detail_feature)

        # ---------------------------------------------------------------------
        # 7. Fallback Routing (fallback_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "fallback_refused_target", "Fallback Routing", "Fallback Refused Target Model (V2)",
            ["payload: nrouter_fallbacks: [invalid-model]"],
            build_body(self.route, self.model, "test fallback", max_tokens=2,
                       nrouter_fallbacks=["unauthorized-model-not-in-acl"]),
            expected_status=400,
            validate=lambda s, h, b: s == 400 and "error" in b,
        ))

        # ---------------------------------------------------------------------
        # 8. Rate Limiting (ratelimit_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "ratelimit_preflight_slot", "Rate Limiting", "Rate Limit Preflight Slot Evaluation (V6)",
            ["tenant RPM/TPM slot verification"],
            build_body(self.route, self.model, "ratelimit slot ping", max_tokens=2),
            validate=lambda s, h, b: (s == 200 and bool(h.get("x-nr-request-id"))) or (s == 429 and "retry-after" in h),
        ))

        features.append(self._under_test(
            "ratelimit_concurrency_burst", "Rate Limiting", "Rate Limit Concurrency Burst (V6)",
            ["burst concurrency rate limit"],
            build_body(self.route, self.model, "ratelimit burst ping", max_tokens=2),
            validate=lambda s, h, b: s in (200, 429) and bool(h.get("x-nr-request-id")),
        ))

        # ---------------------------------------------------------------------
        # 9. Response Cache (cache_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "cache_ttl_control", "Response Cache", "Response Cache TTL Control Header",
            ["header: x-nr-cache-ttl: 60"],
            build_body(self.route, self.model, "ping", max_tokens=2),
            extra_headers={"x-nr-cache-ttl": "60"},
            validate=lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        ))

        features.append(self._under_test(
            "cache_bypass", "Response Cache", "Response Cache Explicit Bypass (V5)",
            ["payload: nrouter_cache: false"],
            build_body(self.route, self.model, "test cache bypass ping", max_tokens=2,
                       nrouter_cache=False),
            validate=lambda s, h, b: s == 200 and h.get("x-nr-response-cache") == "bypass" and bool(h.get("x-nr-request-id")),
        ))

        # ---------------------------------------------------------------------
        # 10. Context Ceilings (context_limit_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "context_limit_output", "Context Ceilings", "Context Output Ceiling Exceeded (V7)",
            [f"payload: {max_tokens_field(self.route)} > model ceiling"],
            build_body(self.route, self.model, "test limit", max_tokens=10000000),
            expected_status=400,
            validate=lambda s, h, b: s == 400 and ("output limit" in b.lower() or "input_too_large" in b or "error" in b),
        ))

        # ---------------------------------------------------------------------
        # 11. Guardrails (guardrail_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "guardrail_foreign_id", "Guardrails", "Foreign or Invalid Guardrail ID Refusal (V4)",
            ["payload: nrouter_guardrails: [uuid]"],
            build_body(self.route, self.model, "test guardrail", max_tokens=2,
                       nrouter_guardrails=["00000000-0000-0000-0000-000000000000"]),
            expected_status=400,
            validate=lambda s, h, b: s == 400 and "error" in b,
        ))

        # ---------------------------------------------------------------------
        # 12. Gateway Routing (routing_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "routing_strategy_header", "Gateway Routing", "Routing Strategy Selection Header",
            ["header: x-nr-routing-strategy: fallback"],
            build_body(self.route, self.model, "ping", max_tokens=2),
            extra_headers={"x-nr-routing-strategy": "fallback"},
            validate=lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        ))

        features.append(self._under_test(
            "routing_client_request_id", "Gateway Routing", "Client Trace Request Correlation ID",
            ["header: x-nr-client-request-id"],
            build_body(self.route, self.model, "ping", max_tokens=2),
            extra_headers={"x-nr-client-request-id": "test-client-trace-uuid-101"},
            validate=lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        ))

        # ---------------------------------------------------------------------
        # 13. Metering & FinOps (metering_)
        # ---------------------------------------------------------------------
        features.append(self._under_test(
            "metering_cost_headers", "Metering & FinOps", "Spend & Token Metering Headers (V8)",
            ["headers: x-nr-request-cost, x-nr-total-tokens"],
            build_body(self.route, self.model, "metering ping", max_tokens=2),
            validate=lambda s, h, b: s == 200 and ("x-nr-request-cost" in h or "x-nr-total-tokens" in h) and bool(h.get("x-nr-request-id")),
        ))

        # ---------------------------------------------------------------------
        # 14. Edge WAF, Security & Contract Refusals (waf_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "waf_unauthorized_token",
            "category": "Edge WAF & Refusals",
            "name": "Missing Auth Refusal (HTTP 401)",
            "method": "GET",
            "endpoint": "/v1/models",
            "no_auth": True,
            "extra_headers": {},
            "payload": None,
            "parameters_tested": ["Missing Authorization header"],
            "expected_status": 401,
            "validate": lambda s, h, b: s == 401 and "error" in b,
        })

        features.append({
            "id": "waf_unknown_model_not_found",
            "category": "Edge WAF & Refusals",
            "name": "Model Not Found Refusal (HTTP 404)",
            "method": "GET",
            "endpoint": "/v1/models/nonexistent-model-xyz-12345",
            "extra_headers": {},
            "payload": None,
            "parameters_tested": ["GET /v1/models/invalid-id"],
            "expected_status": 404,
            "validate": lambda s, h, b: s == 404 and "error" in b,
        })

        features.append(self._under_test(
            "waf_malformed_json", "Edge WAF & Refusals", "Malformed JSON Body Refusal (HTTP 400)",
            ["Malformed JSON payload syntax"],
            None,
            raw_payload='{"model": "test", "messages": [invalid json body',
            expected_status=400,
            validate=lambda s, h, b: s == 400 and ("error" in b or "bad request" in b.lower()),
        ))

        return features

    def _unrunnable_detail(self, feature: Dict[str, Any]) -> Optional[str]:
        """Why this probe cannot be made at all on the plane the operator named.

        Two absent preconditions, both decided BEFORE a request is sent:

        * the probe was handed a fixture it cannot use (a slashed model id in a
          URL path), which the feature itself supplies as `unconfigured_detail`;
        * the probe's PARAMETER does not exist on the wire under test. Sending
          `presence_penalty` to the Anthropic-shaped wire earns a 400 about the
          request body — a fact about this script, reported as a gateway defect.
        """
        if feature.get("unconfigured_detail"):
            return str(feature["unconfigured_detail"])
        if not feature.get("route_under_test"):
            return None
        wires = feature.get("wires", ALL_WIRES)
        wire = self._wire()
        if wire in wires:
            return None
        return (
            f"{', '.join(feature['parameters_tested'])} exists on the "
            f"{'/'.join(wires)} wire{'s' if len(wires) > 1 else ''}, and the route under test "
            f"({self.route}) speaks the {wire} wire, which has no such field. Nothing about the "
            f"gateway was tested. Point {ROUTE_ENV} at a route whose wire carries it "
            f"(current: {ROUTE_ENV}={self.route}, {MODEL_ENV}={self.model})."
        )

    def _scope_detail(self, feature: Dict[str, Any], status: int, headers: Dict[str, str]) -> Optional[str]:
        """NOT-CONFIGURED prose for a key whose route policy excludes this path.

        Deliberately as narrow as the shared guard: ONLY a 403 that NAMES
        `key_route_not_allowed`. A 403 for any other reason, and any other
        status, falls straight through to the probe's own assertions — the guard
        exists to stop a key policy being reported as a gateway defect, not to
        swallow denials.
        """
        detail = fixed_route_scope_detail(feature["endpoint"], status, headers)
        if detail and feature.get("route_under_test"):
            return (
                f"the gateway answered 403 with x-nr-auth-reason: key_route_not_allowed for "
                f"{feature['endpoint']} — the ROUTE UNDER TEST. This key's route policy does not "
                f"include it, so nothing about the gateway was tested. Point {ROUTE_ENV} at a "
                f"route the key allows (current: {ROUTE_ENV}={self.route}, {MODEL_ENV}={self.model})."
            )
        return detail

    def execute_feature(self, index: int, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single feature check via pure curl and record full response metadata."""
        unrunnable = self._unrunnable_detail(feature)
        if unrunnable:
            result = {
                "index": index,
                "id": feature["id"],
                "category": feature["category"],
                "name": feature["name"],
                "method": feature["method"],
                "endpoint": feature["endpoint"],
                "parameters_tested": feature["parameters_tested"],
                "curl_command": "(not executed)",
                "expected_status": feature["expected_status"],
                "http_status": 0,
                "latency_ms": 0.0,
                "request_id": "N/A",
                "cost_usd": None,
                "model_served": None,
                "response_snippet": "",
                "passed": False,
                "not_configured": True,
                "error": unrunnable,
            }
            self.results.append(result)
            return result

        clean_base = self.base_url.rstrip("/")
        if clean_base.endswith("/v1") and feature["endpoint"].startswith("/v1/"):
            clean_base = clean_base[:-3]
        endpoint = f"{clean_base}{feature['endpoint']}"
        curl_args: List[str] = []

        if not feature.get("no_auth"):
            curl_args.extend(self._auth_headers())

        for k, v in feature.get("extra_headers", {}).items():
            curl_args.extend(["-H", f"{k}: {v}"])

        payload_str: Optional[str] = None
        if "raw_payload" in feature:
            payload_str = feature["raw_payload"]
            curl_args.extend(["-d", payload_str])
        elif feature.get("payload") is not None:
            payload_str = json.dumps(feature["payload"])
            curl_args.extend(["-d", payload_str])

        curl_args.append(endpoint)

        # Build reproducible curl command string (with redacted token)
        safe_curl_cmd = f"curl -X {feature['method']} '{endpoint}'"
        if not feature.get("no_auth"):
            safe_curl_cmd += " -H 'Authorization: Bearer [REDACTED]'"
        for k, v in feature.get("extra_headers", {}).items():
            safe_curl_cmd += f" -H '{k}: {v}'"
        if payload_str is not None:
            # Escape single quotes for clean command representation
            safe_curl_cmd += f" -d '{payload_str}'"

        status, headers, body, latency = self.curl_fn(curl_args)

        validator = feature.get("validate", lambda s, h, b: s == feature["expected_status"])
        passed = False
        error_msg = None
        not_configured = False

        scope_detail = self._scope_detail(feature, status, headers)
        if scope_detail:
            not_configured = True
            error_msg = scope_detail
        else:
            try:
                passed = validator(status, headers, body)
                if not passed:
                    error_msg = f"HTTP {status} (expected {feature['expected_status']}): {sanitize(body[:150])}"
            except Exception as exc:
                passed = False
                error_msg = f"Validation exception: {exc}"

        req_id = headers.get("x-nr-request-id", "N/A")
        cost = parse_request_cost(headers)
        model_served = headers.get("x-nr-model")

        # Capture response snippet
        clean_snippet = re.sub(r"\s+", " ", sanitize(body[:160])).strip()

        result = {
            "index": index,
            "id": feature["id"],
            "category": feature["category"],
            "name": feature["name"],
            "method": feature["method"],
            "endpoint": feature["endpoint"],
            "parameters_tested": feature["parameters_tested"],
            "curl_command": safe_curl_cmd,
            "expected_status": feature["expected_status"],
            "http_status": status,
            "latency_ms": latency,
            "request_id": req_id,
            "cost_usd": cost,
            "model_served": model_served,
            "response_snippet": clean_snippet,
            "passed": passed,
            "not_configured": not_configured,
            "error": error_msg,
        }
        self.results.append(result)
        return result

    def run_suite(self, quick: bool = False, feature_filter: Optional[str] = None) -> Dict[str, Any]:
        """Run feature-specific curl checks, optionally filtered by feature prefix/name."""
        self.results.clear()
        features = self.define_features()

        if feature_filter:
            filt = feature_filter.strip().lower()
            features = [
                f for f in features
                if f["id"].lower().startswith(filt)
                or filt in f["id"].lower()
                or filt in f["category"].lower()
                or filt in f["name"].lower()
            ]
            if not features:
                print(f"Warning: No checks matched feature filter '{feature_filter}'", file=sys.stderr)

        # Quick mode runs representative sample of 10 checks when not filtered
        if quick and not feature_filter:
            features = features[:10]

        for idx, feat in enumerate(features, start=1):
            self.execute_feature(idx, feat)

        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        not_configured = sum(1 for r in self.results if r.get("not_configured"))
        # NOT-CONFIGURED is neither a pass nor a failure: the precondition for
        # the probe was provably absent, so it proved nothing either way. It is
        # counted and surfaced as PARTIAL — never quietly folded into `passed`.
        failed = total - passed - not_configured
        # The ONE verdict rule, shared by every module and by run_all.py: nothing
        # failed AND something was actually proven. A run of 40 NOT-CONFIGURED
        # probes and zero passes proved nothing and is not a pass. See
        # `_curl_common.suite_verdict`.
        verdict = suite_verdict(passed, failed, not_configured)

        # Group by category
        cat_summary: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            cat = r["category"]
            if cat not in cat_summary:
                cat_summary[cat] = {"total": 0, "passed": 0, "failed": 0, "not_configured": 0}
            cat_summary[cat]["total"] += 1
            if r["passed"]:
                cat_summary[cat]["passed"] += 1
            elif r.get("not_configured"):
                cat_summary[cat]["not_configured"] += 1
            else:
                cat_summary[cat]["failed"] += 1

        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": self.base_url,
            "route": self.route,
            "model": self.model,
            "wire": self._wire(),
            "total_features": total,
            "passed_features": passed,
            "failed_features": failed,
            "not_configured_features": not_configured,
            **verdict,
            "category_summary": cat_summary,
            "checks": self.results,
        }

    def render_markdown_summary(self, suite_result: Dict[str, Any]) -> str:
        """Render markdown summary for GitHub Step Summary."""
        if not suite_result["all_passed"]:
            status_badge = "🔴 **FAILED**"
        elif suite_result.get("partial"):
            status_badge = "🟡 **PARTIAL** (a precondition was absent — not release evidence)"
        else:
            status_badge = "🟢 **PASSED**"
        lines = [
            f"## ⚡ nRouter Pure-Curl Health Check: Feature Probes ({suite_result['total_features']} Checks)",
            "",
            f"**Overall Status**: {status_badge} | **Base URL**: `{suite_result['base_url']}`"
            f" | **Route**: `{suite_result.get('route', '')}` (`{suite_result.get('wire', '')}` wire)"
            f" | **Model**: `{suite_result.get('model', '')}`",
            f"- **Total Feature Probes**: `{suite_result['total_features']}`",
            f"- **Features Passed**: `{suite_result['passed_features']}`",
            f"- **Features Failed**: `{suite_result['failed_features']}`",
            f"- **Not-Configured**: `{suite_result.get('not_configured_features', 0)}`",
            "",
            "### Category Breakdown",
            "",
            "| Category | Probes | Passed | Failed | Not-Configured | Status |",
            "|---|---|---|---|---|---|",
        ]

        for cat, counts in suite_result["category_summary"].items():
            unconfigured = counts.get("not_configured", 0)
            if counts["failed"]:
                st = f"❌ {counts['failed']} Fail"
            elif unconfigured:
                st = f"🟡 {unconfigured} Not-Configured"
            else:
                st = "✅ Pass"
            lines.append(
                f"| `{cat}` | {counts['total']} | {counts['passed']} | {counts['failed']} | "
                f"{unconfigured} | {st} |"
            )

        lines.extend([
            "",
            "### Feature Commands & Captured Responses",
            "",
            "| # | Category & Name | Method & Endpoint | Parameters Tested | Status | HTTP | Latency | Request ID | Captured Response Snippet |",
            "|---|---|---|---|---|---|---|---|---|",
        ])

        for c in suite_result["checks"]:
            st = "🟡" if c.get("not_configured") else ("✅" if c["passed"] else "❌")
            req_id = c.get("request_id", "N/A")
            params = ", ".join(f"`{p}`" for p in c["parameters_tested"])
            snippet = c.get("response_snippet") or "OK"
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(
                f"| {c['index']} | **{c['name']}** (`{c['category']}`) | `{c['method']} {c['endpoint']}` | {params} | {st} | {c['http_status']} | {c['latency_ms']}ms | `{req_id}` | `{snippet}` |"
            )

        return "\n".join(lines)


def run_self_test() -> int:
    """Validate feature_curl offline using mocked HTTP responses for all 40 features.

    Every checker below names its route and model EXPLICITLY. A self-test that
    inherited NROUTER_HEALTH_ROUTE / NROUTER_HEALTH_MODEL from the shell would
    pass or fail according to the terminal it was run in, which is not a gate.
    """
    print("Running feature_curl.py --self-test (offline mode)...")

    def mock_curl(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
        endpoint = args[-1]
        headers: Dict[str, str] = {
            "x-nr-request-id": "req-mock-feat-12345",
            "content-type": "application/json",
            "x-nr-model": "mock-model",
            "x-nr-request-cost": "0.000005",
        }

        # Check for unauthorized probe
        has_auth = any("Authorization:" in arg for arg in args)
        if not has_auth:
            return 401, headers, '{"error": {"message": "Unauthorized", "type": "auth_error"}}', 5.0

        # Check for 404 nonexistent model probe
        if "nonexistent-model" in endpoint:
            return 404, headers, '{"error": {"message": "unknown model", "type": "gateway_error"}}', 8.0

        # Check for malformed JSON
        for i, arg in enumerate(args):
            if arg == "-d" and i + 1 < len(args):
                val = args[i + 1]
                if "invalid json" in val:
                    return 400, headers, '{"error": {"message": "Bad Request: malformed json", "type": "invalid_request_error"}}', 6.0

        # Check for context ceiling output limit
        for i, arg in enumerate(args):
            if arg == "-d" and i + 1 < len(args):
                val = args[i + 1]
                if "10000000" in val:
                    return 400, headers, '{"error": {"message": "the requested maximum output of 10000000 tokens is above the output limit", "type": "gateway_error"}}', 6.0
                if "00000000-0000-0000-0000-000000000000" in val:
                    return 400, headers, '{"error": {"message": "guardrail not found", "type": "gateway_error"}}', 7.0
                if "unauthorized-model-not-in-acl" in val:
                    return 400, headers, '{"error": {"message": "fallback target model unauthorized", "type": "gateway_error"}}', 7.0
                if '"nrouter_cache": false' in val or '"nrouter_cache":false' in val:
                    headers["x-nr-response-cache"] = "bypass"

        # Check for streaming
        is_stream = any('"stream": true' in arg or '"stream":true' in arg for arg in args)
        if is_stream:
            headers["content-type"] = "text/event-stream"
            stream_body = 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n'
            return 200, headers, stream_body, 12.0

        # Check for token counting
        if endpoint.endswith("/messages/count_tokens"):
            return 200, headers, '{"input_tokens": 12}', 10.0

        # Check for embeddings
        if endpoint.endswith("/embeddings"):
            body = json.dumps({
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.01] * 256},
                    {"object": "embedding", "index": 1, "embedding": [0.02] * 256},
                ],
                "model": "text-embedding-3-small",
            })
            return 200, headers, body, 15.0

        # Check for models list
        if endpoint.endswith("/models"):
            body = json.dumps({
                "object": "list",
                "data": [{"id": "claude-haiku-4-5-20251001", "object": "model"}],
            })
            return 200, headers, body, 8.0

        # Check for model detail
        if "/models/" in endpoint:
            body = json.dumps({
                "id": "claude-haiku-4-5-20251001",
                "object": "model",
                "nrouter_endpoints": ["/v1/messages", "/v1/messages/count_tokens"],
            })
            return 200, headers, body, 7.0

        # Check for Anthropic messages
        if endpoint.endswith("/messages"):
            body = json.dumps({
                "id": "msg_mock_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "OK"}],
            })
            return 200, headers, body, 20.0

        # Check for legacy completions (ensure not chat/completions)
        if endpoint.endswith("/v1/completions") or (endpoint.endswith("/completions") and "/chat/" not in endpoint):
            body = json.dumps({
                "id": "cmpl_mock_123",
                "object": "completion",
                "choices": [{"index": 0, "text": "2"}],
            })
            return 200, headers, body, 18.0

        # Default Chat Completions (/v1/chat/completions)
        body = json.dumps({
            "id": "chatcmpl_mock_123",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"status": "ok"}',
                    "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather"}}],
                },
            }],
            "logprobs": {"content": [{"token": "1"}]},
        })
        return 200, headers, body, 22.0

    checker = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/chat/completions",
        model="openai/gpt-4o-mini",
        messages_model="claude-haiku-4-5-20251001",
        curl_fn=mock_curl,
    )

    result = checker.run_suite(quick=False)
    assert result["all_passed"] is True, f"Self-test failed: {result['failed_features']} features failed"
    assert result["total_features"] == 42, f"Expected 42 feature probes, got {result['total_features']}"

    # Verify feature filtering by prefix (fallback_, ratelimit_, cache_)
    fallback_res = checker.run_suite(feature_filter="fallback_")
    assert fallback_res["all_passed"] is True, "fallback_ filter failed"
    assert fallback_res["total_features"] == 1, f"Expected 1 fallback check, got {fallback_res['total_features']}"
    assert all(c["id"].startswith("fallback_") for c in fallback_res["checks"])

    ratelimit_res = checker.run_suite(feature_filter="ratelimit_")
    assert ratelimit_res["all_passed"] is True, "ratelimit_ filter failed"
    assert ratelimit_res["total_features"] == 2, f"Expected 2 ratelimit checks, got {ratelimit_res['total_features']}"
    assert all(c["id"].startswith("ratelimit_") for c in ratelimit_res["checks"])

    cache_res = checker.run_suite(feature_filter="cache_")
    assert cache_res["all_passed"] is True, "cache_ filter failed"
    assert cache_res["total_features"] == 2, f"Expected 2 cache checks, got {cache_res['total_features']}"
    assert all(c["id"].startswith("cache_") for c in cache_res["checks"])

    # Verify markdown generation
    md = checker.render_markdown_summary(result)
    assert "nRouter Pure-Curl Health Check: Feature Probes" in md, "Missing title in markdown"
    assert "Category Breakdown" in md, "Missing category table in markdown"

    # Verify broken mock error detection
    def mock_broken(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
        return 500, {}, "Server Error", 5.0

    broken_checker = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/chat/completions",
        model="openai/gpt-4o-mini",
        curl_fn=mock_broken,
    )
    broken_result = broken_checker.run_suite(quick=True)
    assert broken_result["all_passed"] is False, "Broken mock should fail"

    # ---------------------------------------------------------------- D6
    # THE ROUTE AND MODEL UNDER TEST REACH EVERY INFERENCE-PATH CHECK.
    #
    # Before this, all 40 probes carried their own hardcoded route and model, so
    # a key scoped to `/messages` produced 30 × `403 key_route_not_allowed` —
    # facts about the KEY POLICY reported as gateway failures. Three things must
    # now hold, and this mock refuses everything except what such a key allows:
    #
    #   1. every inference-path probe asks the ROUTE UNDER TEST, on that wire's
    #      body shape, reading the completion where that wire puts it;
    #   2. a probe whose PARAMETER does not exist on that wire reports
    #      NOT-CONFIGURED naming the wire, not FAIL;
    #   3. a probe pinned to its own route by nature (embeddings, token
    #      counting, legacy completions) reports NOT-CONFIGURED naming THAT
    #      route when the key is scoped away from it — and every other probe
    #      still runs.
    scoped_paths: List[str] = []
    scoped_bodies: List[Tuple[str, str]] = []  # (endpoint, request body) pairs

    def mock_messages_only(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
        endpoint = args[-1]
        scoped_paths.append(endpoint)
        payload = ""
        for index, arg in enumerate(args):
            if arg == "-d" and index + 1 < len(args):
                payload = args[index + 1]
                scoped_bodies.append((endpoint, payload))
        headers: Dict[str, str] = {
            "x-nr-request-id": "req-scoped-feature",
            "content-type": "application/json",
            "x-nr-model": "claude-haiku-4-5-20251001",
            "x-nr-request-cost": "0.000005",
            "x-nr-total-tokens": "9",
        }
        if not any("Authorization:" in arg for arg in args):
            return 401, headers, '{"error": {"message": "Unauthorized", "type": "auth_error"}}', 4.0
        if "nonexistent-model" in endpoint:
            return 404, headers, '{"error": {"message": "unknown model", "type": "gateway_error"}}', 5.0
        if endpoint.endswith("/models"):
            return 200, headers, json.dumps({
                "object": "list",
                "data": [{"id": "claude-haiku-4-5-20251001", "object": "model"}],
            }), 6.0
        if "/models/" in endpoint:
            return 200, headers, json.dumps({
                "id": endpoint.split("/models/", 1)[1], "object": "model",
            }), 6.0
        if not endpoint.endswith("/messages"):
            # This key's route policy covers /v1/messages and nothing else.
            return 403, {"x-nr-auth-reason": "key_route_not_allowed"}, json.dumps({
                "error": {"message": "this API key is not allowed to use this route", "type": "gateway_error"}
            }), 5.0
        if "invalid json" in payload:
            return 400, headers, '{"error": {"message": "invalid request json", "type": "gateway_error"}}', 5.0
        if "10000000" in payload:
            return 400, headers, '{"error": {"message": "the requested maximum output is above the output limit", "type": "gateway_error"}}', 5.0
        if "00000000-0000-0000-0000-000000000000" in payload:
            return 400, headers, '{"error": {"message": "guardrail not found", "type": "gateway_error"}}', 5.0
        if "unauthorized-model-not-in-acl" in payload:
            return 400, headers, '{"error": {"message": "fallback target model unauthorized", "type": "gateway_error"}}', 5.0
        if '"nrouter_cache": false' in payload or '"nrouter_cache":false' in payload:
            headers["x-nr-response-cache"] = "bypass"
        if '"stream": true' in payload or '"stream":true' in payload:
            headers["content-type"] = "text/event-stream"
            return 200, headers, 'event: message_start\ndata: {"type":"message_start"}\n\n', 8.0
        served: Dict[str, Any] = {
            "id": "msg_scoped",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "OK"}],
        }
        if '"tools"' in payload:
            served["content"] = [{"type": "tool_use", "name": "get_weather", "input": {}}]
        return 200, headers, json.dumps(served), 14.0

    scoped_checker = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_messages_only,
    )
    scoped = scoped_checker.run_suite()
    rows = {row["id"]: row for row in scoped["checks"]}

    failing = [(row["id"], row.get("error")) for row in scoped["checks"] if row["passed"] is False and not row.get("not_configured")]
    assert not failing, (
        "a key scoped to the route under test must produce ZERO failures; these are "
        f"the module's own hardcoding reported as gateway defects: {failing}"
    )
    assert scoped["failed_features"] == 0, scoped["failed_features"]
    assert scoped["not_configured_features"] > 0, "nothing reported an absent precondition"
    assert scoped["partial"] is True, "a run carrying NOT-CONFIGURED rows is PARTIAL, never clean green"

    # 1. The inference-path probes reached the route under test, and NOTHING
    #    reached the route the module used to hardcode.
    assert any(path.endswith("/messages") for path in scoped_paths), scoped_paths[:5]
    assert not any(path.endswith("/chat/completions") for path in scoped_paths), (
        f"a probe still posted to the hardcoded route: "
        f"{[p for p in scoped_paths if p.endswith('/chat/completions')][:3]}"
    )
    assert rows["chat_basic"]["passed"] is True, rows["chat_basic"].get("error")
    assert rows["chat_basic"]["endpoint"] == "/v1/messages", rows["chat_basic"]["endpoint"]

    # ...on that wire's body shape. A chat-only field on the Anthropic-shaped
    # wire is a 400 about the request, not a test of the gateway.
    messages_bodies = [body for path, body in scoped_bodies if path.endswith("/messages")]
    assert messages_bodies, "nothing was posted to the route under test"
    for field in ('"presence_penalty"', '"frequency_penalty"', '"seed"', '"response_format"', '"logprobs"'):
        assert not any(field in body for body in messages_bodies), (
            f"{field} was sent on the messages wire, which does not accept it"
        )
    valid_docs = [json.loads(body) for body in messages_bodies if "invalid json" not in body]
    assert all(doc.get("model") == "claude-haiku-4-5-20251001" for doc in valid_docs), (
        "a probe sent a model the operator did not name"
    )
    # ...and the Anthropic wire's own required fields ARE present.
    assert all("max_tokens" in doc for doc in valid_docs), (
        "max_tokens is required on the Anthropic-shaped wire and was omitted"
    )

    # 2. A parameter that does not exist on this wire is an absent precondition.
    for chat_only in ("chat_json_mode", "chat_logprobs", "chat_sampling_params"):
        row = rows[chat_only]
        assert row.get("not_configured") is True, f"{chat_only}: {row.get('error')!r}"
        assert "messages" in (row.get("error") or ""), (
            f"{chat_only}'s detail must name the wire under test: {row.get('error')!r}"
        )

    # 3. A probe pinned to its own route reports NOT-CONFIGURED naming THAT
    #    route, and the rest of the suite still runs.
    for fixed_id, fixed_route in (
        ("embed_single_input", "/v1/embeddings"),
        ("tokens_messages", "/v1/messages/count_tokens"),
        ("completions_basic", "/v1/completions"),
    ):
        row = rows[fixed_id]
        assert row.get("not_configured") is True, f"{fixed_id}: {row.get('error')!r}"
        assert fixed_route in (row.get("error") or ""), (
            f"{fixed_id}'s detail must NAME the route it could not use: {row.get('error')!r}"
        )
    assert rows["messages_basic"]["passed"] is True, rows["messages_basic"].get("error")
    assert rows["models_list"]["passed"] is True, rows["models_list"].get("error")
    assert rows["waf_unauthorized_token"]["passed"] is True, rows["waf_unauthorized_token"].get("error")

    # The model detail probe asks for the model under test, not a constant.
    assert "claude-haiku-4-5-20251001" in rows["models_detail_retrieve"]["endpoint"], (
        rows["models_detail_retrieve"]["endpoint"]
    )

    # 4. A run in which EVERY probe was NOT-CONFIGURED proved NOTHING, so it must
    #    never read as passing. Under `all_passed = failed == 0` a 40/40
    #    NOT-CONFIGURED run with zero passes reported `all_passed: true`, and a CI
    #    gate reading that field waved it through as release evidence.
    absent_checker = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_messages_only,
    )

    def absent_feature(idx: int, feat: Dict[str, Any]) -> Dict[str, Any]:
        row = {
            "index": idx,
            "id": feat["id"],
            "name": feat["name"],
            "category": feat["category"],
            "endpoint": feat["endpoint"],
            "passed": False,
            "not_configured": True,
            "error": "precondition absent on this plane",
        }
        absent_checker.results.append(row)
        return row

    absent_checker.execute_feature = absent_feature  # type: ignore[method-assign]
    absent_suite = absent_checker.run_suite()
    assert absent_suite["total_features"] > 0, absent_suite
    assert absent_suite["passed_features"] == 0, absent_suite["passed_features"]
    assert absent_suite["not_configured_features"] == absent_suite["total_features"], absent_suite
    assert absent_suite["all_passed"] is False, (
        "an all-NOT-CONFIGURED run proved nothing and must not report all_passed"
    )
    assert absent_suite["proved_nothing"] is True, absent_suite["passed_features"]
    assert absent_suite["partial"] is True, absent_suite

    # ---- the guard is NARROW: only 403 + key_route_not_allowed -------------
    def mock_other_denial(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
        if args[-1].endswith("/embeddings"):
            return 403, {"x-nr-auth-reason": "key_model_not_allowed"}, json.dumps({
                "error": {"message": "this API key is not allowed to use this model", "type": "gateway_error"}
            }), 4.0
        return mock_messages_only(args, timeout_s)

    other = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_other_denial,
    ).run_suite(feature_filter="embed_")
    embed_row = other["checks"][0]
    assert embed_row["passed"] is False and not embed_row.get("not_configured"), (
        "a 403 naming a reason OTHER than key_route_not_allowed is a real finding "
        f"and must never be downgraded: {embed_row.get('error')!r}"
    )

    def mock_500_on_fixed(args: List[str], timeout_s: int = 35) -> Tuple[int, Dict[str, str], str, float]:
        if args[-1].endswith("/embeddings"):
            return 500, {}, "Internal Server Error", 4.0
        return mock_messages_only(args, timeout_s)

    five_hundred = FeatureCurlHealthCheck(
        base_url="https://mock.api.nrouter.ai/v1",
        api_key="sk-nrouter-mock-test-key",
        route="/messages",
        model="claude-haiku-4-5-20251001",
        curl_fn=mock_500_on_fixed,
    ).run_suite(feature_filter="embed_")
    assert five_hundred["checks"][0]["passed"] is False, "a 500 is a failure"
    assert not five_hundred["checks"][0].get("not_configured"), (
        "a 500 on a fixed route is a gateway failure, not an absent precondition"
    )

    # THE `--json` CONTRACT, driven through the REAL main(): a banner on stdout
    # above the document is what makes `--json > feature.json` unparseable.
    # The checker is substituted for a double, so nothing touches the network.
    class _StubChecker:
        def __init__(self, **_kwargs):
            self.route = "/chat/completions"
            self.model = resolve_model()
            self.messages_model = DEFAULT_MESSAGES_MODEL
            self.embed_model = DEFAULT_EMBED_MODEL

        def _wire(self):
            return wire_of(self.route)

        def run_suite(self, quick: bool = False, feature_filter: str = ""):
            return result

        def render_markdown_summary(self, _result):
            return "## stub"

    saved_class = globals()["FeatureCurlHealthCheck"]
    globals()["FeatureCurlHealthCheck"] = _StubChecker
    try:
        for argv in (
            ["feature_curl.py", "--json"],
            ["feature_curl.py"],
        ):
            main_json_stdout_contract_self_test(
                main,
                argv,
                "=== Starting nRouter Feature-by-Feature Pure-Curl Health Check ===",
                ("all_passed", "checks", "total_features"),
            )
    finally:
        globals()["FeatureCurlHealthCheck"] = saved_class

    # L2: DEFAULT_CHAT_MODEL and FeatureCurlHealthCheck must resolve model lazily
    old_model_env = os.environ.get(MODEL_ENV)
    try:
        os.environ[MODEL_ENV] = "test/lazy-override-model"
        lazy_checker = FeatureCurlHealthCheck(api_key="k")
        assert lazy_checker.model == "test/lazy-override-model", (
            f"Expected lazy model resolution 'test/lazy-override-model', got {lazy_checker.model!r}"
        )
    finally:
        if old_model_env is not None:
            os.environ[MODEL_ENV] = old_model_env
        else:
            os.environ.pop(MODEL_ENV, None)

    print("[PASS] feature_curl.py self-test passed cleanly (all 42 features & prefix filters verified offline).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Feature-by-Feature Pure-Curl Health Check")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    parser.add_argument("--quick", action="store_true", help="Run quick subset of 10 feature probes")
    parser.add_argument("--feature", default="", help="Filter checks by feature name or prefix (e.g. 'fallback_', 'ratelimit_', 'cache_', 'chat_')")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL), help="Gateway Base URL")
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""), help="nRouter API key")
    # The route and model UNDER TEST — the directory-wide pair. `--chat-model`
    # is this module's historical name for the model and still works; an
    # explicit `--model` wins over it.
    parser.add_argument(
        "--route",
        default="",
        help=f"Route under test, one of: {', '.join(ALLOWED_ROUTES)} (env {ROUTE_ENV})",
    )
    parser.add_argument("--model", default="", help=f"Model under test (env {MODEL_ENV})")
    parser.add_argument("--chat-model", default=os.environ.get("NROUTER_HEALTH_CHAT_MODEL", ""), help=f"Alias for --model (env {MODEL_ENV})")
    parser.add_argument("--messages-model", default=os.environ.get("NROUTER_HEALTH_MESSAGES_MODEL", DEFAULT_MESSAGES_MODEL), help="Model for the pinned /v1/messages probes")
    parser.add_argument("--embed-model", default=os.environ.get("NROUTER_HEALTH_EMBED_MODEL", DEFAULT_EMBED_MODEL), help="Model for the pinned /v1/embeddings probes")
    parser.add_argument("--step-summary", action="store_true", help="Write markdown summary to GITHUB_STEP_SUMMARY")
    parser.add_argument("--json", action="store_true", help="Output JSON results to stdout")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    # The key comes from --api-key or NROUTER_API_KEY, and nowhere else (see the
    # constructor above for why there is no credentials-file fallback).
    api_key = args.api_key
    if not api_key:
        print("ERROR: NROUTER_API_KEY is required to run live feature health checks.", file=sys.stderr)
        print("Set NROUTER_API_KEY or use --self-test for offline validation.", file=sys.stderr)
        return 1

    try:
        checker = FeatureCurlHealthCheck(
            base_url=args.base_url,
            api_key=api_key,
            chat_model=args.chat_model,
            messages_model=args.messages_model,
            embed_model=args.embed_model,
            route=args.route,
            model=args.model,
        )
    except ValueError as exc:  # an unsupported --route names itself
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # THE `--json` CONTRACT: with --json, stdout carries EXACTLY ONE JSON
    # document and nothing else, so `feature_curl.py --json > out.json` produces
    # a parseable file. The human report moves to stderr rather than being
    # discarded. Matches `emit_results` and the ten newer modules.
    report = sys.stderr if args.json else sys.stdout

    mode_label = f"Filtered by '{args.feature}'" if args.feature else ("Quick (10 features)" if args.quick else "Full (40 feature-specific curl commands)")
    print("=== Starting nRouter Feature-by-Feature Pure-Curl Health Check ===", file=report)
    print(f"Base URL:       {args.base_url}", file=report)
    print(f"Mode:           {mode_label}", file=report)
    print(f"Route:          {checker.route}  (wire: {checker._wire()})", file=report)
    print(f"Model:          {checker.model}", file=report)
    print(f"Messages Model: {checker.messages_model}   (pinned {FIXED_MESSAGES_ROUTE} probes)", file=report)
    print(f"Embed Model:    {checker.embed_model}   (pinned {FIXED_EMBEDDINGS_ROUTE} probes)", file=report)
    print("------------------------------------------------------------", file=report)

    result = checker.run_suite(quick=args.quick, feature_filter=args.feature)

    for check in result["checks"]:
        st = "NOT-CONFIGURED" if check.get("not_configured") else ("PASS" if check["passed"] else "FAIL")
        params_str = ", ".join(check["parameters_tested"])
        print(f"[{st}] #{check['index']} [{check['category']}] {check['name']} - HTTP {check['http_status']} ({check['latency_ms']}ms)", file=report)
        print(f"       Endpoint:    {check['method']} {check['endpoint']}", file=report)
        print(f"       Parameters:  {params_str}", file=report)
        print(f"       Response:    {check['response_snippet']}", file=report)
        if not check["passed"] and check.get("error"):
            label = "Absent:     " if check.get("not_configured") else "Error:      "
            print(f"       {label} {check['error']}", file=report)

    print("------------------------------------------------------------", file=report)
    print(f"Total Feature Probes: {result['total_features']}", file=report)
    print(f"Passed:               {result['passed_features']}", file=report)
    print(f"Failed:               {result['failed_features']}", file=report)
    print(f"Not-Configured:       {result['not_configured_features']}", file=report)
    overall = "PASS" if result["all_passed"] else "FAIL"
    if result["all_passed"] and result["partial"]:
        overall = "PARTIAL (a precondition was absent — this is not release evidence)"
    print(f"Overall Result:       {overall}", file=report)

    if args.step_summary:
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            md_content = checker.render_markdown_summary(result)
            try:
                with open(step_summary_path, "a") as f:
                    f.write("\n" + md_content + "\n")
                print(f"Appended feature markdown summary to GITHUB_STEP_SUMMARY ({step_summary_path})", file=report)
            except Exception as exc:
                print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {exc}", file=sys.stderr)

    if args.json:
        # The one and only thing this function writes to stdout.
        print(json.dumps(result, indent=2))

    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
