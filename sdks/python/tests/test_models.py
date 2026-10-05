"""Tests for model constants and references in the Python SDK."""

from __future__ import annotations

from nroutersdk import (
    MODELS,
    MODEL_META_LLAMA_3_3_70B_INSTRUCT,
    MODEL_META_LLAMA_3_1_70B_INSTRUCT,
    MODEL_TYPESAFE_JEV,
    MODEL_TYPESAFE_JEV_SYSTEM_ONE,
    MODEL_GOOGLE_GEMINI_2_0_FLASH,
    MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE,
    MODEL_GOOGLE_GEMINI_1_5_PRO_002,
    MODEL_GOOGLE_GEMINI_1_5_FLASH_002,
    MODEL_GEMINI_2_0_FLASH,
    MODEL_GEMINI_2_0_FLASH_LITE,
    MODEL_GEMINI_1_5_PRO_002,
    MODEL_GEMINI_1_5_FLASH_002,
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


def test_gemini_constants():
    assert MODEL_GOOGLE_GEMINI_2_0_FLASH == "google/gemini-2.0-flash"
    assert MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE == "google/gemini-2.0-flash-lite"
    assert MODEL_GOOGLE_GEMINI_1_5_PRO_002 == "google/gemini-1.5-pro-002"
    assert MODEL_GOOGLE_GEMINI_1_5_FLASH_002 == "google/gemini-1.5-flash-002"

    assert MODEL_GEMINI_2_0_FLASH == "google/gemini-2.0-flash"
    assert MODEL_GEMINI_2_0_FLASH_LITE == "google/gemini-2.0-flash-lite"
    assert MODEL_GEMINI_1_5_PRO_002 == "google/gemini-1.5-pro-002"
    assert MODEL_GEMINI_1_5_FLASH_002 == "google/gemini-1.5-flash-002"

    assert MODELS["GOOGLE_GEMINI_2_0_FLASH"] == "google/gemini-2.0-flash"
    assert MODELS["GOOGLE_GEMINI_2_0_FLASH_LITE"] == "google/gemini-2.0-flash-lite"
    assert MODELS["GOOGLE_GEMINI_1_5_PRO_002"] == "google/gemini-1.5-pro-002"
    assert MODELS["GOOGLE_GEMINI_1_5_FLASH_002"] == "google/gemini-1.5-flash-002"
    assert MODELS["GEMINI_2_0_FLASH"] == "google/gemini-2.0-flash"
    assert MODELS["GEMINI_2_0_FLASH_LITE"] == "google/gemini-2.0-flash-lite"
    assert MODELS["GEMINI_1_5_PRO_002"] == "google/gemini-1.5-pro-002"
    assert MODELS["GEMINI_1_5_FLASH_002"] == "google/gemini-1.5-flash-002"


def test_models_dictionary_contains_canonical_models():
    assert MODELS["GPT_5_4_MINI"] == MODEL_GPT_5_4_MINI
    assert MODELS["CLAUDE_SONNET_4_5"] == MODEL_CLAUDE_SONNET_4_5
