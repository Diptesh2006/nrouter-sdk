"""Google Gemini 2.0 Flash Chat Completion Example.

Demonstrates:
1. Setting and reading NROUTER_API_KEY
2. Initializing the nRouter Python client
3. Calling chat completion on Google Gemini 2.0 Flash (google/gemini-2.0-flash)
4. Fast response latency and exact list-price FinOps tracking via client.last_response
5. Referencing Gemini 2.0 Flash Lite and Gemini 1.5 model family constants

Usage:
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
    python sdks/python/examples/gemini_flash_chat.py
"""

from __future__ import annotations

import os
import sys

# Ensure local package is discoverable when run directly from directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nroutersdk import (
    MODEL_GOOGLE_GEMINI_2_0_FLASH,
    MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE,
    MODEL_GOOGLE_GEMINI_1_5_PRO_002,
    MODEL_GOOGLE_GEMINI_1_5_FLASH_002,
    nRouter,
)


def main() -> None:
    # 1. Setting and reading NROUTER_API_KEY
    api_key = os.environ.get("NROUTER_API_KEY")
    if not api_key:
        print("Notice: NROUTER_API_KEY not found in environment.")
        print("To run against the live gateway: export NROUTER_API_KEY='sk-nrouter-...'\n")

    print("======================================================")
    print(f"Model: {MODEL_GOOGLE_GEMINI_2_0_FLASH}")
    print("Available Gemini 2.0 / 1.5 Family:")
    print(f" - {MODEL_GOOGLE_GEMINI_2_0_FLASH}")
    print(f" - {MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE}")
    print(f" - {MODEL_GOOGLE_GEMINI_1_5_PRO_002}")
    print(f" - {MODEL_GOOGLE_GEMINI_1_5_FLASH_002}")
    print("======================================================\n")

    # 2. Initializing nRouter client (reads NROUTER_API_KEY automatically if unset)
    with nRouter(
        api_key=api_key or "sk-nrouter-demo-virtual-key",
        base_url=os.environ.get("NROUTER_BASE_URL", "https://api.nrouter.ai/v1"),
    ) as client:
        try:
            # 3. Calling chat completion on Google Gemini 2.0 Flash
            print("Sending chat request to Google Gemini 2.0 Flash...")
            response = client.chat.completions.create(
                model=MODEL_GOOGLE_GEMINI_2_0_FLASH,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise engineering assistant.",
                    },
                    {
                        "role": "user",
                        "content": "Explain vector databases vs traditional relational databases in two short bullet points.",
                    },
                ],
                temperature=0.2,
                max_tokens=256,
            )

            assistant_reply = response.choices[0].message.content or ""
            print("\n--- Assistant Response ---")
            print(assistant_reply)

            # 4. Inspect automatic response metadata & FinOps tracking
            meta = client.last_response
            if meta:
                print("\n--- Request Observability & FinOps ---")
                print(f"Request ID:      {meta.request_id}")
                print(f"Served Model:    {meta.model or MODEL_GOOGLE_GEMINI_2_0_FLASH}")
                print(f"Gateway Latency: {meta.latency_ms} ms")
                print(
                    f"Tokens:          {meta.input_tokens} prompt + "
                    f"{meta.output_tokens} completion = {meta.total_tokens} total"
                )
                if meta.cost_status == "exact" and meta.cost is not None:
                    print(f"Settled Spend:   ${meta.cost:.6f} USD (Exact list price, 0% markup)")
                else:
                    print(f"Cost Status:     {meta.cost_status}")
        except Exception as exc:
            print(f"Inference error: {exc}")


if __name__ == "__main__":
    main()
