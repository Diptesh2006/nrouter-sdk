"""Proof that the typed errors are WIRED, not merely defined.

`tests/test_errors.py` calls `_maybe_raise_nrouter_error` directly, so it would
pass unchanged even if nothing ever called that function — which is exactly the
2.0.2 defect: the mapper was correct-looking, exported, documented, and dead.

These tests drive a real client through a stubbed transport and assert on what
a CUSTOMER receives, so deleting the `_make_status_error` override turns them
red.
"""

from __future__ import annotations

try:
    import openai._base_client as _obc
    httpx = _obc.httpx
except (ImportError, AttributeError):
    try:
        import httpx
    except ImportError:
        import httpx2 as httpx
import pytest

from nroutersdk import (
    AsyncnRouter,
    nRouterAuthenticationError,
    nRouterCreditError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
    nRouterServiceError,
    nRouter,
)

KEY = "sk-nrouter-test-only-not-a-real-key"


def gateway(status: int, message: str, headers: dict | None = None) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers=headers or {},
            json={"error": {"type": "gateway_error", "message": message}},
        )

    return httpx.MockTransport(handler)


def client(status: int, message: str, headers: dict | None = None) -> nRouter:
    return nRouter(
        api_key=KEY,
        base_url="https://api.nrouter.ai/v1",
        http_client=httpx.Client(transport=gateway(status, message, headers)),
        max_retries=0,
    )


def chat(c: nRouter):
    return c.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": "hi"}],
        max_completion_tokens=16,
    )


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (400, "blocked by guardrail 'pii'", nRouterGuardrailBlockedError),
        (401, "unauthorized", nRouterAuthenticationError),
        (402, "insufficient credits", nRouterCreditError),
        (404, "unknown model: gpt-9", nRouterNotFoundError),
        (429, "rate limit exceeded", nRouterRateLimitError),
        (500, "a backend service is temporarily unavailable", nRouterServiceError),
    ],
)
def test_a_real_call_raises_the_typed_error(status, message, expected):
    with client(status, message) as c:
        with pytest.raises(expected) as caught:
            chat(c)
    assert str(caught.value) == message


def test_a_401_carries_the_gateway_auth_reason():
    """`unauthorized` alone sends people to regenerate a key that was fine; the
    reason names the actual refusal (measured: `key_route_not_allowed` when a
    key's endpoint scope does not cover the path)."""
    with client(401, "unauthorized", {"x-nr-auth-reason": "key_route_not_allowed"}) as c:
        with pytest.raises(nRouterAuthenticationError) as caught:
            chat(c)
    assert caught.value.auth_reason == "key_route_not_allowed"


def test_a_429_reports_the_measured_limit_source_not_a_guess():
    with client(429, "budget exhausted", {"x-nr-limit-source": "budget"}) as c:
        with pytest.raises(nRouterRateLimitError) as caught:
            chat(c)
    assert caught.value.limit_source == "budget"


def test_an_unclassified_status_still_raises_the_openai_error():
    from openai import APIStatusError

    with client(418, "teapot") as c:
        with pytest.raises(APIStatusError):
            chat(c)


@pytest.mark.asyncio
async def test_the_async_client_types_errors_too():
    c = AsyncnRouter(
        api_key=KEY,
        base_url="https://api.nrouter.ai/v1",
        http_client=httpx.AsyncClient(transport=gateway(402, "insufficient credits")),
        max_retries=0,
    )
    with pytest.raises(nRouterCreditError):
        await c.chat.completions.create(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hi"}],
            max_completion_tokens=16,
        )
    await c.close()
