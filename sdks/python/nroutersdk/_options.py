"""nRouter request option helpers shared by the Python surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nroutersdk._errors import nRouterRequestError

PROMPT_TEMPLATE_ID_FIELD = "nrouter_prompt_template_id"
PROMPT_VARIABLES_FIELD = "nrouter_prompt_variables"
CACHE_FIELD = "nrouter_cache"
EXTRA_BODY_FIELDS = (PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD, CACHE_FIELD)

_TENANCY_KEYS = {"organizationid", "orgid", "teamid", "userid", "nrouterorg"}


def _normalize_key(key: str) -> str:
    return key.lower().replace("_", "")


def _configuration_error(message: str) -> nRouterRequestError:
    return nRouterRequestError(message)


def build_extra_body(
    *,
    prompt_template_id: str | None = None,
    prompt_variables: Mapping[str, str] | None = None,
    guardrail_ids: Sequence[str] | None = None,
    cache: bool | None = None,
) -> dict[str, Any]:
    """Map Python options to the exact nRouter gateway body fields.

    Guardrails are configured per key, team, or organization in nRouter. The
    gateway has no per-request guardrail override, so a non-empty guardrail list
    is refused instead of being forwarded to the provider as a dead field.
    """
    if guardrail_ids:
        raise _configuration_error(
            "guardrail_ids is not supported: guardrails are assigned per key, "
            "team, or organization in the nRouter dashboard and already apply "
            "automatically to every call. Remove guardrail_ids to use them."
        )

    extra: dict[str, Any] = {}
    if prompt_template_id:
        extra[PROMPT_TEMPLATE_ID_FIELD] = prompt_template_id
    if prompt_variables:
        extra[PROMPT_VARIABLES_FIELD] = dict(prompt_variables)
    if cache is False:
        extra[CACHE_FIELD] = False
    return extra


def vet_extra(extra: Mapping[str, Any]) -> None:
    """Refuse body fields that cannot be safely honored by the gateway."""
    for key in extra:
        if _normalize_key(key) in _TENANCY_KEYS:
            raise _configuration_error(
                f'extra_body must not carry the tenancy field "{key}". The '
                "gateway resolves organization, team, and user from the "
                "authenticated API key alone."
            )
        if key == "__proto__":
            raise _configuration_error('extra_body must not carry a "__proto__" key; remove it.')
