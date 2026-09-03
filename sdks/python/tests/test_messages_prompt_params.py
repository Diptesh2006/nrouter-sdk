"""Managed prompt parameters on the Messages wire (`/v1/messages`).

WHY THIS PATH SPECIFICALLY. The gateway resolves a provider endpoint per WIRE
and answers 404 `model_unavailable_on_route` for an Anthropic-family model on
`/v1/chat/completions` (see `tests/test_defaults.py`). `_nRouterChat.chat()`
posts only to chat-completions, so for a Claude model `messages.create()` is the
ONLY reachable route to a managed prompt template. Until this landed it took the
wire field names as raw `**kwargs` and vetted nothing, so the tenancy and
`__proto__` refusals in `_options.vet_extra` — the ones the chat path gets — did
not apply to the one path a Claude caller can use.

Parity reference: the JS SDK's `client.messages(body, opts)` ->
`buildFeatureBody` with `promptTemplateId` / `promptVariables` in
`NRouterFeatureOptions` (`sdks/js/src/options.ts`).

Field names are the spec's, not this SDK's invention: `extra_body_fields` in
`spec/nrouter-sdk-spec.json` (Rule #14).
"""

from __future__ import annotations

import pytest

from nroutersdk import AsyncnRouter, nRouter
from nroutersdk._errors import nRouterRequestError
from nroutersdk._options import PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD


def _sync_client(monkeypatch):
    client = nRouter(api_key="sk-nrouter-test")
    posted: list[tuple[str, dict]] = []

    def mock_post(path, json=None):
        posted.append((path, json))
        return {"ok": True}

    monkeypatch.setattr(client, "_nrouter_post", mock_post)
    return client, posted


def _async_client(monkeypatch):
    client = AsyncnRouter(api_key="sk-nrouter-test")
    posted: list[tuple[str, dict]] = []

    async def mock_post(path, json=None):
        posted.append((path, json))
        return {"ok": True}

    monkeypatch.setattr(client, "_nrouter_post", mock_post)
    return client, posted


# --- named parameters reach the wire ---------------------------------------


def test_sync_named_prompt_params_map_to_spec_fields(monkeypatch):
    client, posted = _sync_client(monkeypatch)

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        prompt_template_id="tpl_123",
        prompt_variables={"topic": "credits"},
    )

    path, body = posted[0]
    assert path == "/v1/messages"
    assert body[PROMPT_TEMPLATE_ID_FIELD] == "tpl_123"
    assert body[PROMPT_VARIABLES_FIELD] == {"topic": "credits"}


@pytest.mark.asyncio
async def test_async_named_prompt_params_map_to_spec_fields(monkeypatch):
    client, posted = _async_client(monkeypatch)

    await client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        prompt_template_id="tpl_123",
        prompt_variables={"topic": "credits"},
    )

    path, body = posted[0]
    assert path == "/v1/messages"
    assert body[PROMPT_TEMPLATE_ID_FIELD] == "tpl_123"
    assert body[PROMPT_VARIABLES_FIELD] == {"topic": "credits"}


def test_variables_without_a_template_id_are_still_sent(monkeypatch):
    """The gateway reads the two fields INDEPENDENTLY.

    With no template id it resolves the key/team/org prompt ASSIGNMENT and
    renders it with the caller's variables, so dropping them here would break
    the assigned-template case — which is the common one in production. Same
    reasoning as the JS `buildExtraBody` comment.
    """
    client, posted = _sync_client(monkeypatch)

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        prompt_variables={"topic": "credits"},
    )

    body = posted[0][1]
    assert body[PROMPT_VARIABLES_FIELD] == {"topic": "credits"}
    assert PROMPT_TEMPLATE_ID_FIELD not in body


def test_absent_prompt_params_add_no_wire_fields(monkeypatch):
    """Omission and emptiness are different on this wire — send neither key."""
    client, posted = _sync_client(monkeypatch)

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
    )

    body = posted[0][1]
    assert PROMPT_TEMPLATE_ID_FIELD not in body
    assert PROMPT_VARIABLES_FIELD not in body
    assert "prompt_template_id" not in body
    assert "prompt_variables" not in body


def test_named_param_wins_over_a_raw_kwarg(monkeypatch):
    """Matches JS `{...body, ...buildExtraBody(opts)}` — the option wins."""
    client, posted = _sync_client(monkeypatch)

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        prompt_template_id="tpl_named",
        **{PROMPT_TEMPLATE_ID_FIELD: "tpl_raw"},
    )

    assert posted[0][1][PROMPT_TEMPLATE_ID_FIELD] == "tpl_named"


# --- the escape hatch is vetted, exactly as the chat path's is --------------


@pytest.mark.parametrize("tenancy_key", ["organization_id", "org_id", "team_id", "user_id"])
def test_sync_tenancy_kwarg_is_refused_before_the_request(monkeypatch, tenancy_key):
    """GATE 5: tenancy comes from the authenticated key alone.

    Refused rather than stripped — stripping leaves the caller believing they
    attributed spend somewhere, and that belief is wrong forever and silently.
    """
    client, posted = _sync_client(monkeypatch)

    with pytest.raises(nRouterRequestError, match=tenancy_key):
        client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            **{tenancy_key: "org_deadbeef"},
        )

    assert posted == [], "the refusal must happen before the POST"


def test_sync_proto_kwarg_is_refused(monkeypatch):
    client, posted = _sync_client(monkeypatch)

    with pytest.raises(nRouterRequestError, match="__proto__"):
        client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            **{"__proto__": {"stream": True}},
        )

    assert posted == []


@pytest.mark.asyncio
async def test_async_tenancy_kwarg_is_refused_before_the_request(monkeypatch):
    client, posted = _async_client(monkeypatch)

    with pytest.raises(nRouterRequestError, match="organization_id"):
        await client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            organization_id="org_deadbeef",
        )

    assert posted == []


def test_prompts_helpers_now_reach_the_messages_wire(monkeypatch):
    """`prompts.apply_prompt` emits exactly these two keyword names.

    They were unusable on this path before — spread into `**kwargs` they went
    onto the wire as `prompt_template_id` / `prompt_variables`, which are not
    the spec's field names, so the gateway forwarded them to the provider as
    unrecognized arguments. Pinning the pairing keeps the helper module and the
    Messages signature from drifting apart again.
    """
    from nroutersdk.prompts import apply_prompt, prompt_template

    client, posted = _sync_client(monkeypatch)
    options = apply_prompt({}, prompt_template("tpl_123", {"topic": "credits"}))

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        **options,
    )

    body = posted[0][1]
    assert body[PROMPT_TEMPLATE_ID_FIELD] == "tpl_123"
    assert body[PROMPT_VARIABLES_FIELD] == {"topic": "credits"}
    assert "prompt_template_id" not in body


def test_unmodelled_kwarg_still_reaches_the_wire(monkeypatch):
    """The hatch stays open: vetting refuses two broken shapes, nothing else."""
    client, posted = _sync_client(monkeypatch)

    client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        top_k=5,
    )

    assert posted[0][1]["top_k"] == 5
