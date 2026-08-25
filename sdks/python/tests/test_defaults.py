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
