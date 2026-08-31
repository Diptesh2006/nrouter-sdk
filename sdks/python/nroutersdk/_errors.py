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


class nRouterError(Exception):
    """Base error for all nRouter SDK errors."""

    #: Stable wire code, mirroring `api-contract.ts`.
    code: str = "nrouter_error"
    #: HTTP status this error is raised for.
    status_code: int | None = None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
        status_code: int | None = None,
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
        request_id: str | None = None,
        guardrail_name: str | None = None,
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
        request_id: str | None = None,
        auth_reason: str | None = None,
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
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)


class nRouterBudgetExceededError(nRouterError):
    """A configured spend ceiling refused the request — NOT a credit shortfall.

    Deliberately NOT a subclass of :class:`nRouterCreditError`, and that is the
    whole point of the class. The gateway answers 402 for three different
    conditions and two of them are budgets:

        insufficient credits: 0.0100 available, 0.5000 required
        budget exceeded: spent 5.0000 of 5.0000
        budget 'team-cap' (team) exceeded: spent 5.0000 of 5.0000

    The fixes are opposite. A credit shortfall is cleared by topping up; a
    budget ceiling is not cleared by topping up at all — the org may hold plenty
    of credit and still be refused. Collapsing both into "please top up" hands
    the caller a confident, wrong instruction.
    """

    code = "budget_exceeded"
    status_code = 402


class nRouterNotFoundError(nRouterError):
    """The MODEL alias does not exist, or is not visible to this key.

    Both cases answer 404 deliberately: telling an unauthorised caller that a
    model exists but is out of reach is itself a disclosure.

    Scoped to models on purpose. The gateway also answers 404 for a missing
    video job, an unknown MCP server and an unknown agent run; raising this
    class for those would attach a confident, wrong stable code
    (``model_not_found``) to a resource that is not a model. Those surface as
    the base :class:`nRouterError`.
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
        request_id: str | None = None,
        limit_source: str | None = None,
        retry_after: int | None = None,
        code: str | None = None,
    ) -> None:
        # Both `rate_limit_exceeded` and `tpm_limit_exceeded` are 429 and both
        # raise this class, so dispatching on status is correct. But the class
        # default would then report `rate_limit_exceeded` for a TPM refusal,
        # which is a wrong stable code on a right exception — pass through what
        # the gateway actually said when it said anything.
        super().__init__(message, request_id=request_id, code=code)
        self.limit_source = limit_source
        self.retry_after = retry_after


class nRouterServiceError(nRouterError):
    """A dependency the gateway needs was unavailable. Transient — retry.

    Covers both ``credit_check_failed`` and ``service_unavailable``: the
    gateway refuses rather than assuming, so nothing was charged.
    """

    code = "service_unavailable"
    status_code = None


__all__ = [
    "nRouterAuthenticationError",
    "nRouterBudgetExceededError",
    "nRouterCreditError",
    "nRouterError",
    "nRouterGuardrailBlockedError",
    "nRouterNotFoundError",
    "nRouterRateLimitError",
    "nRouterRequestError",
    "nRouterServiceError",
]
