"""What the client exposes, and what it must NOT.

The 2.0.2 client shipped ten methods pointing at endpoints no nRouter service
mounts. Measured against the live gateway on 2026-08-25, every one answered 404
and raised a bare `httpx.HTTPStatusError` — not even an OpenAI SDK error:

    client.credits.balance()        -> 404 /api/credits/balance
    client.credits.history()        -> 404 /api/credits/history
    client.guardrails.list()        -> 404 /nrouter/guardrail/list
    client.guardrails.get()         -> 404 /nrouter/guardrail/info
    client.guardrails.logs()        -> 404 /nrouter/guardrail/logs
    client.prompts.list()           -> 404 /nrouter/prompt/list
    client.prompts.get()            -> 404 /nrouter/prompt/info
    client.prompts.versions()       -> 404 /nrouter/prompt/info
    client.prompts.diff()           -> 404 /nrouter/prompt/version/diff
    client.nrouter_models.pricing() -> 404 /api/models/pricing

`/nrouter/*` is the retired Python engine's namespace and is mounted nowhere.
Gateway rule §0 forbids keeping a dead path, so they are deleted rather than
deprecated.
"""

from __future__ import annotations

import pytest

from nroutersdk import AsyncnRouter, nRouter

KEY = "sk-nrouter-test-only-not-a-real-key"

DELETED = ["credits", "guardrails", "prompts"]


@pytest.fixture
def client():
    c = nRouter(api_key=KEY, base_url="http://127.0.0.1:4000/v1")
    yield c
    c.close()


@pytest.mark.parametrize("name", DELETED)
def test_namespaces_backed_by_no_endpoint_are_gone(client, name):
    assert not hasattr(client, name), (
        f"client.{name} points at an endpoint no nRouter service mounts"
    )


def test_pricing_is_gone_but_the_model_list_remains(client):
    assert hasattr(client, "nrouter_models")
    assert not hasattr(client.nrouter_models, "pricing")


def test_responses_is_reachable_not_blocked(client):
    """`/v1/responses` IS mounted and answered 200 live on 2026-08-25. The 2.0.2
    `UNSUPPORTED` table still carried a blocker telling customers otherwise."""
    assert client.responses is not None


@pytest.mark.parametrize(
    "blocked", ["files", "fine_tuning", "batches", "beta", "vector_stores", "uploads"]
)
def test_resources_the_gateway_does_not_mount_still_refuse_loudly(client, blocked):
    from nroutersdk import nRouterUnsupportedError

    with pytest.raises(nRouterUnsupportedError):
        getattr(client, blocked)


@pytest.mark.parametrize("cls", [nRouter, AsyncnRouter])
def test_a_key_without_the_nrouter_prefix_is_refused(cls):
    with pytest.raises(ValueError, match="sk-nrouter-"):
        cls(api_key="sk-openai-shaped-key")


@pytest.mark.parametrize("cls", [nRouter, AsyncnRouter])
def test_the_default_base_url_is_the_canonical_production_host(cls):
    c = cls(api_key=KEY)
    assert str(c.base_url).rstrip("/") == "https://api.nrouter.ai/v1"


def test_sync_and_async_clients_expose_the_same_nrouter_surface():
    sync = nRouter(api_key=KEY)
    async_ = AsyncnRouter(api_key=KEY)
    surface = lambda c: {
        n for n in ("nrouter", "nrouter_models", "messages", "videos") if hasattr(c, n)
    }
    assert surface(sync) == surface(async_)


@pytest.mark.parametrize("cls", [nRouter, AsyncnRouter])
def test_repr_and_str_never_print_full_api_key(cls):
    secret_key = "sk-nrouter-TOPSECRET123456"
    client = cls(api_key=secret_key)
    rep = repr(client)
    st = str(client)
    assert "TOPSECRET" not in rep
    assert "TOPSECRET" not in st
    assert "sk-nrouter-...3456" in rep
    assert "sk-nrouter-...3456" in st

