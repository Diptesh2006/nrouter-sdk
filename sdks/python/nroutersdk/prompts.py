"""Managed prompt helpers for the nRouter request fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

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

    template_id: Optional[str] = None
    variables: Optional[Dict[str, str]] = None


def prompt_template(
    template_id: str, variables: Optional[Mapping[str, str]] = None
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


def with_variables(
    selection: PromptSelection, more: Mapping[str, str]
) -> PromptSelection:
    """Return a new selection with extra variables, later values winning."""
    return PromptSelection(
        template_id=selection.template_id,
        variables={**(selection.variables or {}), **dict(more)},
    )


def prompt_extra_body(selection: PromptSelection) -> Dict[str, object]:
    """Map a prompt selection to nRouter's request body fields."""
    return build_extra_body(
        prompt_template_id=selection.template_id,
        prompt_variables=selection.variables,
    )


def apply_prompt(options: Dict[str, object], selection: PromptSelection) -> Dict[str, object]:
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


def system_variable_conflicts(variables: Optional[Mapping[str, str]]) -> list[str]:
    """Names the caller supplied that the gateway will overwrite."""
    if not variables:
        return []
    return [name for name in SYSTEM_VARIABLE_NAMES if name in variables]
