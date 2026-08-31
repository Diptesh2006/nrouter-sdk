"""09. Error Handling & Resilience — Catching typed exceptions and retry strategies.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import (
    nRouter,
    nRouterGuardrailBlockedError,
    nRouterCreditError,
    nRouterRateLimitError,
    nRouterAuthenticationError,
    nRouterNotFoundError,
    nRouterRequestError,
    nRouterServiceError,
    nRouterError,
)

def main() -> None:
    with nRouter() as client:
        try:
            # Example: testing non-existent model
            client.chat.completions.create(
                model="nonexistent-model-xyz",
                messages=[{"role": "user", "content": "Hello"}],
            )
        except nRouterGuardrailBlockedError as e:
            print(f"[Guardrail Blocked] {e}")
        except nRouterCreditError as e:
            print(f"[Credit Exhausted] {e}")
        except nRouterRateLimitError as e:
            print(f"[Rate Limited] {e}")
        except nRouterAuthenticationError as e:
            print(f"[Auth Error] {e}")
        except nRouterNotFoundError as e:
            print(f"[Model Not Found - Expected] {e}")
        except nRouterServiceError as e:
            print(f"[Gateway Outage] {e}")
        except nRouterError as e:
            print(f"[General nRouter Error] {e}")

if __name__ == "__main__":
    main()
