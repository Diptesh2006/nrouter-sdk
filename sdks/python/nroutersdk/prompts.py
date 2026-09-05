"""Managed prompt helpers for the nRouter request fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from nroutersdk._errors import nRouterRequestError
from nroutersdk._options import (
    PROMPT_TEMPLATE_ID_FIELD,
    PROMPT_VARIABLES_FIELD,
    build_extra_body,
)

PROMPT_WIRE_FIELDS = (PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD)
SYSTEM_VARIABLE_NAMES = ("org_name", "model", "timestamp", "user_id")


@dataclass(frozen=True)
class PromptSelection:
    """One request's prompt selection."""

    template_id: str | None = None
    variables: dict[str, str] | None = None


def prompt_template(
    template_id: str, variables: Mapping[str, str] | None = None
) -> PromptSelection:
    """Select a specific prompt template for one request."""
    if not isinstance(template_id, str) or not template_id.strip():
        raise nRouterRequestError(
            "prompt_template requires a template id. Pass the template id, or "
            "call prompt_variables() to use the assignment for this key, team, "
            "or organization."
        )
    return PromptSelection(
        template_id=template_id.strip(),
        variables=dict(variables) if variables is not None else None,
    )


def prompt_variables(variables: Mapping[str, str]) -> PromptSelection:
    """Render the prompt already assigned to this key, team, or organization."""
    return PromptSelection(variables=dict(variables))


def with_variables(selection: PromptSelection, more: Mapping[str, str]) -> PromptSelection:
    """Return a new selection with extra variables, later values winning."""
    return PromptSelection(
        template_id=selection.template_id,
        variables={**(selection.variables or {}), **dict(more)},
    )


def prompt_extra_body(selection: PromptSelection) -> dict[str, object]:
    """Map a prompt selection to nRouter's request body fields."""
    return build_extra_body(
        prompt_template_id=selection.template_id,
        prompt_variables=selection.variables,
    )


def apply_prompt(options: dict[str, object], selection: PromptSelection) -> dict[str, object]:
    """Return a new options dict with the prompt selection applied."""
    next_options = dict(options)
    if selection.template_id:
        next_options["prompt_template_id"] = selection.template_id
    if selection.variables:
        existing = next_options.get("prompt_variables")
        merged = dict(existing) if isinstance(existing, (dict, Mapping)) else {}
        merged.update(selection.variables)
        next_options["prompt_variables"] = merged
    return next_options


def system_variable_conflicts(variables: Mapping[str, str] | None) -> list[str]:
    """Names the caller supplied that the gateway will overwrite."""
    if not variables:
        return []
    return [name for name in SYSTEM_VARIABLE_NAMES if name in variables]


import re

_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}")


def render_prompt(
    template: str,
    variables: Mapping[str, object] | None = None,
    *,
    strict: bool = False,
    system_variables: Mapping[str, str] | None = None,
) -> str:
    """Safely renders a prompt template by interpolating `{{variable}}` tokens.

    Security & resiliency properties:
    - Single-pass replacement: prevents recursive expansion loops.
    - Callable replacer: prevents regex backreference escapes (\\1, \\g<...>).
    - Strict mode: raises nRouterRequestError if any template variable is missing.
    - System variables: take precedence over caller variables matching gateway rules.
    """
    if not isinstance(template, str):
        return ""

    missing_keys: list[str] = []

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if system_variables and key in system_variables:
            val = system_variables[key]
            return "" if val is None else str(val)
        if variables and key in variables:
            val = variables[key]
            return "" if val is None else str(val)
        if strict:
            missing_keys.append(key)
        return match.group(0)

    result = _VARIABLE_PATTERN.sub(_repl, template)
    if strict and missing_keys:
        raise nRouterRequestError(
            f"Missing required prompt template variables: {', '.join(missing_keys)}"
        )
    return result

