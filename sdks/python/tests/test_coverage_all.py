from __future__ import annotations

from typing import Any, Mapping
import httpx2 as httpx
import pytest

from nroutersdk import AsyncnRouter, nRouter
from nroutersdk._errors import (
    nRouterAuthenticationError,
    nRouterError,
    nRouterRateLimitError,
    nRouterRequestError,
    nRouterServiceError,
)
from nroutersdk._options import build_extra_body, vet_extra
from nroutersdk.client import _maybe_raise_nrouter_error
from nroutersdk.memory import ArrayMemoryStore, MemoryStore, create_array_store, create_memory
from nroutersdk.prompts import (
    prompt_template,
    prompt_variables,
    system_variable_conflicts,
    with_variables,
)
from nroutersdk.sampling import build_sampling_params, is_claude_model


def test_extra_and_vetting_edges():
    # __proto__ rejection
    with pytest.raises(nRouterRequestError, match="__proto__"):
        vet_extra({"__proto__": "pollute"})

    # empty extra
    vet_extra({})

    # build_extra_body with empty prompt_variables / template
    assert build_extra_body(prompt_template_id="", prompt_variables={}) == {}
    assert build_extra_body(prompt_template_id="tpl", prompt_variables={"k": "v"}, cache=None) == {
        "nrouter_prompt_template_id": "tpl",
        "nrouter_prompt_variables": {"k": "v"},
    }


def test_sampling_edges():
    # is_claude_model checks
    assert is_claude_model("custom-model", "anthropic") is True
    assert is_claude_model("claude-3-opus", None) is True
    assert is_claude_model("gpt-4o", "openai") is False

    # Negative temperature or out-of-range top_p
    with pytest.raises(nRouterRequestError):
        build_sampling_params(advanced=True, model="x", temperature=-0.1)
    with pytest.raises(nRouterRequestError):
        build_sampling_params(advanced=True, model="x", top_p=-0.1)
    with pytest.raises(nRouterRequestError):
        build_sampling_params(advanced=True, model="x", temperature=float("inf"))


def test_prompts_edges():
    sel = prompt_template("tpl_1")
    assert sel.template_id == "tpl_1"
    assert sel.variables is None

    # with_variables on selection without initial variables
    merged = with_variables(sel, {"foo": "bar"})
    assert merged.variables == {"foo": "bar"}

    # with_variables with extra mapping
    merged2 = with_variables(merged, {"baz": "qux"})
    assert merged2.variables == {"foo": "bar", "baz": "qux"}

    # system_variable_conflicts with non-dict
    assert system_variable_conflicts(None) == []


@pytest.mark.asyncio
async def test_memory_store_edges():
    store = create_array_store([{"role": "user", "content": "hello"}])
    assert len(store.load()) == 1

    memory = create_memory(store)
    assert len(await memory.messages()) == 1

    # clear
    await memory.clear()
    assert len(await memory.messages()) == 0

    # Invalid message role
    with pytest.raises(nRouterRequestError, match="role"):
        await memory.add({"role": "invalid_role", "content": "hi"})

    # Invalid message content
    with pytest.raises(nRouterRequestError, match="content"):
        await memory.add({"role": "user", "content": 12345})

    # Non-dict message
    with pytest.raises(nRouterRequestError, match="dict"):
        await memory.add("not a dict")  # type: ignore

    # Nested array and dict copying
    await memory.add(
        {
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "metadata": {"nested": [1, 2, 3]},
        }
    )
    msgs = await memory.messages()
    assert len(msgs) == 1

    # Broken custom store returning non-list
    class BadStore(MemoryStore):
        def load(self):
            return "not a list"

        def save(self, msgs):
            pass

    bad_memory = create_memory(BadStore())
    with pytest.raises(nRouterRequestError, match="list"):
        await bad_memory.messages()


def test_sync_messages_and_videos_endpoints(monkeypatch):
    client = nRouter(api_key="sk-nrouter-test")

    # Mock _nrouter_post / _nrouter_get / _nrouter_get_bytes
    posted = []
    getted = []
    getted_bytes = []

    def mock_post(path, json=None):
        posted.append((path, json))
        return {"status": "ok", "path": path}

    def mock_get(path):
        getted.append(path)
        return {"id": "vid_123", "status": "completed"}

    def mock_get_bytes(path):
        getted_bytes.append(path)
        return b"fake_mp4_bytes"

    monkeypatch.setattr(client, "_nrouter_post", mock_post)
    monkeypatch.setattr(client, "_nrouter_get", mock_get)
    monkeypatch.setattr(client, "_nrouter_get_bytes", mock_get_bytes)

    # Messages create
    res = client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
    )
    assert res["status"] == "ok"
    assert posted[0][0] == "/v1/messages"

    # Messages stream=True refusal
    with pytest.raises(NotImplementedError):
        client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            stream=True,
        )

    # Messages count_tokens
    client.messages.count_tokens(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert posted[1][0] == "/v1/messages/count_tokens"

    # Videos create, retrieve, download_content
    v_res = client.videos.create(model="veo-2", prompt="sunset")
    assert v_res["status"] == "ok"
    assert posted[2][0] == "/v1/videos"

    v_get = client.videos.retrieve("vid_123/special")
    assert v_get["id"] == "vid_123"
    assert getted[0] == "/v1/videos/vid_123%2Fspecial"

    v_bytes = client.videos.download_content("vid_123/special")
    assert v_bytes == b"fake_mp4_bytes"
    assert getted_bytes[0] == "/v1/videos/vid_123%2Fspecial/content"


@pytest.mark.asyncio
async def test_async_messages_and_videos_endpoints(monkeypatch):
    client = AsyncnRouter(api_key="sk-nrouter-test")

    posted = []
    getted = []
    getted_bytes = []

    async def mock_post(path, json=None):
        posted.append((path, json))
        return {"status": "ok", "path": path}

    async def mock_get(path):
        getted.append(path)
        return {"id": "vid_456", "status": "completed"}

    async def mock_get_bytes(path):
        getted_bytes.append(path)
        return b"fake_async_mp4_bytes"

    monkeypatch.setattr(client, "_nrouter_post", mock_post)
    monkeypatch.setattr(client, "_nrouter_get", mock_get)
    monkeypatch.setattr(client, "_nrouter_get_bytes", mock_get_bytes)

    # Messages create
    res = await client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
    )
    assert res["status"] == "ok"
    assert posted[0][0] == "/v1/messages"

    # Messages stream=True refusal
    with pytest.raises(NotImplementedError):
        await client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            stream=True,
        )

    # Messages count_tokens
    await client.messages.count_tokens(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert posted[1][0] == "/v1/messages/count_tokens"

    # Videos create, retrieve, download_content
    v_res = await client.videos.create(model="veo-2", prompt="ocean")
    assert v_res["status"] == "ok"
    assert posted[2][0] == "/v1/videos"

    v_get = await client.videos.retrieve("vid_456")
    assert v_get["id"] == "vid_456"
    assert getted[0] == "/v1/videos/vid_456"

    v_bytes = await client.videos.download_content("vid_456")
    assert v_bytes == b"fake_async_mp4_bytes"
    assert getted_bytes[0] == "/v1/videos/vid_456/content"


def test_error_interceptor_branches(monkeypatch):
    from openai import APIStatusError

    # 1. Non-dict JSON body
    mock_resp = httpx.Response(
        status_code=400,
        headers={"x-nr-request-id": "req_1"},
        json=["not", "a", "dict"],
        request=httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions"),
    )
    err = APIStatusError("bad", response=mock_resp, body=["not", "a", "dict"])
    _maybe_raise_nrouter_error(err)  # does not raise

    # 2. String error in JSON body
    mock_resp2 = httpx.Response(
        status_code=401,
        headers={"x-nr-request-id": "req_2", "x-nr-auth-reason": "revoked_key"},
        json={"error": "Simple error message"},
        request=httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions"),
    )
    err2 = APIStatusError("bad", response=mock_resp2, body={"error": "Simple error message"})
    with pytest.raises(nRouterAuthenticationError) as exc_info:
        _maybe_raise_nrouter_error(err2)
    assert exc_info.value.auth_reason == "revoked_key"
    assert exc_info.value.request_id == "req_2"

    # 3. credit_check_failed and service_unavailable with explicit code
    mock_resp3 = httpx.Response(
        status_code=503,
        headers={},
        json={"error": {"code": "credit_check_failed", "message": "credit backend down"}},
        request=httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions"),
    )
    err3 = APIStatusError("503", response=mock_resp3, body=mock_resp3.json())
    with pytest.raises(nRouterServiceError) as exc_info3:
        _maybe_raise_nrouter_error(err3)
    assert exc_info3.value.code == "credit_check_failed"

    # 4. Unknown code on 503 stays generic nRouterError with the exact code
    mock_resp4 = httpx.Response(
        status_code=503,
        headers={},
        json={"error": {"code": "new_unseen_code", "message": "future reason"}},
        request=httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions"),
    )
    err4 = APIStatusError("503", response=mock_resp4, body=mock_resp4.json())
    with pytest.raises(nRouterError) as exc_info4:
        _maybe_raise_nrouter_error(err4)
    assert exc_info4.value.code == "new_unseen_code"

    # 5. Non-dict non-str error field in JSON body
    mock_resp5 = httpx.Response(
        status_code=400,
        headers={},
        json={"error": 12345},
        request=httpx.Request("POST", "https://api.nrouter.ai/v1/chat/completions"),
    )
    err5 = APIStatusError("400", response=mock_resp5, body=mock_resp5.json())
    with pytest.raises(nRouterRequestError):
        _maybe_raise_nrouter_error(err5)


def test_client_nrouter_helpers_sync_and_async(monkeypatch):
    client = nRouter(api_key="sk-nrouter-test")
    async_client = AsyncnRouter(api_key="sk-nrouter-test")

    json_resp = httpx.Response(
        status_code=200,
        json={"status": "ok"},
        request=httpx.Request("GET", "https://api.nrouter.ai/v1/models"),
    )
    bytes_resp = httpx.Response(
        status_code=200,
        content=b"bytes_content",
        request=httpx.Request("GET", "https://api.nrouter.ai/v1/models"),
    )

    # Test _raise_for_status on success
    client._raise_for_status(json_resp)
    async_client._raise_for_status(json_resp)

    # Test direct _nrouter_get / _nrouter_post on client._client
    monkeypatch.setattr(
        client._client,
        "get",
        lambda path, **kwargs: bytes_resp if "content" in path or "bytes" in path else json_resp,
    )
    monkeypatch.setattr(client._client, "post", lambda path, **kwargs: json_resp)

    assert client._nrouter_get("/test") == {"status": "ok"}
    assert client._nrouter_post("/test", json={"a": 1}) == {"status": "ok"}
    assert client._nrouter_get_bytes("/test/content") == b"bytes_content"

    # Async equivalents
    async def async_get(path, **kwargs):
        return bytes_resp if "content" in path or "bytes" in path else json_resp

    async def async_post(path, **kwargs):
        return json_resp

    monkeypatch.setattr(async_client._client, "get", async_get)
    monkeypatch.setattr(async_client._client, "post", async_post)

    import asyncio

    assert asyncio.run(async_client._nrouter_get("/test")) == {"status": "ok"}
    assert asyncio.run(async_client._nrouter_post("/test", json={"a": 1})) == {"status": "ok"}
    assert asyncio.run(async_client._nrouter_get_bytes("/test/content")) == b"bytes_content"

    # Test _raise_for_status on failure
    fail_resp = httpx.Response(
        status_code=401,
        json={"error": {"type": "gateway_error", "message": "invalid key"}},
        request=httpx.Request("GET", "https://api.nrouter.ai/v1/models"),
    )
    with pytest.raises(nRouterAuthenticationError):
        client._raise_for_status(fail_resp)
    with pytest.raises(nRouterAuthenticationError):
        async_client._raise_for_status(fail_resp)


@pytest.mark.asyncio
async def test_nrouter_chat_helper_dispatch(monkeypatch):
    client = nRouter(api_key="sk-nrouter-test")

    def mock_create(*args, **kwargs):
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(client.chat.completions, "create", mock_create)

    res = client.nrouter.chat(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        prompt_template_id="tpl_x",
        prompt_variables={"name": "Ada"},
        cache=False,
        advanced_sampling=True,
        temperature=0.7,
    )
    assert res == {"choices": [{"message": {"content": "ok"}}]}
