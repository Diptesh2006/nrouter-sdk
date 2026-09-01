"""BILLED acceptance probes against a real nRouter gateway.

Every test here reaches a real gateway, a real provider and a real credit
balance, so the whole module is opt-in::

    pytest -q                          # every probe reports SKIPPED
    NROUTER_LIVE=1 pytest -q           # runs them; needs the env below

# Why the gate is ``pytest.mark.skipif`` and not an early ``return``

An early ``return`` inside a test body is a PASS to the runner, so a machine
with no key, no gateway and no credits would print these probes as passing --
release evidence that cannot tell a probe that ran from one that never executed
a line. ``skipif`` is decided BEFORE the body runs, so the report says SKIPPED
with its reason. Non-execution can be skipped or a failure; it can never be a
pass.

# And why a missing per-wire variable is a RAISE, not a skip

Once ``NROUTER_LIVE=1`` is set the caller has asked for the billed probes. A
missing variable at that point is a misconfigured live run, not a reason to
report success -- so :func:`required` raises and names the variable.

# The route-family matrix

Claude-through-``/v1/messages`` was the only live acceptance the Python SDK
had, so the wires customers actually reported broken -- OpenAI chat
completions, ``/v1/responses``, and an opaque alias whose provider is not
inferable from its name -- were outside live evidence entirely. This SDK was
additionally the ONE supported SDK with no matrix at all, because its suite
could not even be collected until ``sdks/python[dev]`` was installable; the
gate was dead rather than merely thin.

They are separate tests with separate model variables because a model is
servable on the wires ITS provider declares and no others: one model cannot
certify the matrix, and a single test that tried would fail for a reason that
is not a defect.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from nroutersdk import nRouter

pytestmark = pytest.mark.skipif(
    os.getenv("NROUTER_LIVE") != "1",
    reason=(
        "billed: set NROUTER_LIVE=1, NROUTER_API_KEY and the per-wire model "
        "variables to run the gateway acceptance matrix"
    ),
)


def required(name: str) -> str:
    """The value of ``name``, or a raise naming it.

    Reached only under ``NROUTER_LIVE=1``, where the caller has already asked
    for a billed run.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is required for a live probe. Set NROUTER_LIVE=1, "
            "NROUTER_API_KEY, and the per-wire model variables, then run "
            "`NROUTER_LIVE=1 pytest -q`."
        )
    return value


def live_client() -> nRouter:
    """A client pointed at the gateway under test."""
    return nRouter(
        api_key=os.environ["NROUTER_API_KEY"],
        base_url=os.getenv("NROUTER_BASE_URL", "http://127.0.0.1:4000/v1"),
        max_retries=0,
    )


def assert_correlatable(client: nRouter, wire: str) -> None:
    """Every response must carry ``x-nr-request-id``.

    It is the only handle a customer has at support, and the join key for the
    spend row the call just wrote.
    """
    meta = client.last_response
    assert meta is not None, f"{wire} answered without any x-nr-* metadata"
    assert meta.request_id, f"{wire} answered without x-nr-request-id"


def assert_honest_cost(client: nRouter, wire: str) -> None:
    """Unpriced is not free.

    ``x-nr-request-cost`` is ABSENT when the model is unpriced -- never a zero
    -- so the honest states are exactly two, and a reported cost of 0 is a
    defect on either.
    """
    meta = client.last_response
    assert meta is not None, f"{wire} answered without any x-nr-* metadata"
    if meta.cost_status is None:
        return
    assert meta.cost_status in ("exact", "unpriced"), (
        f"{wire} reported x-nr-cost-status {meta.cost_status!r}"
    )
    if meta.cost_status == "exact":
        assert meta.cost is not None and meta.cost > 0, (
            f"{wire} claimed an exact cost that was not above zero"
        )
    else:
        assert meta.cost is None, f"{wire} priced an unpriced response"


def advertised_endpoints(catalogue: dict[str, Any], model: str) -> list[str]:
    """The ``/v1`` paths ``GET /v1/models`` says this alias can be called on.

    The gateway renders ``nrouter_endpoints`` from the provider's own endpoint
    declaration, so this is the discovery answer an SDK is supposed to use
    instead of guessing a wire from the model name.
    """
    data = catalogue.get("data")
    assert isinstance(data, list) and data, "GET /v1/models returned an empty catalogue"
    entry = next((item for item in data if item.get("id") == model), None)
    assert entry is not None, f"{model} is not in this key's catalogue"
    endpoints = entry.get("nrouter_endpoints")
    assert isinstance(endpoints, list), f"{model} carries no nrouter_endpoints"
    return endpoints


def test_live_claude_messages_returns_billing_metadata():
    with live_client() as client:
        response = client.messages.create(
            model=os.getenv("NROUTER_LIVE_MESSAGES_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=2,
            messages=[{"role": "user", "content": "Reply OK"}],
        )
        assert response["content"], "/v1/messages returned no content block"
        assert_correlatable(client, "/v1/messages")
        # A known-priced Claude model: this wire must report an exact cost, not
        # merely an honest one.
        assert client.last_response is not None
        assert client.last_response.cost_status == "exact"
        assert client.last_response.cost is not None
        assert client.last_response.cost > 0


def test_live_openai_chat_completions_wire_answers():
    with live_client() as client:
        response = client.chat.completions.create(
            model=required("NROUTER_LIVE_CHAT_MODEL"),
            max_tokens=2,
            messages=[{"role": "user", "content": "Reply OK"}],
        )
        assert response.choices, "/v1/chat/completions returned no choices"
        assert_correlatable(client, "/v1/chat/completions")
        assert_honest_cost(client, "/v1/chat/completions")


def test_live_responses_wire_answers():
    with live_client() as client:
        response = client.responses.create(
            model=required("NROUTER_LIVE_RESPONSES_MODEL"),
            input="Reply OK",
            max_output_tokens=16,
        )
        assert response is not None, "/v1/responses returned an empty document"
        assert getattr(response, "id", None), "/v1/responses returned no response id"
        assert_correlatable(client, "/v1/responses")
        assert_honest_cost(client, "/v1/responses")


def test_live_opaque_alias_is_callable_on_the_wire_discovery_advertises():
    """An alias whose provider a client cannot infer from the name.

    A Bedrock GLM or a Gemma alias must still be callable, and the wire must
    come from discovery rather than from a guess.

    This is the one probe that proves the matrix is DERIVABLE: it reads the
    endpoints out of ``GET /v1/models`` and then calls the wire it was told
    about. An alias listed with an endpoint it cannot serve fails here.
    """
    model = required("NROUTER_LIVE_OPAQUE_MODEL")
    with live_client() as client:
        endpoints = advertised_endpoints(client.nrouter_models.list(), model)
        assert endpoints, (
            f"{model} is listed with an empty nrouter_endpoints — the catalogue "
            "advertises a name no wire serves"
        )

        messages = [{"role": "user", "content": "Reply OK"}]
        if "/v1/chat/completions" in endpoints:
            wire = "/v1/chat/completions"
            response = client.chat.completions.create(
                model=model, max_tokens=2, messages=messages
            )
            assert response.choices, f"{wire} returned no choices for {model}"
        elif "/v1/messages" in endpoints:
            wire = "/v1/messages"
            body = client.messages.create(model=model, max_tokens=2, messages=messages)
            assert body["content"], f"{wire} returned no content block for {model}"
        else:
            pytest.fail(f"{model} advertises no text wire: {endpoints}")

        assert_correlatable(client, f"the discovered text wire {wire}")
        assert_honest_cost(client, f"the discovered text wire {wire}")
