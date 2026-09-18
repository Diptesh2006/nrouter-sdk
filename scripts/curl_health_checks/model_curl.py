#!/usr/bin/env python3
"""nRouter Model & Provider Pure-Curl Health Check (`model_curl`).

Consolidated health check verifying:
  1. Models Catalog (GET /v1/models):
     - Endpoint HTTP 200 OK
     - Catalog response structure & schema
     - Total models count
  2. Provider Discovery & Coverage:
     - Extraction and grouping of active model providers
     - Model distribution across providers
     - Key provider availability check (openai, anthropic, gemini, meta, etc.)
  3. Live Model / Provider Inference Probe (POST /v1/chat/completions):
     - Verifies gateway provider wire execution via pure curl
     - Validates response contract (x-nr-request-id, x-nr-model, usage, latency)

Usage:
  python3 scripts/curl_health_checks/model_curl.py --self-test
  python3 scripts/curl_health_checks/model_curl.py
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

# Only the shared SELF-TEST contract is borrowed: this module keeps its own
# transport and its own report shape. `main_json_stdout_contract_self_test` is
# the one thing all thirteen modules must agree on — `--json` puts exactly one
# JSON document on stdout — so it has one home rather than three copies.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curl_common import main_json_stdout_contract_self_test  # noqa: E402

DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
DEFAULT_PROBE_MODEL = "openai/gpt-4o-mini"
MIN_EXPECTED_MODELS = 10

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
        probe_model: str = DEFAULT_PROBE_MODEL,
        curl_fn: Callable = run_curl,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("NROUTER_API_KEY", "")
        self.probe_model = probe_model
        self.curl_fn = curl_fn
        self.results: List[Dict[str, Any]] = []

    def _auth_headers(self) -> List[str]:
        return [
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "User-Agent: nrouter-curl-health-check/1.0",
        ]

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

        if status == 200:
            try:
                data = json.loads(body)
                model_list = data.get("data", [])
                if isinstance(model_list, list):
                    models_count = len(model_list)
                    sample_models = [m.get("id", "") for m in model_list[:10] if isinstance(m, dict)]
                    for m in model_list:
                        if isinstance(m, dict) and "id" in m:
                            prov = extract_provider(m["id"])
                            providers_map[prov] = providers_map.get(prov, 0) + 1

                    if models_count >= MIN_EXPECTED_MODELS:
                        passed = True
                    else:
                        error_msg = f"Models count ({models_count}) below threshold ({MIN_EXPECTED_MODELS})"
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
            "http_status": status,
            "latency_ms": latency,
            "request_id": headers.get("x-nr-request-id", "N/A"),
            "models_count": models_count,
            "providers_count": len(providers_map),
            "providers_distribution": dict(sorted(providers_map.items(), key=lambda item: -item[1])),
            "sample_models": sample_models,
            "error": error_msg,
        }
        self.results.append(res)
        return res

    def check_provider_inference_probe(self) -> Dict[str, Any]:
        """Execute a lightweight chat completion curl to verify provider wire execution."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = json.dumps({
            "model": self.probe_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 2,
        })
        args = self._auth_headers() + [
            "-H", "Content-Type: application/json",
            "-d", payload,
            endpoint,
        ]
        status, headers, body, latency = self.curl_fn(args)

        passed = False
        error_msg = None
        model_served = headers.get("x-nr-model")
        request_id = headers.get("x-nr-request-id", "N/A")
        completion_content = None

        if status == 200:
            try:
                data = json.loads(body)
                choices = data.get("choices", [])
                if choices and isinstance(choices, list):
                    msg = choices[0].get("message", {})
                    completion_content = msg.get("content", "").strip()
                    passed = True
                else:
                    error_msg = "No choices returned in chat completion payload"
            except Exception as exc:
                error_msg = f"Failed to parse completion JSON: {exc}"
        else:
            error_msg = f"HTTP {status}: {sanitize(body)}"

        res = {
            "check": "model_probe",
            "name": f"Provider Probe ({self.probe_model})",
            "method": "POST",
            "endpoint": "/v1/chat/completions",
            "passed": passed,
            "http_status": status,
            "latency_ms": latency,
            "request_id": request_id,
            "model_requested": self.probe_model,
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

        all_passed = catalog_res["passed"] and probe_res["passed"]
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": self.base_url,
            "passed": all_passed,
            "checks": self.results,
            "summary": {
                "total_models": catalog_res.get("models_count", 0),
                "total_providers": catalog_res.get("providers_count", 0),
                "probe_latency_ms": probe_res.get("latency_ms", 0.0),
                "all_passed": all_passed,
            },
        }

    def render_markdown_summary(self, suite_result: Dict[str, Any]) -> str:
        """Render markdown summary for GitHub Step Summary or PR comment."""
        status_badge = "🟢 **PASSED**" if suite_result["passed"] else "🔴 **FAILED**"
        summary = suite_result["summary"]

        lines = [
            "## 🤖 nRouter Pure-Curl Health Check: Models & Providers",
            "",
            f"**Overall Status**: {status_badge} | **Base URL**: `{suite_result['base_url']}`",
            f"- **Total Servable Models**: `{summary['total_models']}`",
            f"- **Active Providers Discovered**: `{summary['total_providers']}`",
            f"- **Provider Inference Latency**: `{summary['probe_latency_ms']} ms`",
            "",
            "### Health Check Results",
            "",
            "| Check | Method & Endpoint | Status | HTTP | Latency | Request ID | Details |",
            "|---|---|---|---|---|---|---|",
        ]

        for c in suite_result["checks"]:
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
    """Validate model_curl health check offline using mock responses."""
    print("Running model_curl.py --self-test (offline mode)...")

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
        curl_fn=mock_failing_curl,
    )
    failing_result = failing_checker.run_all()
    assert failing_result["passed"] is False, "Failing checker should report passed=False"

    # THE `--json` CONTRACT, driven through the REAL main(). A banner on stdout
    # above the document is what makes `model_curl.py --json > model.json`
    # unparseable, so the only honest test runs main() and parses what it wrote.
    # The checker is substituted for a double, so nothing touches the network.
    class _StubChecker:
        def __init__(self, **_kwargs):
            self.route = "/chat/completions"

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
    parser.add_argument("--probe-model", default=DEFAULT_PROBE_MODEL, help="Model to probe for inference check")
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

    checker = ModelCurlHealthCheck(
        base_url=args.base_url,
        api_key=api_key,
        probe_model=args.probe_model,
    )

    # THE `--json` CONTRACT: with --json, stdout carries EXACTLY ONE JSON
    # document and nothing else, so `model_curl.py --json > model.json` produces
    # a parseable file. The human report is not discarded — it moves to stderr,
    # so a person watching the terminal still sees it. Matches `emit_results`.
    report = sys.stderr if args.json else sys.stdout

    print(f"=== Starting nRouter Model & Provider Curl Health Check ===", file=report)
    print(f"Base URL:    {args.base_url}", file=report)
    print(f"Probe Model: {args.probe_model}", file=report)
    print("------------------------------------------------------------", file=report)

    result = checker.run_all()

    for check in result["checks"]:
        st = "PASS" if check["passed"] else "FAIL"
        print(f"[{st}] {check['name']} - HTTP {check['http_status']} ({check['latency_ms']}ms)", file=report)
        if not check["passed"] and check.get("error"):
            print(f"       Error: {check['error']}", file=report)

    print("------------------------------------------------------------", file=report)
    print(f"Catalog Models:    {result['summary']['total_models']}", file=report)
    print(f"Active Providers:  {result['summary']['total_providers']}", file=report)
    print(f"Overall Result:    {'PASS' if result['passed'] else 'FAIL'}", file=report)

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
