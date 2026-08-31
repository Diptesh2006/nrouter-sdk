"""03. Streaming — Real-time token streaming using Server-Sent Events (SSE).

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        print("Streaming response:")
        stream = client.chat.completions.create(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Write a short 4-line poem about routers."}],
            max_tokens=256,
            stream=True,
        )

        for chunk in stream:
            # Check choices before indexing (the final stream chunk may carry usage with empty choices)
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
        print("\n\nStream complete.")

if __name__ == "__main__":
    main()
