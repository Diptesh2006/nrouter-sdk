# nRouter Python hello world
#
# pip install nrouter-sdk
# set NROUTER_API_KEY before running.

from nroutersdk import nRouter


def main() -> None:
    client = nRouter()  # reads NROUTER_API_KEY from environment
    # A Smart Router alias activates its configured strategy and fallback
    # chain; a concrete model id pins the request to that model.
    import os
    model = os.getenv("NROUTER_MODEL", "claude-sonnet-4-5-20250929")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with one short sentence saying hello from nRouter."}],
        max_tokens=32,
    )

    print(response.choices[0].message.content)
    if client.last_response:
        print(f"Request ID: {client.last_response.request_id}")
        print(f"Model: {client.last_response.model}")
        print(f"Cost: ${client.last_response.cost}" if client.last_response.cost is not None else "Cost: unpriced")


if __name__ == "__main__":
    main()
