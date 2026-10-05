"""Tests for Model Context Protocol (MCP) support in the nRouter Python SDK."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from nroutersdk import AsyncnRouter, nRouter, nRouterRequestError, nRouterServiceError
from nroutersdk.mcp import _MCP, _AsyncMCP

KEY = "sk-nrouter-test-only-not-a-real-key"


@pytest.fixture
def client():
    c = nRouter(api_key=KEY, base_url="http://127.0.0.1:4000/v1")
    yield c
    c.close()


@pytest.fixture
def async_client():
    c = AsyncnRouter(api_key=KEY, base_url="http://127.0.0.1:4000/v1")
    yield c


def test_mcp_attribute_present(client, async_client):
    """Verify client.mcp is mounted and instantiated properly."""
    assert hasattr(client, "mcp")
    assert isinstance(client.mcp, _MCP)
    assert hasattr(async_client, "mcp")
    assert isinstance(async_client.mcp, _AsyncMCP)


def test_mcp_list_tools_sync(client):
    """Test sync client.mcp.list() sends JSON-RPC tools/list."""
    mock_tools = [
        {"name": "execute_sql", "description": "Run BigQuery SQL"},
        {"name": "get_table_info", "description": "Fetch schema"},
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": mock_tools},
    }

    with patch.object(client._client, "post", return_value=mock_response) as mock_post:
        tools = client.mcp.list(server_id="bigquery-gcp")

        assert tools == mock_tools
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://127.0.0.1:4000/mcp/bigquery-gcp"
        assert kwargs["json"]["method"] == "tools/list"


def test_mcp_call_tool_sync(client):
    """Test sync client.mcp.call() invokes tools/call with arguments."""
    mock_result = {
        "content": [{"type": "text", "text": "Dataset count: 3"}],
        "isError": False,
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": mock_result,
    }

    with patch.object(client._client, "post", return_value=mock_response) as mock_post:
        res = client.mcp.call(
            "execute_sql",
            {"query": "SELECT count(*) FROM datasets"},
            server_id="bigquery-gcp",
        )

        assert res == mock_result
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://127.0.0.1:4000/mcp/bigquery-gcp"
        assert kwargs["json"]["method"] == "tools/call"
        assert kwargs["json"]["params"] == {
            "name": "execute_sql",
            "arguments": {"query": "SELECT count(*) FROM datasets"},
        }


def test_mcp_unwraps_json_rpc_error(client):
    """Test that JSON-RPC errors returned with HTTP 200 are unwrapped into nRouterRequestError."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32601, "message": "Method not found"},
    }

    with patch.object(client._client, "post", return_value=mock_response):
        with pytest.raises(nRouterRequestError, match="Method not found"):
            client.mcp.rpc("unknown_method", {})


@pytest.mark.asyncio
async def test_mcp_list_and_call_async(async_client):
    """Test async client.mcp.list() and client.mcp.call()."""
    mock_tools = [{"name": "list_datasets"}]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": mock_tools},
    }

    with patch.object(async_client._client, "post", AsyncMock(return_value=mock_response)) as mock_post:
        tools = await async_client.mcp.list("bigquery-gcp")
        assert tools == mock_tools
        mock_post.assert_called_once()
