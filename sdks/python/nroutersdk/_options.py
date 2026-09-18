"""nRouter request option helpers shared by the Python surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nroutersdk._errors import nRouterRequestError

PROMPT_TEMPLATE_ID_FIELD = "nrouter_prompt_template_id"
PROMPT_VARIABLES_FIELD = "nrouter_prompt_variables"
CACHE_FIELD = "nrouter_cache"
FALLBACKS_FIELD = "nrouter_fallbacks"
GUARDRAILS_FIELD = "nrouter_guardrails"
EXTRA_BODY_FIELDS = (
    PROMPT_TEMPLATE_ID_FIELD,
    PROMPT_VARIABLES_FIELD,
    CACHE_FIELD,
    FALLBACKS_FIELD,
    GUARDRAILS_FIELD,
)

#: Published ceilings, from ``spec/nrouter-sdk-spec.json`` (``extra_body_fields``).
#:
#: Enforced HERE rather than left to the gateway. The gateway refuses an
#: over-long list with a 400 the caller pays a round trip for, and that refusal
#: names the wire field (``nrouter_fallbacks``) rather than the Python argument
#: they actually set. A local refusal costs nothing and names the argument.
MAX_FALLBACKS = 4
MAX_GUARDRAILS = 8

_TENANCY_KEYS = {"organizationid", "orgid", "teamid", "userid", "nrouterorg"}


def _normalize_key(key: str) -> str:
    return key.lower().replace("_", "")


def _configuration_error(message: str) -> nRouterRequestError:
    return nRouterRequestError(message)


def _names(value: Sequence[str], *, argument: str, ceiling: int) -> list[str]:
    """Normalize one override list, or refuse it.

    Whitespace-only entries are refused rather than trimmed away. Dropping one
    leaves the caller with a SHORTER list than they wrote and no way to know:
    for guardrails that is a safety control the request was never inspected by,
    and for fallbacks it is a chain shorter than the one they reasoned about.
    """
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise _configuration_error(
                f"{argument} contains an empty entry. Every entry must be a "
                f"non-empty name; an entry silently dropped here is a shorter "
                f"list than you wrote, with nothing saying so."
            )
        out.append(entry.strip())
    if len(out) > ceiling:
        raise _configuration_error(
            f"{argument} carries {len(out)} entries; the gateway accepts at "
            f"most {ceiling}. Sent as-is the whole request is refused with a "
            f"400 before any provider call."
        )
    return out


def build_extra_body(
    *,
    prompt_template_id: str | None = None,
    prompt_variables: Mapping[str, str] | None = None,
    fallbacks: Sequence[str] | None = None,
    guardrails: Sequence[str] | None = None,
    cache: bool | None = None,
) -> dict[str, Any]:
    """Map Python options to the exact nRouter gateway body fields.

    The field set is CLOSED — ``extra_body_fields`` in
    ``spec/nrouter-sdk-spec.json`` is the whole of what the gateway lifts off a
    request body, and it forwards everything else to the provider verbatim. A
    field this SDK invents is therefore not an error a caller ever sees; it is a
    dead option that looks live.

    ``guardrail_ids`` USED to live here as a REFUSAL, and that was correct while
    it lasted: measured 2026-08-28, no gateway read any per-request guardrail
    field, so sending one bought the caller an opaque provider rejection. The
    gateway added real per-request overrides on 2026-09-17 —
    ``nrouter_fallbacks`` and ``nrouter_guardrails`` — so the refusal now
    inverts its own reason and is gone. The replacements are NOT renames:

    * ``fallbacks`` REPLACES the organization's fallback policy for this one
      call; it is not merged with it. ``model`` stays the primary.
    * ``guardrails`` is ADD-ONLY. It adds to what the key, team and organization
      already assign and to the platform moderation floor, and can never remove,
      relax or replace any of them. A request cannot turn a guardrail off.

    An empty list is OMITTED rather than sent. On this wire omission and
    emptiness mean different things: an empty list is a caller asking for
    something, and ``fallbacks=state.selected`` with an empty default is a
    caller asking for nothing.
    """
    extra: dict[str, Any] = {}
    if prompt_template_id:
        extra[PROMPT_TEMPLATE_ID_FIELD] = prompt_template_id
    if prompt_variables:
        extra[PROMPT_VARIABLES_FIELD] = dict(prompt_variables)
    if cache is False:
        extra[CACHE_FIELD] = False
    if fallbacks:
        extra[FALLBACKS_FIELD] = _names(
            fallbacks, argument="fallbacks", ceiling=MAX_FALLBACKS
        )
    if guardrails:
        extra[GUARDRAILS_FIELD] = _names(
            guardrails, argument="guardrails", ceiling=MAX_GUARDRAILS
        )
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
