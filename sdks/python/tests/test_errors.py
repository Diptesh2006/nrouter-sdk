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

import httpx2 as httpx
import pytest
from openai import APIStatusError

from nroutersdk import (
    nRouterAuthenticationError,
    nRouterBudgetExceededError,
    nRouterCreditError,
    nRouterError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
    nRouterRequestError,
    nRouterServiceError,
)
from nroutersdk.client import _maybe_raise_nrouter_error


def status_error(
    status: int,
    message: str,
    headers: dict | None = None,
    code: str | None = None,
) -> APIStatusError:
    """An APIStatusError carrying the gateway's real envelope.

    `code` is optional because the gateway does not always send one; omitting it
    is the shape this SDK saw before 2.1.0 and must keep handling.
    """
    request = httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions")
    error: dict = {"type": "gateway_error", "message": message}
    if code is not None:
        error["code"] = code
    response = httpx.Response(
        status,
        request=request,
        headers=headers or {},
        json={"error": error},
    )
    return APIStatusError(message, response=response, body=None)


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (400, "blocked by guardrail 'pii'", nRouterGuardrailBlockedError),
        (400, "invalid request: messages must be an array", nRouterRequestError),
        (401, "unauthorized", nRouterAuthenticationError),
        (402, "insufficient credits: 0.0100 available, 0.5000 required", nRouterCreditError),
        # A 402 is NOT always "top up". The gateway emits three of them and two
        # are budget ceilings, whose fix is to RAISE THE BUDGET — telling that
        # caller to add funds sends them to the wrong place entirely.
        (402, "budget exceeded: spent 5.0000 of 5.0000", nRouterBudgetExceededError),
        (
            402,
            "budget 'team-cap' (team) exceeded: spent 5.0000 of 5.0000",
            nRouterBudgetExceededError,
        ),
        (404, "unknown model: gpt-9", nRouterNotFoundError),
        # 404 also covers a missing video job, an unknown MCP server and an
        # unknown agent run. Reporting those as a missing MODEL is a wrong
        # answer with a confident stable code attached.
        (404, "video not found: vid_123", nRouterError),
        (429, "rate limit exceeded", nRouterRateLimitError),
        (500, "a backend service is temporarily unavailable", nRouterServiceError),
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


def test_service_errors_carry_the_actual_status_code():
    with pytest.raises(nRouterServiceError) as caught:
        _maybe_raise_nrouter_error(
            status_error(500, "a backend service is temporarily unavailable")
        )
    assert caught.value.status_code == 500


def test_an_unmapped_status_is_left_for_the_openai_sdk():
    """Not every failure is ours to reclassify; a 418 stays an APIStatusError."""
    assert _maybe_raise_nrouter_error(status_error(418, "teapot")) is None


def test_a_non_json_body_does_not_mask_the_original_error():
    request = httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions")
    response = httpx.Response(502, request=request, text="<html>gateway</html>")
    assert (
        _maybe_raise_nrouter_error(APIStatusError("bad gateway", response=response, body=None))
        is None
    )


def test_every_error_class_the_api_contract_names_is_importable():
    """`nrouter-app/src/data/api-reference/api-contract.ts` publishes these class
    names to customers. A name in the docs with no class behind it is a lie."""
    for cls in (
        nRouterBudgetExceededError,
        nRouterRequestError,
        nRouterGuardrailBlockedError,
        nRouterAuthenticationError,
        nRouterCreditError,
        nRouterNotFoundError,
        nRouterRateLimitError,
        nRouterServiceError,
    ):
        assert issubclass(cls, nRouterError)


def test_a_budget_ceiling_is_not_swallowed_by_a_credit_handler():
    """`except nRouterCreditError` must NOT catch a budget refusal.

    If it did, the caller would be told to top up while the actual fix is to
    raise a budget — and topping up would not clear the refusal.
    """
    assert not issubclass(nRouterBudgetExceededError, nRouterCreditError)
    assert not issubclass(nRouterCreditError, nRouterBudgetExceededError)


def test_a_generic_404_is_not_reported_as_a_missing_model():
    err = status_error(404, "video not found: vid_123")
    with pytest.raises(nRouterError) as caught:
        _maybe_raise_nrouter_error(err)
    assert not isinstance(caught.value, nRouterNotFoundError)


def test_a_tpm_refusal_reports_its_own_code_not_the_class_default():
    """`tpm_limit_exceeded` and `rate_limit_exceeded` share status 429.

    Both correctly raise nRouterRateLimitError, but reporting the class default
    `rate_limit_exceeded` for a TPM refusal is a wrong stable code on a right
    exception — and `code` is what a caller branches on when `limit_source` is
    absent.
    """
    with pytest.raises(nRouterRateLimitError) as caught:
        _maybe_raise_nrouter_error(
            status_error(429, "token rate exceeded", code="tpm_limit_exceeded")
        )
    assert caught.value.code == "tpm_limit_exceeded"


def test_an_rpm_refusal_keeps_its_own_code_too():
    with pytest.raises(nRouterRateLimitError) as caught:
        _maybe_raise_nrouter_error(
            status_error(429, "too many requests", code="rate_limit_exceeded")
        )
    assert caught.value.code == "rate_limit_exceeded"


def test_a_429_without_a_code_falls_back_to_the_class_default():
    with pytest.raises(nRouterRateLimitError) as caught:
        _maybe_raise_nrouter_error(status_error(429, "too many requests"))
    assert caught.value.code == "rate_limit_exceeded"


def test_a_code_when_present_beats_the_status():
    """The gateway's WAF and upstream passthrough DO send a code.

    Status alone cannot separate the two 429s or the two 400s, so a code the
    gateway did send must win.
    """
    with pytest.raises(nRouterGuardrailBlockedError):
        _maybe_raise_nrouter_error(
            # A message that does NOT say "guardrail" — only the code does.
            status_error(400, "request rejected", code="guardrail_blocked")
        )


def test_the_header_name_list_matches_what_is_parsed():
    from nroutersdk import nRouterResponseMeta

    assert len(nRouterResponseMeta.HEADER_NAMES) == 13
    meta = nRouterResponseMeta.from_headers(
        {name: "1" for name in nRouterResponseMeta.HEADER_NAMES}
    )
    # Every advertised header must reach a field; a name in the list that the
    # parser ignores is a promise the SDK does not keep.
    assert meta.request_id is not None
    assert meta.cost is not None
    assert meta.limit_source is not None
    assert meta.response_cache is not None


def test_auth_reason_reaches_the_metadata():
    """HEADER_NAMES advertises it, so the parser has to produce it.

    A name in that list the parser ignores is a promise the SDK does not keep,
    and the cross-SDK gate cannot see the difference.
    """
    from nroutersdk import nRouterResponseMeta

    meta = nRouterResponseMeta.from_headers(
        {"x-nr-auth-reason": "key_route_not_allowed", "x-nr-request-id": "req_1"}
    )
    assert meta.auth_reason == "key_route_not_allowed"


def test_a_service_error_keeps_the_code_the_gateway_named():
    """`credit_check_failed` and `service_unavailable` share one class.

    Without the code the exception reports the class default, so a caller
    branching on the stable code is handed the wrong one.
    """
    with pytest.raises(nRouterServiceError) as caught:
        _maybe_raise_nrouter_error(
            status_error(503, "credit system unavailable", code="credit_check_failed")
        )
    assert caught.value.code == "credit_check_failed"
