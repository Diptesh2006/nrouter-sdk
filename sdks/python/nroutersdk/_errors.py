"""nRouter-specific error types.

These wrap gateway errors into typed exceptions so a caller can handle a
guardrail block, a credit shortfall and a rate limit distinctly, rather than
string-matching an ``openai.APIStatusError``.

The class names here are a PUBLISHED contract: `api-contract.ts` in
`nrouter-app` renders them on `/docs` and `/api-reference`, so a name in that
table with no class behind it is a documented lie. `tests/test_errors.py` pins
the pairing in both directions.
"""

from __future__ import annotations

from typing import Optional


class nRouterError(Exception):
    """Base error for all nRouter SDK errors."""

    #: Stable wire code, mirroring `api-contract.ts`.
    code: str = "nrouter_error"
    #: HTTP status this error is raised for.
    status_code: Optional[int] = None

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.request_id = request_id

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class nRouterRequestError(nRouterError):
    """The request shape was rejected before it reached a provider."""

    code = "invalid_request"
    status_code = 400


class nRouterGuardrailBlockedError(nRouterError):
    """A guardrail denied the request (PII, prompt injection, keyword, ...).

    Guardrails are configured in the dashboard and cannot be overridden
    per-request.
    """

    code = "guardrail_blocked"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        guardrail_name: Optional[str] = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.guardrail_name = guardrail_name


class nRouterAuthenticationError(nRouterError):
    """The virtual key was refused.

    The gateway states a stable reason in ``x-nr-auth-reason`` — for example
    ``key_route_not_allowed`` when the key carries an endpoint scope that does
    not cover this path, or ``auth_backend_unavailable`` when the lookup itself
    failed. It is surfaced as :attr:`auth_reason` because "unauthorized" alone
    sends people to regenerate a key that was never the problem.
    """

    code = "invalid_api_key"
    status_code = 401

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        auth_reason: Optional[str] = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.auth_reason = auth_reason


class nRouterCreditError(nRouterError):
    """Insufficient credits to reserve for this request.

    The reserve happens BEFORE the provider call, so nothing was spent.
    Top up at https://app.nrouter.ai/billing.
    """

    code = "insufficient_credits"
    status_code = 402

    def __init__(
        self,
        message: str = "Insufficient credits. Please top up your balance.",
        *,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, request_id=request_id)


class nRouterNotFoundError(nRouterError):
    """The model alias does not exist, or is not visible to this key.

    Both cases answer 404 deliberately: telling an unauthorised caller that a
    model exists but is out of reach is itself a disclosure.
    """

    code = "model_not_found"
    status_code = 404


class nRouterRateLimitError(nRouterError):
    """An RPM or TPM ceiling was hit.

    Attributes:
        limit_source: WHICH ceiling refused — ``key``, ``plan``, ``team``,
            ``user`` or ``budget``, read from ``x-nr-limit-source``. The
            gateway sends ``None`` rather than guessing when a refusal cannot
            be attributed, and this SDK does not guess either: raising every
            429 as an RPM problem sends a customer whose BUDGET is exhausted to
            go and raise a rate limit.
        retry_after: Seconds to wait, from the ``Retry-After`` header.
    """

    code = "rate_limit_exceeded"
    status_code = 429

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        limit_source: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.limit_source = limit_source
        self.retry_after = retry_after


class nRouterServiceError(nRouterError):
    """A dependency the gateway needs was unavailable. Transient — retry.

    Covers both ``credit_check_failed`` and ``service_unavailable``: the
    gateway refuses rather than assuming, so nothing was charged.
    """

    code = "service_unavailable"
    status_code = 503


__all__ = [
    "nRouterError",
    "nRouterRequestError",
    "nRouterGuardrailBlockedError",
    "nRouterAuthenticationError",
    "nRouterCreditError",
    "nRouterNotFoundError",
    "nRouterRateLimitError",
    "nRouterServiceError",
]
