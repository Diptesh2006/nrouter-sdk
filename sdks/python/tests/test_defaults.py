"""Model defaults and the token-cap parameter.

MEASURED on 2026-08-25 against live OpenAI through the gateway: the whole gpt-5
family and the o-series answer 400 to `max_tokens`. The gateway now renames it
(nrouter-rust-gateway 4b26e9e), but the SDK must not itself default to a model
that has been superseded, and its own documented example must use the parameter
OpenAI actually documents today.
"""

from __future__ import annotations

import inspect

from nroutersdk import nRouter
from nroutersdk.client import DEFAULT_MODEL

RETIRED = {"gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "claude-sonnet-4-20250514"}


def test_the_default_model_is_not_a_superseded_one():
    assert DEFAULT_MODEL not in RETIRED, f"{DEFAULT_MODEL} has been superseded"


def test_nrouter_chat_defaults_to_the_shared_default_model():
    signature = inspect.signature(nRouter(api_key="sk-nrouter-x").nrouter.chat)
    assert signature.parameters["model"].default == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# The default must be callable on the wire the default call path uses
# ---------------------------------------------------------------------------
#
# `_nRouterChat.chat()` ends in `self._c.chat.completions.create(...)`, so its
# `model` default is posted to `/v1/chat/completions` unconditionally — this SDK
# has no per-model wire switch. The gateway resolves a provider endpoint PER
# WIRE, and a provider declaring no endpoint for a wire answers 404
# `model_unavailable_on_route`: the model exists, just not on the route it was
# asked for. Anthropic declares Messages only, so an Anthropic id here is a 404
# for a brand-new customer holding a valid key who wrote `client.nrouter.chat`
# with no model at all — the worst possible first impression, and one no test
# saw because the suite never calls the network. Derive the gateway side rather
# than trusting this comment::
#
#     cd nrouter-rust-gateway
#     grep -n "fn endpoints" -A 12 src/sdk/providers/anthropic/transformation.rs
#     # => messages: Some(...), responses: None, chat_completions: None

#: Model-id families the gateway serves ONLY on `/v1/messages`.
MESSAGES_WIRE_ONLY = ("anthropic/", "claude-")


def test_the_default_model_is_callable_on_the_wire_the_default_path_uses():
    assert not DEFAULT_MODEL.startswith(MESSAGES_WIRE_ONLY), (
        f"{DEFAULT_MODEL!r} is an Anthropic-family id, which the gateway serves on "
        f"/v1/messages ONLY, but nRouter.nrouter.chat() posts to "
        f"/v1/chat/completions. A caller passing no model gets 404 "
        f"model_unavailable_on_route."
    )


def test_the_module_quickstart_uses_a_chat_completions_capable_model():
    """The docstring at the top of `nroutersdk/__init__.py` is the first code a
    new user copies, and it names `client.chat.completions.create` explicitly."""
    import nroutersdk

    doc = nroutersdk.__doc__ or ""
    assert "chat.completions.create" in doc, "quickstart no longer shows that call"
    for family in MESSAGES_WIRE_ONLY:
        assert family not in doc, (
            f"the package quickstart posts a {family!r} id to "
            f"chat.completions.create, which the gateway answers 404"
        )
