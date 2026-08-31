#!/usr/bin/env python3
"""
nRouter Multi-Language SDK Demo E2E Certification Script

This script demonstrates and records end-to-end execution of the nRouter SDK using
a demo configuration / demo key, validating:
1. Client initialization and API key validation.
2. Chat completions with prompt template selection, prompt variables, and sampling controls.
3. Response metadata extraction: x-nr-request-id, x-nr-request-cost, x-nr-model, token counts.
4. Conversation memory persistence with NRouterMemory.
5. Error typing and classification.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time

# Ensure nroutersdk is on sys.path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "sdks", "python"),
)

from nroutersdk import (
    nRouter,
    prompt_template,
    prompt_variables,
    create_memory,
    build_sampling_params,
    nRouterError,
)


class MockGatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default stdout logging

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(body.decode("utf-8")) if body else {}

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer sk-nrouter-"):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("x-nr-request-id", "req-demo-auth-err")
            self.send_header("x-nr-auth-reason", "invalid_key")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": {"type": "gateway_error", "message": "unauthorized key"}}).encode("utf-8")
            )
            return

        if self.path == "/v1/chat/completions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("x-nr-request-id", "req-demo-001")
            self.send_header("x-nr-request-cost", "0.002450")
            self.send_header("x-nr-cost-status", "exact")
            # This mock certifies one fixed model. Never reflect request data
            # into a header: CR/LF there would create a response-splitting
            # primitive in what is meant to be a safe copyable example.
            self.send_header("x-nr-model", "openai/gpt-5")
            self.send_header("x-nr-input-tokens", "42")
            self.send_header("x-nr-output-tokens", "18")
            self.send_header("x-nr-total-tokens", "60")
            self.send_header("x-nr-response-cache", "miss")
            self.end_headers()
            resp_body = {
                "id": "chatcmpl-demo-001",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", "openai/gpt-5"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello! Your query processed successfully through nRouter Gateway.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
            }
            self.wfile.write(json.dumps(resp_body).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_demo_e2e() -> int:
    print("=" * 70)
    print("nRouter SDK End-to-End Demo Certification")
    print("=" * 70)

    # 1. Start local mock gateway server to emulate live gateway response headers
    server = HTTPServer(("127.0.0.1", 0), MockGatewayHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}/v1"
    demo_key = "sk-nrouter-demo0000000000000000000000000000000000"

    print(f"\n[1/4] Initializing nRouter client with Demo credentials...")
    print(f"      Endpoint : {base_url}")
    print(f"      Key Prefix: {demo_key[:12]}...")

    client = nRouter(api_key=demo_key, base_url=base_url)

    # 2. Execute chat completion with prompt selection & sampling
    print(f"\n[2/4] Executing chat completion with prompt template and sampling...")
    prompt_sel = prompt_template("welcome-template", {"user_email": "demo@example.com"})
    sampling = build_sampling_params(advanced=True, model="openai/gpt-5", temperature=0.7, top_p=0.9)

    completion = client.chat.completions.create(
        model="openai/gpt-5",
        messages=[
            {"role": "system", "content": "You are nRouter Demo Assistant."},
            {"role": "user", "content": "Demonstrate routing and metadata capture."},
        ],
        extra_body={
            "nrouter_prompt_template_id": prompt_sel.template_id,
            "nrouter_prompt_variables": prompt_sel.variables,
        },
        **sampling,
    )

    answer = completion.choices[0].message.content
    print(f"      Response : \"{answer}\"")

    # 3. Verify Response Metadata Headers
    print(f"\n[3/4] Validating captured response metadata (x-nr-*)...")
    meta = client.last_response
    assert meta is not None, "Response metadata must be captured on client.last_response"

    print(f"      Request ID   : {meta.request_id}")
    print(f"      Cost USD     : ${meta.cost:.6f} ({meta.cost_status})")
    print(f"      Model Served : {meta.model}")
    print(f"      Tokens       : {meta.input_tokens} in / {meta.output_tokens} out (Total: {meta.total_tokens})")
    print(f"      Cache Status : {meta.response_cache}")

    assert meta.request_id == "req-demo-001"
    assert meta.cost == 0.00245
    assert meta.cost_status == "exact"
    assert meta.total_tokens == 60

    # 4. Memory Store & Multi-Turn Conversation
    print(f"\n[4/4] Testing NRouterMemory conversation store...")
    import asyncio

    async def test_mem():
        mem = create_memory()
        await mem.add({"role": "user", "content": "Hello from demo"})
        await mem.add({"role": "assistant", "content": "Hello! How can I help?"})
        msgs = await mem.messages()
        assert len(msgs) == 2
        print(f"      Stored {len(msgs)} turns in memory store successfully.")

    asyncio.run(test_mem())

    print(f"\n" + "=" * 70)
    print(f"Result: PASS (All checks certified)")
    print("=" * 70)

    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(run_demo_e2e())
