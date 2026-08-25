"""The typed-error contract, pinned against the envelope the gateway REALLY emits.

Every assertion here was measured against a live gateway on 2026-08-25
(`http://127.0.0.1:4000`, nrouter-rust-gateway at 4b26e9e). The shape is built
by `GatewayError::into_response` in `src/errors.rs`:

    {"error": {"type": "gateway_error", "message": "..."}}

Note what is NOT there: a top-level `code`, and a top-level `error` that is a
string. The pre-2.1.0 client read exactly those two fields, so no typed error
could ever be constructed — and the function that read them was never called
from anywhere either.
"""

from __future__ import annotations

import httpx
import pytest
from openai import APIStatusError

from nroutersdk import (
    nRouterAuthenticationError,
    nRouterCreditError,
    nRouterError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
    nRouterRequestError,
    nRouterServiceError,
)
from nroutersdk.client import _maybe_raise_nrouter_error


def status_error(status: int, message: str, headers: dict | None = None) -> APIStatusError:
    """An APIStatusError carrying the gateway's real envelope."""
    request = httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions")
    response = httpx.Response(
        status,
        request=request,
        headers=headers or {},
        json={"error": {"type": "gateway_error", "message": message}},
    )
    return APIStatusError(message, response=response, body=None)


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (400, "blocked by guardrail 'pii'", nRouterGuardrailBlockedError),
        (400, "invalid request: messages must be an array", nRouterRequestError),
        (401, "unauthorized", nRouterAuthenticationError),
        (402, "insufficient credits", nRouterCreditError),
        (404, "unknown model: gpt-9", nRouterNotFoundError),
        (429, "rate limit exceeded", nRouterRateLimitError),
        (503, "authentication is temporarily unavailable", nRouterServiceError),
    ],
)
def test_each_status_maps_to_its_typed_error(status, message, expected):
    with pytest.raises(expected):
        _maybe_raise_nrouter_error(status_error(status, message))


def test_the_message_is_the_gateway_string_not_a_dict():
    """The pre-2.1.0 client did `body.get("error")`, which is a DICT here.

    A stringified dict reaching a customer's log is not an error message.
    """
    with pytest.raises(nRouterError) as caught:
        _maybe_raise_nrouter_error(status_error(402, "insufficient credits"))
    assert str(caught.value) == "insufficient credits"


def test_a_429_names_its_limit_source_from_the_header():
    """GATE 7: the gateway reports WHICH ceiling produced the 429 in
    `x-nr-limit-source`. Guessing "rpm" sends the customer to the wrong fix."""
    err = status_error(429, "rate limit exceeded", {"x-nr-limit-source": "budget"})
    with pytest.raises(nRouterRateLimitError) as caught:
        _maybe_raise_nrouter_error(err)
    assert caught.value.limit_source == "budget"


def test_retry_after_is_carried_through():
    err = status_error(429, "rate limit exceeded", {"retry-after": "30"})
    with pytest.raises(nRouterRateLimitError) as caught:
        _maybe_raise_nrouter_error(err)
    assert caught.value.retry_after == 30


def test_the_request_id_is_carried_through():
    err = status_error(402, "insufficient credits", {"x-nr-request-id": "req-abc"})
    with pytest.raises(nRouterCreditError) as caught:
        _maybe_raise_nrouter_error(err)
    assert caught.value.request_id == "req-abc"


def test_an_unmapped_status_is_left_for_the_openai_sdk():
    """Not every failure is ours to reclassify; a 418 stays an APIStatusError."""
    assert _maybe_raise_nrouter_error(status_error(418, "teapot")) is None


def test_a_non_json_body_does_not_mask_the_original_error():
    request = httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions")
    response = httpx.Response(502, request=request, text="<html>gateway</html>")
    assert _maybe_raise_nrouter_error(APIStatusError("bad gateway", response=response, body=None)) is None


def test_every_error_class_the_api_contract_names_is_importable():
    """`nrouter-app/src/data/api-reference/api-contract.ts` publishes these class
    names to customers. A name in the docs with no class behind it is a lie."""
    for cls in (
        nRouterRequestError,
        nRouterGuardrailBlockedError,
        nRouterAuthenticationError,
        nRouterCreditError,
        nRouterNotFoundError,
        nRouterRateLimitError,
        nRouterServiceError,
    ):
        assert issubclass(cls, nRouterError)
