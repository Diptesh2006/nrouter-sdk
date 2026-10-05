"""Model Context Protocol (MCP) support for the nRouter Python SDK.

Enables listing tools and invoking tool calls on remote MCP servers fronted
by the nRouter Gateway via POST /mcp and POST /mcp/{server_id}.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from nroutersdk._errors import nRouterRequestError, nRouterServiceError

if TYPE_CHECKING:
    from nroutersdk.client import AsyncnRouter, nRouter


class _MCP:
    """Synchronous client resource for Model Context Protocol (MCP) servers."""

    def __init__(self, client: nRouter) -> None:
        self._client = client

    def list(self, server_id: str | None = None) -> list[dict[str, Any]]:
        """List the tools an MCP server exposes.

        Args:
            server_id: The identifier of the server, or None when only one is configured.
        """
        res = self.rpc("tools/list", {}, server_id=server_id)
        tools = res.get("tools")
        return tools if isinstance(tools, list) else []

    def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        server_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke an MCP tool on the specified or default MCP server.

        Args:
            name: The tool name to invoke (e.g. 'execute_sql', 'get_dataset_info').
            arguments: The arguments dictionary matching the tool's input schema.
            server_id: Optional MCP server ID (e.g. 'bigquery-gcp').
        """
        return self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            server_id=server_id,
        )

    def rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        server_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request to an MCP server fronted by the gateway."""
        path = f"/mcp/{quote(server_id)}" if server_id else "/mcp"
        url = f"{self._client._nrouter_base}{path}"
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {},
        }
        res = self._client._client.post(
            url,
            json=payload,
            headers=self._client._nrouter_headers,
        )

        if res.status_code != 200:
            raise nRouterServiceError(
                f"MCP request failed with HTTP {res.status_code}: {res.text}",
                status_code=res.status_code,
            )

        data = res.json()
        if "error" in data and data["error"] is not None:
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise nRouterRequestError(f"MCP {method} failed: {msg}")

        return data.get("result", {})


class _AsyncMCP:
    """Asynchronous client resource for Model Context Protocol (MCP) servers."""

    def __init__(self, client: AsyncnRouter) -> None:
        self._client = client

    async def list(self, server_id: str | None = None) -> list[dict[str, Any]]:
        """List the tools an MCP server exposes asynchronously."""
        res = await self.rpc("tools/list", {}, server_id=server_id)
        tools = res.get("tools")
        return tools if isinstance(tools, list) else []

    async def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        server_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke an MCP tool asynchronously."""
        return await self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            server_id=server_id,
        )

    async def rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        server_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request asynchronously."""
        path = f"/mcp/{quote(server_id)}" if server_id else "/mcp"
        url = f"{self._client._nrouter_base}{path}"
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {},
        }
        res = await self._client._client.post(
            url,
            json=payload,
            headers=self._client._nrouter_headers,
        )

        if res.status_code != 200:
            raise nRouterServiceError(
                f"MCP request failed with HTTP {res.status_code}: {res.text}",
                status_code=res.status_code,
            )

        data = res.json()
        if "error" in data and data["error"] is not None:
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise nRouterRequestError(f"MCP {method} failed: {msg}")

        return data.get("result", {})
