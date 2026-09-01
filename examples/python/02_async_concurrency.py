"""02. Async Concurrency — Running multiple requests concurrently with AsyncnRouter.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

import asyncio
from nroutersdk import AsyncnRouter

async def fetch_summary(client: AsyncnRouter, topic: str) -> str:
    response = await client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": f"Give a 1-sentence summary of: {topic}"}],
        max_tokens=100,
    )
    cost_str = f"${client.last_response.cost:.6f}" if client.last_response.cost is not None else "unpriced"
    return f"[{topic}] {response.choices[0].message.content.strip()} (Cost: {cost_str})"

async def main() -> None:
    topics = ["Distributed Systems", "WebAssembly", "CRDTs"]

    async with AsyncnRouter() as client:
        print(f"Fetching summaries for {len(topics)} topics concurrently...")
        tasks = [fetch_summary(client, topic) for topic in topics]
        results = await asyncio.gather(*tasks)

        print("\nResults:")
        for res in results:
            print(f" - {res}")

if __name__ == "__main__":
    asyncio.run(main())
