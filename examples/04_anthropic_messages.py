"""04. Anthropic Messages API — Using Anthropic format on the same API key.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        # Pre-call token count (Free route, carries no cost)
        token_count = client.messages.count_tokens(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Analyze system performance across clusters."}],
        )
        print(f"Pre-call token count: {token_count.get('input_tokens')} tokens\n")

        # Create message using native Anthropic Messages wire format
        message = client.messages.create(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Analyze system performance across clusters."}],
            max_tokens=300,
        )

        print("Response Text:")
        print(message["content"][0]["text"])

        meta = client.last_response
        print(f"\nRequest ID: {meta.request_id} | Cost: ${meta.cost}")

if __name__ == "__main__":
    main()
