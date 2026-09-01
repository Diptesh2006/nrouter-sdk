"""01. Quickstart — Basic chat completions with nRouter.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

import os
from nroutersdk import nRouter

def main() -> None:
    # Client automatically reads NROUTER_API_KEY from environment
    with nRouter() as client:
        print("Sending chat completion request...")
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": "You are a concise AI assistant."},
                {"role": "user", "content": "Explain quantum computing in one sentence."},
            ],
            max_tokens=256,
        )

        # Output text
        print("\nAssistant Response:")
        print(response.choices[0].message.content)

        # Inspect automatic metadata & cost
        meta = client.last_response
        print("\n--- Request Metadata ---")
        print(f"Request ID:   {meta.request_id}")
        print(f"Served Model: {meta.model}")
        print(f"Tokens:       {meta.input_tokens} in / {meta.output_tokens} out (Total: {meta.total_tokens})")
        if meta.cost_status == "exact":
            print(f"Cost:         ${meta.cost:.6f}")
        else:
            print(f"Cost:         unpriced ({meta.cost_status})")

if __name__ == "__main__":
    main()
