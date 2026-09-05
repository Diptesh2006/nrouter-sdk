"""Diagnostics for completion and streaming failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningExhaustionReport:
    exhausted: bool
    finish_reason: str
    reasoning_tokens: int = 0
    output_tokens: int = 0
    message: str | None = None


def diagnose_reasoning_exhaustion(
    finish_reason: str,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    content: str = "",
) -> ReasoningExhaustionReport:
    """Diagnoses whether a completion produced no content because reasoning tokens consumed the budget."""
    f = (finish_reason or "").strip().lower()
    if (f == "length" or f == "max_tokens") and not (content or "").strip():
        if reasoning_tokens > 0 or output_tokens > 0:
            return ReasoningExhaustionReport(
                exhausted=True,
                finish_reason=finish_reason,
                reasoning_tokens=reasoning_tokens,
                output_tokens=output_tokens,
                message=(
                    "Reasoning consumed the entire token budget before completion text could be "
                    "generated. Increase max_tokens or max_completion_tokens."
                ),
            )
    return ReasoningExhaustionReport(
        exhausted=False,
        finish_reason=finish_reason,
        reasoning_tokens=reasoning_tokens,
        output_tokens=output_tokens,
    )
