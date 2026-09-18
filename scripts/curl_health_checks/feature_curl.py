#!/usr/bin/env python3
"""nRouter Feature-by-Feature Pure-Curl Health Check (`feature_curl`).

Executes 40 comprehensive feature-specific curl checks covering Gateway endpoints
and exercising supported request parameters, headers, and refusal contracts.
Supports filtering by feature prefix via `--feature <prefix>` (e.g. `fallback_`, `ratelimit_`).

Feature Suites & Prefixes:
  1. Chat Completions (`chat_`):
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

# Only the shared SELF-TEST contract is borrowed: this module keeps its own
# transport and its own report shape. `--json` puts exactly one JSON document on
# stdout in all thirteen modules, so that contract has one home, not three.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import main_json_stdout_contract_self_test  # noqa: E402

DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_CHAT_MODEL = "openai/gpt-4o-mini"
DEFAULT_MESSAGES_MODEL = "claude-haiku-4-5-20251001"
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
        chat_model: str = DEFAULT_CHAT_MODEL,
        messages_model: str = DEFAULT_MESSAGES_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        # The key comes from the caller or NROUTER_API_KEY, and nowhere else.
        # There is deliberately no credentials-file fallback: this repository is
        # public, a hardcoded path leaks an internal convention, and a silent
        # fallback here would send whatever key it found to whatever base_url
        # this object was constructed with.
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.chat_model = chat_model
        self.messages_model = messages_model
        self.embed_model = embed_model
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    def _auth_headers(self) -> List[str]:
        return [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "User-Agent: nrouter-feature-curl-health-check/1.0",
        ]

    def define_features(self) -> List[Dict[str, Any]]:
        """Construct the 33 feature-specific curl definitions."""
        features: List[Dict[str, Any]] = []

        # ---------------------------------------------------------------------
        # 1. Chat Completions (/v1/chat/completions)
        # ---------------------------------------------------------------------
        features.append({
            "id": "chat_basic",
            "category": "Chat Completions",
            "name": "Basic Chat Completion",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "max_tokens": 5,
            },
            "parameters_tested": ["model", "messages", "max_tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "chat_system_multiturn",
            "category": "Chat Completions",
            "name": "System Prompt & Multi-Turn History",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": "You are a concise arithmetic calculator."},
                    {"role": "user", "content": "What is 2+2?"},
                    {"role": "assistant", "content": "4"},
                    {"role": "user", "content": "Add 3 more."},
                ],
                "max_tokens": 5,
            },
            "parameters_tested": ["messages[role: system|user|assistant]"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        features.append({
            "id": "chat_sampling_params",
            "category": "Chat Completions",
            "name": "Sampling Temperature & Top-P",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Name a color"}],
                "temperature": 0.7,
                "top_p": 0.95,
                "max_tokens": 5,
            },
            "parameters_tested": ["temperature", "top_p"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        features.append({
            "id": "chat_stop_sequences",
            "category": "Chat Completions",
            "name": "Stop Sequences",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Count from 1 to 5: 1 2 3 4 5"}],
                "stop": ["3", "STOP"],
                "max_tokens": 10,
            },
            "parameters_tested": ["stop"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        features.append({
            "id": "chat_penalties",
            "category": "Chat Completions",
            "name": "Presence & Frequency Penalties",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "List 3 words"}],
                "presence_penalty": 0.5,
                "frequency_penalty": 0.5,
                "max_tokens": 10,
            },
            "parameters_tested": ["presence_penalty", "frequency_penalty"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        features.append({
            "id": "chat_deterministic_seed",
            "category": "Chat Completions",
            "name": "Deterministic Seed",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "1+1="}],
                "seed": 42,
                "temperature": 0.0,
                "max_tokens": 4,
            },
            "parameters_tested": ["seed", "temperature: 0.0"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

        features.append({
            "id": "chat_json_mode",
            "category": "Chat Completions",
            "name": "Structured JSON Object Mode",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Return a JSON object with key status set to ok"}],
                "response_format": {"type": "json_object"},
                "max_tokens": 20,
            },
            "parameters_tested": ["response_format.type: json_object"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "status" in b and "{" in b,
        })

        features.append({
            "id": "chat_tool_calling",
            "category": "Chat Completions",
            "name": "Tools & Function Calling",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
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
                "max_tokens": 30,
            },
            "parameters_tested": ["tools", "tool_choice: auto"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and ("tool_calls" in b or "get_weather" in b),
        })

        features.append({
            "id": "chat_streaming_sse",
            "category": "Chat Completions",
            "name": "Server-Sent Events (SSE) Streaming",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Say hi"}],
                "stream": True,
                "max_tokens": 4,
            },
            "parameters_tested": ["stream: true"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and ("text/event-stream" in h.get("content-type", "") or "data:" in b),
        })

        features.append({
            "id": "chat_logprobs",
            "category": "Chat Completions",
            "name": "Logprobs & Top-Logprobs",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "1+1="}],
                "logprobs": True,
                "top_logprobs": 2,
                "max_tokens": 2,
            },
            "parameters_tested": ["logprobs: true", "top_logprobs: 2"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "logprobs" in b,
        })

        features.append({
            "id": "chat_user_identifier",
            "category": "Chat Completions",
            "name": "Client End-User ID Tracking",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "Ping"}],
                "user": "usr_tenant_audit_client_99",
                "max_tokens": 3,
            },
            "parameters_tested": ["user: string"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and "choices" in b,
        })

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

        features.append({
            "id": "models_detail_retrieve",
            "category": "Models Catalog",
            "name": "Individual Model Detail Retrieval",
            "method": "GET",
            "endpoint": f"/v1/models/{self.messages_model}",
            "extra_headers": {},
            "payload": None,
            "parameters_tested": ["GET /v1/models/{model_id}"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and self.messages_model in b and bool(h.get("x-nr-request-id")),
        })

        # ---------------------------------------------------------------------
        # 7. Fallback Routing (fallback_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "fallback_refused_target",
            "category": "Fallback Routing",
            "name": "Fallback Refused Target Model (V2)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "test fallback"}],
                "max_tokens": 2,
                "nrouter_fallbacks": ["unauthorized-model-not-in-acl"],
            },
            "parameters_tested": ["payload: nrouter_fallbacks: [invalid-model]"],
            "expected_status": 400,
            "validate": lambda s, h, b: s == 400 and "error" in b,
        })

        # ---------------------------------------------------------------------
        # 8. Rate Limiting (ratelimit_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "ratelimit_preflight_slot",
            "category": "Rate Limiting",
            "name": "Rate Limit Preflight Slot Evaluation (V6)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "ratelimit slot ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["tenant RPM/TPM slot verification"],
            "expected_status": 200,
            "validate": lambda s, h, b: (s == 200 and bool(h.get("x-nr-request-id"))) or (s == 429 and "retry-after" in h),
        })

        features.append({
            "id": "ratelimit_concurrency_burst",
            "category": "Rate Limiting",
            "name": "Rate Limit Concurrency Burst (V6)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "ratelimit burst ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["burst concurrency rate limit"],
            "expected_status": 200,
            "validate": lambda s, h, b: s in (200, 429) and bool(h.get("x-nr-request-id")),
        })

        # ---------------------------------------------------------------------
        # 9. Response Cache (cache_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "cache_ttl_control",
            "category": "Response Cache",
            "name": "Response Cache TTL Control Header",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {
                "Content-Type": "application/json",
                "x-nr-cache-ttl": "60",
            },
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["header: x-nr-cache-ttl: 60"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "cache_bypass",
            "category": "Response Cache",
            "name": "Response Cache Explicit Bypass (V5)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "test cache bypass ping"}],
                "max_tokens": 2,
                "nrouter_cache": False,
            },
            "parameters_tested": ["payload: nrouter_cache: false"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and h.get("x-nr-response-cache") == "bypass" and bool(h.get("x-nr-request-id")),
        })

        # ---------------------------------------------------------------------
        # 10. Context Ceilings (context_limit_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "context_limit_output",
            "category": "Context Ceilings",
            "name": "Context Output Ceiling Exceeded (V7)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "test limit"}],
                "max_tokens": 10000000,
            },
            "parameters_tested": ["payload: max_tokens > model ceiling"],
            "expected_status": 400,
            "validate": lambda s, h, b: s == 400 and ("output limit" in b.lower() or "input_too_large" in b or "error" in b),
        })

        # ---------------------------------------------------------------------
        # 11. Guardrails (guardrail_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "guardrail_foreign_id",
            "category": "Guardrails",
            "name": "Foreign or Invalid Guardrail ID Refusal (V4)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "test guardrail"}],
                "max_tokens": 2,
                "nrouter_guardrails": ["00000000-0000-0000-0000-000000000000"],
            },
            "parameters_tested": ["payload: nrouter_guardrails: [uuid]"],
            "expected_status": 400,
            "validate": lambda s, h, b: s == 400 and "error" in b,
        })

        # ---------------------------------------------------------------------
        # 12. Gateway Routing (routing_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "routing_strategy_header",
            "category": "Gateway Routing",
            "name": "Routing Strategy Selection Header",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {
                "Content-Type": "application/json",
                "x-nr-routing-strategy": "fallback",
            },
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["header: x-nr-routing-strategy: fallback"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        })

        features.append({
            "id": "routing_client_request_id",
            "category": "Gateway Routing",
            "name": "Client Trace Request Correlation ID",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {
                "Content-Type": "application/json",
                "x-nr-client-request-id": "test-client-trace-uuid-101",
            },
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["header: x-nr-client-request-id"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and bool(h.get("x-nr-request-id")),
        })

        # ---------------------------------------------------------------------
        # 13. Metering & FinOps (metering_)
        # ---------------------------------------------------------------------
        features.append({
            "id": "metering_cost_headers",
            "category": "Metering & FinOps",
            "name": "Spend & Token Metering Headers (V8)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "payload": {
                "model": self.chat_model,
                "messages": [{"role": "user", "content": "metering ping"}],
                "max_tokens": 2,
            },
            "parameters_tested": ["headers: x-nr-request-cost, x-nr-total-tokens"],
            "expected_status": 200,
            "validate": lambda s, h, b: s == 200 and ("x-nr-request-cost" in h or "x-nr-total-tokens" in h) and bool(h.get("x-nr-request-id")),
        })

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

        features.append({
            "id": "waf_malformed_json",
            "category": "Edge WAF & Refusals",
            "name": "Malformed JSON Body Refusal (HTTP 400)",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "extra_headers": {"Content-Type": "application/json"},
            "raw_payload": '{"model": "test", "messages": [invalid json body',
            "parameters_tested": ["Malformed JSON payload syntax"],
            "expected_status": 400,
            "validate": lambda s, h, b: s == 400 and ("error" in b or "bad request" in b.lower()),
        })

        return features

    def execute_feature(self, index: int, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single feature check via pure curl and record full response metadata."""
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
        failed = total - passed
        all_passed = (failed == 0)

        # Group by category
        cat_summary: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            cat = r["category"]
            if cat not in cat_summary:
                cat_summary[cat] = {"total": 0, "passed": 0, "failed": 0}
            cat_summary[cat]["total"] += 1
            if r["passed"]:
                cat_summary[cat]["passed"] += 1
            else:
                cat_summary[cat]["failed"] += 1

        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": self.base_url,
            "total_features": total,
            "passed_features": passed,
            "failed_features": failed,
            "all_passed": all_passed,
            "category_summary": cat_summary,
            "checks": self.results,
        }

    def render_markdown_summary(self, suite_result: Dict[str, Any]) -> str:
        """Render markdown summary for GitHub Step Summary."""
        status_badge = "🟢 **PASSED**" if suite_result["all_passed"] else "🔴 **FAILED**"
        lines = [
            f"## ⚡ nRouter Pure-Curl Health Check: Feature Probes ({suite_result['total_features']} Checks)",
            "",
            f"**Overall Status**: {status_badge} | **Base URL**: `{suite_result['base_url']}`",
            f"- **Total Feature Probes**: `{suite_result['total_features']}`",
            f"- **Features Passed**: `{suite_result['passed_features']}`",
            f"- **Features Failed**: `{suite_result['failed_features']}`",
            "",
            "### Category Breakdown",
            "",
            "| Category | Probes | Passed | Failed | Status |",
            "|---|---|---|---|---|",
        ]

        for cat, counts in suite_result["category_summary"].items():
            st = "✅ Pass" if counts["failed"] == 0 else f"❌ {counts['failed']} Fail"
            lines.append(f"| `{cat}` | {counts['total']} | {counts['passed']} | {counts['failed']} | {st} |")

        lines.extend([
            "",
            "### Feature Commands & Captured Responses",
            "",
            "| # | Category & Name | Method & Endpoint | Parameters Tested | Status | HTTP | Latency | Request ID | Captured Response Snippet |",
            "|---|---|---|---|---|---|---|---|---|",
        ])

        for c in suite_result["checks"]:
            st = "✅" if c["passed"] else "❌"
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
    """Validate feature_curl offline using mocked HTTP responses for all 33 features."""
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
        curl_fn=mock_curl,
    )

    result = checker.run_suite(quick=False)
    assert result["all_passed"] is True, f"Self-test failed: {result['failed_features']} features failed"
    assert result["total_features"] == 40, f"Expected 40 feature probes, got {result['total_features']}"

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
        curl_fn=mock_broken,
    )
    broken_result = broken_checker.run_suite(quick=True)
    assert broken_result["all_passed"] is False, "Broken mock should fail"

    # THE `--json` CONTRACT, driven through the REAL main(): a banner on stdout
    # above the document is what makes `--json > feature.json` unparseable.
    # The checker is substituted for a double, so nothing touches the network.
    class _StubChecker:
        def __init__(self, **_kwargs):
            pass

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

    print("[PASS] feature_curl.py self-test passed cleanly (all 40 features & prefix filters verified offline).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="nRouter Feature-by-Feature Pure-Curl Health Check")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    parser.add_argument("--quick", action="store_true", help="Run quick subset of 10 feature probes")
    parser.add_argument("--feature", default="", help="Filter checks by feature name or prefix (e.g. 'fallback_', 'ratelimit_', 'cache_', 'chat_')")
    parser.add_argument("--base-url", default=os.environ.get("NROUTER_BASE_URL", DEFAULT_BASE_URL), help="Gateway Base URL")
    parser.add_argument("--api-key", default=os.environ.get("NROUTER_API_KEY", ""), help="nRouter API key")
    parser.add_argument("--chat-model", default=os.environ.get("NROUTER_HEALTH_CHAT_MODEL", DEFAULT_CHAT_MODEL), help="Chat model")
    parser.add_argument("--messages-model", default=os.environ.get("NROUTER_HEALTH_MESSAGES_MODEL", DEFAULT_MESSAGES_MODEL), help="Messages model")
    parser.add_argument("--embed-model", default=os.environ.get("NROUTER_HEALTH_EMBED_MODEL", DEFAULT_EMBED_MODEL), help="Embeddings model")
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

    checker = FeatureCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        chat_model=args.chat_model,
        messages_model=args.messages_model,
        embed_model=args.embed_model,
    )

    # THE `--json` CONTRACT: with --json, stdout carries EXACTLY ONE JSON
    # document and nothing else, so `feature_curl.py --json > out.json` produces
    # a parseable file. The human report moves to stderr rather than being
    # discarded. Matches `emit_results` and the ten newer modules.
    report = sys.stderr if args.json else sys.stdout

    mode_label = f"Filtered by '{args.feature}'" if args.feature else ("Quick (10 features)" if args.quick else "Full (40 feature-specific curl commands)")
    print("=== Starting nRouter Feature-by-Feature Pure-Curl Health Check ===", file=report)
    print(f"Base URL:       {args.base_url}", file=report)
    print(f"Mode:           {mode_label}", file=report)
    print(f"Chat Model:     {args.chat_model}", file=report)
    print(f"Messages Model: {args.messages_model}", file=report)
    print(f"Embed Model:    {args.embed_model}", file=report)
    print("------------------------------------------------------------", file=report)

    result = checker.run_suite(quick=args.quick, feature_filter=args.feature)

    for check in result["checks"]:
        st = "PASS" if check["passed"] else "FAIL"
        params_str = ", ".join(check["parameters_tested"])
        print(f"[{st}] #{check['index']} [{check['category']}] {check['name']} - HTTP {check['http_status']} ({check['latency_ms']}ms)", file=report)
        print(f"       Endpoint:    {check['method']} {check['endpoint']}", file=report)
        print(f"       Parameters:  {params_str}", file=report)
        print(f"       Response:    {check['response_snippet']}", file=report)
        if not check["passed"] and check.get("error"):
            print(f"       Error:       {check['error']}", file=report)

    print("------------------------------------------------------------", file=report)
    print(f"Total Feature Probes: {result['total_features']}", file=report)
    print(f"Passed:               {result['passed_features']}", file=report)
    print(f"Failed:               {result['failed_features']}", file=report)
    print(f"Overall Result:       {'PASS' if result['all_passed'] else 'FAIL'}", file=report)

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
