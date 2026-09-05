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

import datetime
import email.utils
import math
import random
import re
import time
from typing import Any

_KEY_RE = re.compile(r"(sk-nrouter-)[A-Za-z0-9._-]{6,}")
_GENERIC_KEY_RE = re.compile(r"(sk-)(?!nrouter-)[A-Za-z0-9._-]{6,}")


def redact_keys(message: str) -> str:
    """Mask nRouter and provider API keys in error strings to prevent credential leaks."""
    if not isinstance(message, str):
        return str(message)
    out = _KEY_RE.sub(r"\g<1>***", message)
    return _GENERIC_KEY_RE.sub(r"\g<1>***", out)


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
        sanitized = redact_keys(message)
        super().__init__(sanitized)
        self.message = sanitized
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


def is_retryable(err: Exception | Any) -> bool:
    """Whether retrying could plausibly succeed.

    True for rate limits, service errors, and transient HTTP status codes (408, 425, 429, 502, 503, 504).
    """
    if isinstance(err, (nRouterRateLimitError, nRouterServiceError)):
        return True
    status = getattr(err, "status_code", None)
    if status in (408, 425, 429, 502, 503, 504):
        return True
    return False


MAX_RETRY_AFTER_SECONDS: int = 86400


def parse_retry_after(value: str | None, now: float | None = None) -> int | None:
    """Parse an RFC 9110 Retry-After header value (delta-seconds or HTTP-date).

    Dates in the past clamp to 0 seconds. Values exceeding 24 hours (86400s) clamp to 86400.
    Invalid, negative, or unparseable values return None.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None

    if trimmed.isdigit():
        try:
            sec = int(trimmed)
            return min(max(0, sec), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            return None

    try:
        dt = email.utils.parsedate_to_datetime(trimmed)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        current_epoch = time.time() if now is None else now
        current_dt = datetime.datetime.fromtimestamp(current_epoch, tz=datetime.timezone.utc)
        diff = (dt - current_dt).total_seconds()
        if diff <= 0:
            return 0
        return min(int(math.ceil(diff)), MAX_RETRY_AFTER_SECONDS)
    except (ValueError, TypeError, IndexError, OverflowError):
        return None


def compute_jittered_backoff(
    attempt: int,
    base_delay_ms: float = 500.0,
    max_delay_ms: float = 30000.0,
    retry_after_seconds: float | None = None,
    jitter_factor: float = 0.5,
) -> float:
    """Compute jittered exponential backoff in milliseconds.

    Honors Retry-After when present and positive, capped at max_delay_ms.
    Clamps attempt to [0, 30] to prevent exponential numeric overflow.
    Applies jitter factor to avoid thundering herd.
    """
    safe_attempt = max(0, min(attempt, 30))
    jitter_factor = max(0.0, min(jitter_factor, 1.0))

    if retry_after_seconds is not None and math.isfinite(retry_after_seconds) and retry_after_seconds > 0:
        retry_ms = min(retry_after_seconds * 1000.0, max_delay_ms)
        multiplier = (1.0 - jitter_factor) + random.random() * jitter_factor
        return max(0.0, retry_ms * multiplier)

    raw_delay = min(max_delay_ms, base_delay_ms * (2.0 ** safe_attempt))
    multiplier = (1.0 - jitter_factor) + random.random() * jitter_factor
    return max(0.0, raw_delay * multiplier)


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
    "is_retryable",
    "redact_keys",
    "parse_retry_after",
    "compute_jittered_backoff",
    "MAX_RETRY_AFTER_SECONDS",
]


