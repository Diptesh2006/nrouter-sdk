"""Tests for uses_messages_wire in the Python SDK."""

import pytest
from nroutersdk import uses_messages_wire


def test_uses_messages_wire_identifies_claude_family():
    assert uses_messages_wire("claude-3-5-sonnet-20241022") is True
    assert uses_messages_wire("anthropic/claude-3-haiku") is True
    assert uses_messages_wire("claude-opus-4-6") is True
    assert uses_messages_wire("anthropic.claude-v2") is True


def test_uses_messages_wire_identifies_provider_attribution():
    assert uses_messages_wire("my-custom-model", provider="anthropic") is True
    assert uses_messages_wire("my-custom-model", provider="Anthropic") is True


def test_uses_messages_wire_returns_false_for_openai_and_other_families():
    assert uses_messages_wire("gpt-4o") is False
    assert uses_messages_wire("gpt-5.4-mini") is False
    assert uses_messages_wire("meta-llama/llama-3-70b") is False
    assert uses_messages_wire("mistralai/mistral-large") is False
    assert uses_messages_wire("bedrock/amazon.titan-text-express-v1", provider="bedrock") is False


def test_is_claude_model_aliases():
    from nroutersdk.sampling import is_claude_model
    assert is_claude_model("sonnet-4-5") is True
    assert is_claude_model("haiku-3-5") is True
    assert is_claude_model("opus-4") is True
    assert is_claude_model("us.anthropic.claude-sonnet-4-6-v1:0") is True
    assert is_claude_model("gpt-4o") is False

