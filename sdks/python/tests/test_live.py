"""Opt-in billed acceptance test against the local nRouter gateway."""

from __future__ import annotations

import os

import pytest

from nroutersdk import nRouter


pytestmark = pytest.mark.skipif(
    os.getenv("NROUTER_LIVE") != "1",
    reason="set NROUTER_LIVE=1 to run the billed local-gateway acceptance",
)


def test_live_claude_messages_returns_billing_metadata():
    with nRouter(
        api_key=os.environ["NROUTER_API_KEY"],
        base_url=os.getenv("NROUTER_BASE_URL", "http://127.0.0.1:4000/v1"),
        max_retries=0,
    ) as client:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2,
            messages=[{"role": "user", "content": "Reply OK"}],
        )
        assert response["content"]
        assert client.last_response is not None
        assert client.last_response.request_id
        assert client.last_response.cost_status == "exact"
        assert client.last_response.cost is not None
        assert client.last_response.cost > 0
