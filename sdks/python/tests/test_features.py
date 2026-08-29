from __future__ import annotations

import pytest

from nroutersdk import (
    apply_prompt,
    build_sampling_params,
    create_memory,
    prompt_extra_body,
    prompt_template,
    prompt_variables,
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
    assert build_sampling_params(
        advanced=False,
        model="anthropic/claude-sonnet",
        temperature=0.7,
        top_p=0.5,
    ) == {}
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
    assert build_sampling_params(
        advanced=False,
        model="x",
        top_p=2,
    ) == {}
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
