"""Sampling policy shared with the JavaScript SDK."""

from __future__ import annotations

import math
import re
from typing import Dict, Optional

from nroutersdk._errors import nRouterRequestError

_NEUTRAL_TOP_P = 1.0


def is_claude_model(model: str, provider: Optional[str] = None) -> bool:
    """Return true when the model belongs to the Claude family."""
    return bool(re.search("claude", model or "", re.I)) or bool(
        re.search("anthropic", provider or "", re.I)
    )


def _require_usable(name: str, value: float, maximum: Optional[float] = None) -> None:
    if not math.isfinite(value):
        raise nRouterRequestError(
            f"{name} must be a finite number; sent as-is it serializes to JSON null."
        )
    if value < 0 or (maximum is not None and value > maximum):
        if maximum is None:
            bounds = "0 or greater"
        else:
            bounds = f"between 0 and {maximum:g}"
        raise nRouterRequestError(f"{name} must be {bounds}, got {value}.")


def build_sampling_params(
    *,
    advanced: bool,
    model: str,
    provider: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
) -> Dict[str, float]:
    """Build the wire sampling fields.

    With advanced sampling off, nothing is sent. For Claude-family models,
    non-neutral top_p wins over temperature because Anthropic rejects both
    together.
    """
    if not advanced:
        return {}

    if temperature is not None:
        _require_usable("temperature", temperature)
    if top_p is not None:
        _require_usable("top_p", top_p, 1)

    top_p_set = top_p is not None and top_p != _NEUTRAL_TOP_P
    suppress_temperature = top_p_set and is_claude_model(model, provider)

    out: Dict[str, float] = {}
    if temperature is not None and not suppress_temperature:
        out["temperature"] = temperature
    if top_p_set and top_p is not None:
        out["top_p"] = top_p
    return out
