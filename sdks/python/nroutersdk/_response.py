"""Response metadata extracted from nRouter response headers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class nRouterResponseMeta:
    """Metadata from the last nRouter API response.

    Extracted from response headers after each API call.

    Attributes:
        request_id: Unique request identifier, present on every response.
        cost: Exact USD request cost, absent when the model is unpriced.
        cost_status: Cost result (``exact`` or ``unpriced``).
        model: Model that served the request.
        input_tokens: Input token count.
        output_tokens: Output token count.
        total_tokens: Total token count, including cache tokens.
        cache_read_tokens: Tokens read from the provider cache.
        cache_write_tokens: Tokens written to the provider cache.
        limit_source: Limit source on a 429 response.
        budget_warning: Present when this request crossed a soft budget you
            configured; the request still served. ``<scope> soft_budget
            <spend>/<ceiling>``, e.g. ``org soft_budget 80.00/100.00``.
        guardrails: Posture of the PRE-CALL guardrail chain — ``none`` |
            ``monitor`` | ``pass`` | ``partial`` | ``blocked``, matched exactly
            and case-sensitively. ``None`` means the gateway made NO guardrail
            claim about this response, never "no guardrail applied" — that is
            the explicit ``none``. Posture only by design: policy name, policy
            id, detector family, rule count and (for ``partial``) which channel
            went uninspected are all deliberately withheld.
        auth_reason: The gateway's stable refusal reason on a 401, e.g.
            ``key_route_not_allowed``. Advertised in :attr:`HEADER_NAMES`, so it
            has to be parsed here too — a name in that list the parser ignores
            is a promise the SDK does not keep.
        response_cache: Executable nRouter response-cache outcome (``hit`` or
            ``miss``), absent when caching did not participate.
        response_cache_age: Age in seconds of a response-cache hit.
    """

    request_id: str | None = None
    cost: float | None = None
    cost_status: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    limit_source: str | None = None
    budget_warning: str | None = None
    guardrails: str | None = None
    auth_reason: str | None = None
    response_cache: str | None = None
    response_cache_age: int | None = None

    #: Every response header this SDK reads, exactly as
    #: ``spec/nrouter-sdk-spec.json`` names them. Published so a caller (and the
    #: cross-SDK conformance gate) can see the set without parsing this module.
    #:
    #: ``ClassVar`` is load-bearing: without it ``dataclass`` makes this an
    #: INSTANCE FIELD, so it becomes a constructor parameter, joins ``repr``,
    #: ``==`` and ``asdict()`` — putting the whole header registry inside every
    #: serialized response — and can be overridden per instance.
    HEADER_NAMES: ClassVar[tuple[str, ...]] = (
        "x-nr-request-id",
        "x-nr-request-cost",
        "x-nr-cost-status",
        "x-nr-model",
        "x-nr-input-tokens",
        "x-nr-output-tokens",
        "x-nr-total-tokens",
        "x-nr-cache-read-tokens",
        "x-nr-cache-write-tokens",
        "x-nr-limit-source",
        "x-nr-budget-warning",
        "x-nr-guardrails",
        "x-nr-auth-reason",
        "x-nr-response-cache",
        "x-nr-response-cache-age",
    )

    @classmethod
    def from_headers(cls, headers: dict) -> nRouterResponseMeta:
        """Parse nRouter response headers into metadata."""
        cost_str = headers.get("x-nr-request-cost")
        cost = float(cost_str) if cost_str else None

        def optional_int(name: str) -> int | None:
            value = headers.get(name)
            return int(value) if value else None

        return cls(
            request_id=headers.get("x-nr-request-id"),
            cost=cost,
            cost_status=headers.get("x-nr-cost-status"),
            model=headers.get("x-nr-model"),
            input_tokens=optional_int("x-nr-input-tokens"),
            output_tokens=optional_int("x-nr-output-tokens"),
            total_tokens=optional_int("x-nr-total-tokens"),
            cache_read_tokens=optional_int("x-nr-cache-read-tokens"),
            cache_write_tokens=optional_int("x-nr-cache-write-tokens"),
            limit_source=headers.get("x-nr-limit-source"),
            budget_warning=headers.get("x-nr-budget-warning"),
            guardrails=headers.get("x-nr-guardrails"),
            auth_reason=headers.get("x-nr-auth-reason"),
            response_cache=headers.get("x-nr-response-cache"),
            response_cache_age=optional_int("x-nr-response-cache-age"),
        )
