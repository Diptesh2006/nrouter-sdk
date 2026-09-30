"""Tests for model constants and references in the Python SDK."""

from __future__ import annotations

from nroutersdk import (
    MODELS,
    MODEL_META_LLAMA_3_3_70B_INSTRUCT,
    MODEL_META_LLAMA_3_1_70B_INSTRUCT,
    MODEL_TYPESAFE_JEV,
    MODEL_TYPESAFE_JEV_SYSTEM_ONE,
)
from nroutersdk.models import (
    MODEL_GPT_5_4_MINI,
    MODEL_CLAUDE_SONNET_4_5,
)


def test_meta_llama_constants():
    assert MODEL_META_LLAMA_3_3_70B_INSTRUCT == "meta/llama-3.3-70b-instruct"
    assert MODEL_META_LLAMA_3_1_70B_INSTRUCT == "meta/llama-3.1-70b-instruct"
    assert MODELS["META_LLAMA_3_3_70B_INSTRUCT"] == "meta/llama-3.3-70b-instruct"


def test_typesafe_jev_constants():
    assert MODEL_TYPESAFE_JEV == "typesafe/jev"
    assert MODEL_TYPESAFE_JEV_SYSTEM_ONE == "typesafe/jev"
    assert MODELS["TYPESAFE_JEV"] == "typesafe/jev"
    assert MODELS["TYPESAFE_JEV_SYSTEM_ONE"] == "typesafe/jev"


def test_models_dictionary_contains_canonical_models():
    assert MODELS["GPT_5_4_MINI"] == MODEL_GPT_5_4_MINI
    assert MODELS["CLAUDE_SONNET_4_5"] == MODEL_CLAUDE_SONNET_4_5
