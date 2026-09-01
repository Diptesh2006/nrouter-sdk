"""10. Conversation Memory — Client-side multi-turn memory without leaking tenancy.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter, create_memory

def main() -> None:
    memory = create_memory()
    with nRouter() as client:
        # Turn 1
        memory.add({"role": "user", "content": "Hi! My favorite programming language is Rust."})
        resp1 = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=memory.messages(),
        )
        memory.add({"role": "assistant", "content": resp1.choices[0].message.content})
        print(f"Assistant: {resp1.choices[0].message.content}\n")

        # Turn 2 (Model recalls context)
        memory.add({"role": "user", "content": "What is my favorite language and why is it popular?"})
        resp2 = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=memory.messages(),
        )
        print(f"Assistant: {resp2.choices[0].message.content}")

if __name__ == "__main__":
    main()
