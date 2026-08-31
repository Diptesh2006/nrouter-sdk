"""07. Tool Calling (Function Calling) — Defining tools and executing function calls.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

import json
from nroutersdk import nRouter

# Mock function
def get_weather(location: str, unit: str = "celsius") -> str:
    return json.dumps({"location": location, "temperature": 22, "condition": "Sunny", "unit": unit})

def main() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather in a given city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    messages = [{"role": "user", "content": "What is the weather in San Francisco right now?"}]

    with nRouter() as client:
        response = client.chat.completions.create(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                print(f"Model requested tool: {tool_call.function.name}")
                args = json.loads(tool_call.function.arguments)
                print(f"Arguments: {args}")

                # Execute local tool
                if tool_call.function.name == "get_weather":
                    result = get_weather(**args)
                    print(f"Tool output: {result}")

                    # Feed tool output back to model
                    messages.append(msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

                    final_resp = client.chat.completions.create(
                        model="anthropic/claude-sonnet-4-5-20250929",
                        messages=messages,
                    )
                    print("\nFinal Model Response:")
                    print(final_resp.choices[0].message.content)
        else:
            print(msg.content)

if __name__ == "__main__":
    main()
