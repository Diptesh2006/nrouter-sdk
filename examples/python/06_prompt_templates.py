"""06. Prompt Templates — Using dashboard-managed prompt templates & variable injection.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter, prompt_template

def main() -> None:
    with nRouter() as client:
        # Build extra body with managed template ID & variable substitution
        extra_body = prompt_template(
            template_id="customer_greeting_v1",
            variables={"customer": "Acme Corp", "tier": "Enterprise"}
        )

        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Draft an onboarding welcome message."}],
            extra_body=extra_body,
        )

        print(response.choices[0].message.content)

if __name__ == "__main__":
    main()
