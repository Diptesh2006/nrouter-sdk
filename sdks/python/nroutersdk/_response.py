"""Response metadata extracted from nRouter response headers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
        response_cache: Executable nRouter response-cache outcome (``hit`` or
            ``miss``), absent when caching did not participate.
        response_cache_age: Age in seconds of a response-cache hit.
    """

    request_id: Optional[str] = None
    cost: Optional[float] = None
    cost_status: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    limit_source: Optional[str] = None
    response_cache: Optional[str] = None
    response_cache_age: Optional[int] = None

    #: Every response header this SDK reads, exactly as
    #: ``spec/nrouter-sdk-spec.json`` names them. Published so a caller (and the
    #: cross-SDK conformance gate) can see the set without parsing this module.
    HEADER_NAMES: "tuple[str, ...]" = (
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
        "x-nr-auth-reason",
        "x-nr-response-cache",
        "x-nr-response-cache-age",
    )

    @classmethod
    def from_headers(cls, headers: dict) -> "nRouterResponseMeta":
        """Parse nRouter response headers into metadata."""
        cost_str = headers.get("x-nr-request-cost")
        cost = float(cost_str) if cost_str else None

        def optional_int(name: str) -> Optional[int]:
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
            response_cache=headers.get("x-nr-response-cache"),
            response_cache_age=optional_int("x-nr-response-cache-age"),
        )
