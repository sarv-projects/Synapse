"""MCP tool registry — exposes MCP servers' tools as LangChain-compatible callables.

This module wraps :class:`MCPClientManager` so the rest of the system can use
MCP tools (Memory, Sequential Thinking, Filesystem) via a uniform interface.
When the ``mcp`` package is not installed or the configured server
binaries are missing, placeholder stub tools are returned so the rest
of the pipeline keeps working.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


# ── LangChain-compatible shims ──────────────────────────────────────────────
#
# We don't want to make `langchain` a hard dependency for tooling. So when a
# real LangChain ``BaseTool`` is requested we provide a thin adapter that
# duck-types the interface: ``name``, ``description``, ``args`` and ``_run``.


class _StubLangChainTool:
    """Minimal duck-typed LangChain tool that delegates to an async callable.

    Compatible with both the legacy LangChain ``BaseTool`` interface and the
    modern ``@tool`` decorator style.  When :class:`mcp.MCPClientManager` is
    unavailable, the ``_run`` method returns a descriptive string instead of
    raising — callers can still list and route tools.
    """

    def __init__(self, name: str, description: str, server_name: str, tool_name: str):
        self.name = name
        self.description = description
        self._server_name = server_name
        self._tool_name = tool_name

    def _run(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - thin shim
        return f"[MCP:{self._server_name}:{self._tool_name}] sync calls not supported, use async"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        from mcp.client import get_mcp_manager

        try:
            manager = get_mcp_manager()
            return await manager.call_tool(
                f"{self._server_name}.{self._tool_name}", **{k: v for k, v in kwargs.items() if not k.startswith("_")}
            )
        except Exception as e:  # noqa: BLE001 — surface to caller, not logs
            logger.error("MCP tool call %s failed: %s", self.name, e, exc_info=True)
            return f"[MCP:{self._server_name}:{self._tool_name}] error: {e}"


def _build_tool(server_name: str, tool_name: str, description: str = "") -> _StubLangChainTool:
    return _StubLangChainTool(
        name=f"{server_name}.{tool_name}",
        description=description or f"MCP tool {tool_name} on {server_name} server",
        server_name=server_name,
        tool_name=tool_name,
    )


# ── Public API ──────────────────────────────────────────────────────────────


def register_mcp_tools() -> list:
    """Return MCP tools wrapped as LangChain-compatible tool objects.

    Returns an empty list when the ``mcp`` package is not installed or no
    servers are configured.  Callers should treat this as "no tools
    available" rather than an error.
    """
    from mcp.client import MCP_AVAILABLE, get_mcp_manager

    if not MCP_AVAILABLE:
        logger.info("MCP package not installed; registering placeholder stubs")
        return [
            _build_tool("memory", "write", "Persist a memory item to the memory server"),
            _build_tool("memory", "read", "Read memory items by query"),
            _build_tool("sequential_thinking", "reason", "Run sequential reasoning steps"),
            _build_tool("filesystem", "read", "Read a file from the configured filesystem"),
            _build_tool("filesystem", "write", "Write a file to the configured filesystem"),
        ]

    try:
        manager = get_mcp_manager()
        schemas = manager.get_tool_schemas()
        logger.info("Registered %d MCP tool stubs from live manager", len(schemas))
        return [_build_tool(name, tool, f"Live MCP tool {tool}") for name, tool in _parse_schemas(schemas)]
    except Exception as e:
        logger.error("Failed to enumerate MCP tools: %s", e, exc_info=True)
        return []


def _parse_schemas(schemas: List[str]) -> list[tuple[str, str]]:
    """Parse dotted ``server.tool`` strings, ignoring malformed entries."""
    out: list[tuple[str, str]] = []
    for s in schemas:
        if not isinstance(s, str) or "." not in s:
            continue
        server, _, tool = s.partition(".")
        if server and tool:
            out.append((server, tool))
    return out


def get_registered_tools() -> Dict[str, Callable[..., Any]]:
    """Return a name → callable mapping for runtime tool invocation.

    Each callable is async and accepts arbitrary ``**kwargs``.  When the
    underlying MCP server is unavailable, the callable returns a
    descriptive string instead of raising.
    """
    from mcp.client import get_mcp_manager

    manager = get_mcp_manager()
    tools: Dict[str, Callable[..., Any]] = {}

    for server, tool in _parse_schemas(manager.get_tool_schemas()):
        async def _call(*, _server: str = server, _tool: str = tool, **kwargs: Any) -> str:
            try:
                return await manager.call_tool(f"{_server}.{_tool}", **kwargs)
            except Exception as e:  # noqa: BLE001
                logger.error("MCP call %s.%s failed: %s", _server, _tool, e, exc_info=True)
                return f"[MCP:{_server}:{_tool}] error: {e}"

        tools[f"{server}.{tool}"] = _call

    return tools


def list_registered_tools() -> List[str]:
    """Return the list of MCP tool names currently available."""
    try:
        from mcp.client import get_mcp_manager
        return get_mcp_manager().get_tool_schemas()
    except Exception as e:  # noqa: BLE001
        logger.error("Could not list MCP tools: %s", e, exc_info=True)
        return []


__all__ = [
    "register_mcp_tools",
    "get_registered_tools",
    "list_registered_tools",
]
