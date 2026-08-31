"""11. Embeddings — Generating vector embeddings.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=["nRouter unified LLM gateway", "Vector search in databases"],
        )

        for i, item in enumerate(response.data):
            print(f"Vector {i+1} dimensions: {len(item.embedding)} (first 5: {item.embedding[:5]})")

if __name__ == "__main__":
    main()
