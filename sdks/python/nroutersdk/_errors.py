"""nRouter-specific error types.

These wrap server errors into typed exceptions so users can handle
guardrail blocks, credit issues, and rate limits distinctly.
"""

from __future__ import annotations

from typing import Optional


class nRouterError(Exception):
    """Base error for all nRouter SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.status_code = status_code


class nRouterGuardrailBlockedError(nRouterError):
    """Request was blocked by a guardrail (PII, prompt injection, keyword, etc.).

    Attributes:
        guardrail_name: Which guardrail blocked the request (if available).
    """

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        guardrail_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            code="guardrail_blocked",
            request_id=request_id,
            status_code=400,
        )
        self.guardrail_name = guardrail_name


class nRouterCreditError(nRouterError):
    """Insufficient credits to process the request.

    Top up credits at https://app.nrouter.ai/billing.
    """

    def __init__(
        self,
        message: str = "Insufficient credits. Please top up your balance.",
        *,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            code="insufficient_credits",
            request_id=request_id,
            status_code=402,
        )


class nRouterRateLimitError(nRouterError):
    """RPM or TPM rate limit exceeded.

    Attributes:
        limit_type: Either "rpm" or "tpm".
        limit_value: The limit that was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        code: str = "rate_limit_exceeded",
        limit_type: Optional[str] = None,
        limit_value: Optional[int] = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            request_id=request_id,
            status_code=429,
        )
        self.limit_type = limit_type
        self.limit_value = limit_value


class nRouterServiceError(nRouterError):
    """Credit system unavailable (credit_check_failed).

    Transient error — retry after a brief wait.
    """

    def __init__(
        self,
        message: str = "Unable to verify credit balance. Please try again.",
        *,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            code="credit_check_failed",
            request_id=request_id,
            status_code=503,
        )
