"""TypeSafe Jev System One Decision Model Example.

Demonstrates:
1. Setting and reading NROUTER_API_KEY
2. Initializing the nRouter Python client
3. Calling System One rapid classification/decision on TypeSafe Jev (typesafe/jev)
4. Structured JSON output for deterministic policy decision-making
5. Low-latency performance and exact cost settlement via client.last_response

Usage:
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
    python sdks/python/examples/typesafe_system_one.py
"""

from __future__ import annotations

import json
import os
import sys

# Ensure local package is discoverable when run directly from directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nroutersdk import MODEL_TYPESAFE_JEV, nRouter


def main() -> None:
    # 1. Setting and reading NROUTER_API_KEY
    api_key = os.environ.get("NROUTER_API_KEY")
    if not api_key:
        print("Set NROUTER_API_KEY before running this live example.", file=sys.stderr)
        raise SystemExit(1)

    print("======================================================")
    print(f"Model: {MODEL_TYPESAFE_JEV} (TypeSafe AI Jev System One)")
    print("======================================================\n")

    incoming_ticket = {
        "ticket_id": "TCK-8821",
        "customer_tier": "enterprise",
        "subject": "Production API returning 500 on all payment settlement endpoints",
        "affected_regions": ["us-east-1", "eu-west-1"],
        "reported_severity": "urgent",
    }

    print("Incoming support ticket for automated triage & routing:")
    print(json.dumps(incoming_ticket, indent=2))

    # 2. Initializing nRouter client (reads NROUTER_API_KEY automatically if unset)
    with nRouter(
        api_key=api_key,
        base_url=os.environ.get("NROUTER_BASE_URL", "https://api.nrouter.ai/v1"),
    ) as client:
        system_prompt = (
            "You are TypeSafe Jev System One, an ultra-fast deterministic incident triage classifier.\n"
            "Analyze the ticket and output JSON with schema:\n"
            "{\n"
            '  "priority": "P0" | "P1" | "P2" | "P3",\n'
            '  "assigned_queue": "SRE_ONCALL" | "BILLING_ENG" | "GENERAL_SUPPORT",\n'
            '  "sla_minutes": number,\n'
            '  "confidence": number,\n'
            '  "triage_summary": string\n'
            "}\n"
            "Output raw JSON only."
        )

        try:
            # 3. Calling System One classification/decision on TypeSafe Jev
            print("\nSending triage request to TypeSafe Jev System One...")
            response = client.chat.completions.create(
                model=MODEL_TYPESAFE_JEV,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Triage ticket: {json.dumps(incoming_ticket)}"},
                ],
                temperature=0.0,  # Deterministic System One classification
                max_tokens=256,
                response_format={"type": "json_object"},
            )

            raw_text = response.choices[0].message.content or "{}"
            decision = json.loads(raw_text)

            # 4. Output classification & decision results
            print("\n--- System One Triage Decision ---")
            print(f"Priority:       {decision.get('priority')}")
            print(f"Assigned Queue: {decision.get('assigned_queue')}")
            print(f"SLA Target:     {decision.get('sla_minutes')} minutes")
            print(f"Confidence:     {decision.get('confidence')}")
            print(f"Summary:        {decision.get('triage_summary')}")

            # 5. Inspect automatic response metadata & FinOps tracking
            meta = client.last_response
            if meta:
                print("\n--- Request Observability & FinOps ---")
                print(f"Request ID:      {meta.request_id}")
                print(f"Served Model:    {meta.model or MODEL_TYPESAFE_JEV}")
                print(f"Gateway Latency: {meta.latency_ms} ms")
                print(
                    f"Tokens:          {meta.input_tokens} prompt + "
                    f"{meta.output_tokens} completion = {meta.total_tokens} total"
                )
                if meta.cost_status == "exact" and meta.cost is not None:
                    print(f"Settled Spend:   ${meta.cost:.6f} USD")
                else:
                    print(f"Cost Status:     {meta.cost_status}")
        except Exception as exc:
            print(f"Inference error: {exc}")


if __name__ == "__main__":
    main()
