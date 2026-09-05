from __future__ import annotations

import pytest

from nroutersdk import (
    apply_prompt,
    build_sampling_params,
    create_memory,
    prompt_extra_body,
    prompt_template,
    prompt_variables,
    parse_sse,
    render_prompt,
    system_variable_conflicts,
    with_variables,
)
from nroutersdk._errors import nRouterRequestError
from nroutersdk._options import build_extra_body, vet_extra


def test_prompt_selection_maps_to_gateway_fields():
    selection = prompt_template("  tpl_123  ", {"name": "Ada"})
    assert prompt_extra_body(selection) == {
        "nrouter_prompt_template_id": "tpl_123",
        "nrouter_prompt_variables": {"name": "Ada"},
    }


def test_variables_only_is_a_supported_prompt_selection():
    assert prompt_extra_body(prompt_variables({"name": "Ada"})) == {
        "nrouter_prompt_variables": {"name": "Ada"}
    }


def test_prompt_helpers_do_not_mutate_inputs():
    selection = prompt_template("tpl", {"a": "1"})
    merged = with_variables(selection, {"a": "2", "b": "3"})
    assert selection.variables == {"a": "1"}
    assert merged.variables == {"a": "2", "b": "3"}
    assert apply_prompt({"prompt_variables": {"a": "0"}}, merged)["prompt_variables"] == {
        "a": "2",
        "b": "3",
    }


def test_empty_prompt_id_is_refused():
    with pytest.raises(nRouterRequestError):
        prompt_template("  ")


def test_guardrail_ids_are_refused_and_cache_true_is_omitted():
    with pytest.raises(nRouterRequestError, match="guardrail_ids"):
        build_extra_body(guardrail_ids=["gr_1"])
    assert build_extra_body(cache=True) == {}
    assert build_extra_body(cache=False) == {"nrouter_cache": False}


def test_extra_body_tenancy_fields_are_refused():
    with pytest.raises(nRouterRequestError, match="tenancy"):
        vet_extra({"organization_id": "spoof"})


def test_sampling_policy_matches_claude_top_p_rule():
    assert (
        build_sampling_params(
            advanced=False,
            model="anthropic/claude-sonnet",
            temperature=0.7,
            top_p=0.5,
        )
        == {}
    )
    assert build_sampling_params(
        advanced=True,
        model="anthropic/claude-sonnet",
        temperature=0.7,
        top_p=0.5,
    ) == {"top_p": 0.5}
    assert build_sampling_params(
        advanced=True,
        model="openai/gpt-5",
        temperature=0.7,
        top_p=0.5,
    ) == {"temperature": 0.7, "top_p": 0.5}
    assert build_sampling_params(
        advanced=True,
        model="openai/gpt-5",
        temperature=0.7,
        top_p=1,
    ) == {"temperature": 0.7}


def test_bad_sampling_values_are_refused_only_when_advanced():
    assert (
        build_sampling_params(
            advanced=False,
            model="x",
            top_p=2,
        )
        == {}
    )
    with pytest.raises(nRouterRequestError):
        build_sampling_params(advanced=True, model="x", top_p=2)


@pytest.mark.asyncio
async def test_memory_stores_copies_and_refuses_tenancy_fields():
    memory = create_memory()
    message = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    await memory.add(message)
    message["content"][0]["text"] = "changed"
    stored = await memory.messages()
    assert stored == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    stored[0]["content"][0]["text"] = "mutated"
    assert (await memory.messages())[0]["content"][0]["text"] == "hi"

    with pytest.raises(nRouterRequestError):
        await memory.add({"role": "user", "content": "hi", "team_id": "team"})


def test_system_variable_conflicts_are_in_gateway_order():
    assert system_variable_conflicts({"model": "fake", "org_name": "fake"}) == [
        "org_name",
        "model",
    ]


@pytest.mark.asyncio
async def test_memory_accepts_tool_and_developer_roles():
    memory = create_memory()
    await memory.add({"role": "developer", "content": "instructions"})
    await memory.add({"role": "user", "content": "calc"})
    await memory.add({"role": "tool", "tool_call_id": "c1", "content": "42"})
    msgs = await memory.messages()
    assert len(msgs) == 3
    assert msgs[0]["role"] == "developer"
    assert msgs[1]["role"] == "user"
    assert msgs[2]["role"] == "tool"


@pytest.mark.asyncio
async def test_memory_accepts_assistant_null_content_with_tool_calls():
    memory = create_memory()
    await memory.add({
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
    })
    msgs = await memory.messages()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"] is None
    assert len(msgs[0]["tool_calls"]) == 1


def test_sliding_window_preserves_system_prompt():
    from nroutersdk.memory import sliding_window

    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
    ]
    pruned = sliding_window(msgs, max_messages=3, preserve_system=True)
    assert len(pruned) == 3
    assert pruned[0]["role"] == "system"
    assert pruned[0]["content"] == "sys"
    assert pruned[1]["content"] == "3"
    assert pruned[2]["content"] == "4"


@pytest.mark.asyncio
async def test_memory_messages_sliding_window():
    memory = create_memory()
    await memory.add({"role": "system", "content": "sys"})
    await memory.add({"role": "user", "content": "1"})
    await memory.add({"role": "assistant", "content": "2"})
    windowed = await memory.messages(max_messages=2, preserve_system=True)
    assert len(windowed) == 2
    assert windowed[0]["role"] == "system"
    assert windowed[1]["content"] == "2"
    assert len(await memory.messages()) == 3


def test_render_prompt_whitespace_and_types():
    tpl = "Hello {{name}}! Age: {{  age  }}, active: {{ active }}."
    out = render_prompt(tpl, {"name": "Alice", "age": 30, "active": True})
    assert out == "Hello Alice! Age: 30, active: True."


def test_render_prompt_prevents_recursive_expansion():
    tpl = "Expanded: {{a}}"
    out = render_prompt(tpl, {"a": "{{b}}", "b": "final"})
    assert out == "Expanded: {{b}}"


def test_render_prompt_regex_backreference_safety():
    tpl = "Path: {{win_path}}, Price: {{price}}"
    # \1 or \g<...> in values must not be processed as regex escapes
    out = render_prompt(tpl, {"win_path": r"C:\test\1\new", "price": "$100"})
    assert out == r"Path: C:\test\1\new, Price: $100"


def test_render_prompt_non_strict_and_strict():
    tpl = "Greeting: {{hello}}, missing: {{world}}"
    assert render_prompt(tpl, {"hello": "hi"}) == "Greeting: hi, missing: {{world}}"

    with pytest.raises(nRouterRequestError, match="world"):
        render_prompt(tpl, {"hello": "hi"}, strict=True)


def test_render_prompt_system_variables_precedence():
    tpl = "Model: {{model}}, Caller: {{user}}"
    out = render_prompt(
        tpl,
        {"model": "caller-model", "user": "alice"},
        system_variables={"model": "claude-3-7-sonnet"},
    )
    assert out == "Model: claude-3-7-sonnet, Caller: alice"


def test_parse_sse_robustness():
    raw = (
        ": keep-alive\r\r"
        "data: ping\r\r"
        "event: content_block_delta\n"
        "data: line1\n"
        "data:   indented_line2\n\n"
        "data: [DONE]"
    )
    events = parse_sse(raw)
    assert len(events) == 3
    assert events[0] == {"data": "ping"}
    assert events[1] == {
        "event": "content_block_delta",
        "data": "line1\n  indented_line2",
    }
    assert events[2] == {"data": "[DONE]"}


def test_cleartext_is_limited_to_loopback_and_rejects_credentials():
    from nroutersdk.client import _resolve_base_url

    for allowed in [
        "http://127.0.0.1:4000/v1",
        "http://[::1]:4000/v1",
        "http://localhost:4000/v1",
        "https://api.nrouter.ai/v1",
    ]:
        assert _resolve_base_url(allowed) == allowed.rstrip("/")

    for refused in [
        "http://api.nrouter.ai/v1",
        "http://192.0.2.10:4000/v1",
        "ftp://127.0.0.1/v1",
        "https://user:pass@api.nrouter.ai/v1",
        "not-a-url",
    ]:
        with pytest.raises(ValueError):
            _resolve_base_url(refused)



