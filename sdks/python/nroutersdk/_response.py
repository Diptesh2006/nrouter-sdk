"""Response metadata extracted from nRouter response headers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class nRouterResponseMeta:
    """Metadata from the last nRouter API response.

    Extracted from response headers after each API call.

    Attributes:
        request_id: Unique request identifier (x-nrouter-request-id).
        cost: Actual cost in dollars (x-nrouter-request-cost).
        guardrails_applied: List of guardrails that were evaluated (x-nrouter-guardrails-applied).
        prompt_version: Active prompt template version (x-nrouter-prompt-version).
        ab_test_variant: A/B test variant assigned (x-nrouter-ab-test).
        post_call_guardrails: Guardrails that ran post-call (x-nrouter-post-call-guardrails).
        stream_buffered: Whether stream was buffered for post-call guardrails.
        cache_status: Cache hit/miss for models endpoint (x-nrouter-cache).
    """

    request_id: Optional[str] = None
    cost: Optional[float] = None
    guardrails_applied: List[str] = field(default_factory=list)
    prompt_version: Optional[int] = None
    ab_test_variant: Optional[str] = None
    post_call_guardrails: List[str] = field(default_factory=list)
    stream_buffered: bool = False
    cache_status: Optional[str] = None

    @classmethod
    def from_headers(cls, headers: dict) -> "nRouterResponseMeta":
        """Parse nRouter response headers into metadata."""
        cost_str = headers.get("x-nrouter-request-cost")
        cost = float(cost_str) if cost_str else None

        guardrails_str = headers.get("x-nrouter-guardrails-applied", "")
        guardrails = [g.strip() for g in guardrails_str.split(",") if g.strip()] if guardrails_str else []

        version_str = headers.get("x-nrouter-prompt-version")
        version = int(version_str) if version_str else None

        post_guards_str = headers.get("x-nrouter-post-call-guardrails", "")
        post_guards = [g.strip() for g in post_guards_str.split(",") if g.strip()] if post_guards_str else []

        return cls(
            request_id=headers.get("x-nrouter-request-id"),
            cost=cost,
            guardrails_applied=guardrails,
            prompt_version=version,
            ab_test_variant=headers.get("x-nrouter-ab-test"),
            post_call_guardrails=post_guards,
            stream_buffered=headers.get("x-nrouter-stream-buffered") == "true",
            cache_status=headers.get("x-nrouter-cache"),
        )
