"""08. Structured Outputs — Enforcing JSON object responses.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

import json
from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        response = client.chat.completions.create(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[
                {"role": "system", "content": "You extract user information into JSON with keys: name, age, skills (list)."},
                {"role": "user", "content": "Alex is a 29-year-old engineer proficient in Rust and Python."}
            ],
            response_format={"type": "json_object"},
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)
        print("Structured JSON Result:")
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
