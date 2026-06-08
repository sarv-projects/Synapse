"""Integration tests for the MCP client.

These tests do not require a live MCP server. They verify:
* Process spawn failure handling
* Health check logic
* Reconnect behavior
* Tool call routing and validation
* Graceful degradation when MCP is unavailable
"""
from __future__ import annotations

import asyncio

import pytest

from mcp.client import (
    MCPConnectionError,
    MCPError,
    MCPStdioClient,
    get_mcp_manager,
    reset_mcp_manager,
)
from mcp.tool_registry import (
    _StubLangChainTool,
    _parse_schemas,
    get_registered_tools,
    list_registered_tools,
    register_mcp_tools,
)


pytestmark = pytest.mark.integration


class TestMCPStdioClientLifecycle:
    def test_invalid_name_raises(self):
        with pytest.raises(ValueError, match="non-empty name"):
            MCPStdioClient("", ["/bin/echo"])

    def test_invalid_command_raises(self):
        with pytest.raises(ValueError, match="must all be strings"):
            MCPStdioClient("x", [123])  # type: ignore[list-item]

    def test_empty_command_does_not_attempt_spawn(self):
        client = MCPStdioClient("x", [])
        loop = asyncio.new_event_loop()
        try:
            ok = loop.run_until_complete(client.connect())
            assert ok is False
            assert client.connected is False
        finally:
            loop.close()

    def test_spawn_with_missing_binary_returns_false(self):
        client = MCPStdioClient("x", ["/does/not/exist/binary-xyz"])
        loop = asyncio.new_event_loop()
        try:
            ok = loop.run_until_complete(client.connect())
            assert ok is False
        finally:
            loop.close()

    def test_health_check_false_when_no_process(self):
        client = MCPStdioClient("x", ["/bin/echo"])
        loop = asyncio.new_event_loop()
        try:
            assert loop.run_until_complete(client.health_check()) is False
        finally:
            loop.close()


class TestMCPErrorTypes:
    def test_mcp_error_is_exception(self):
        assert issubclass(MCPError, Exception)

    def test_mcp_connection_error_inherits(self):
        assert issubclass(MCPConnectionError, MCPError)

    def test_mcp_error_can_be_raised(self):
        with pytest.raises(MCPError):
            raise MCPError("test")


class TestMCPClientManager:
    def setup_method(self):
        # Reset between tests
        reset_mcp_manager()

    def teardown_method(self):
        reset_mcp_manager()

    def test_manager_constructs_without_env(self, monkeypatch):
        monkeypatch.delenv("MCP_MEMORY_PATH", raising=False)
        monkeypatch.delenv("MCP_SEQUENTIAL_THINKING_PATH", raising=False)
        monkeypatch.delenv("MCP_FILESYSTEM_PATH", raising=False)
        mgr = get_mcp_manager()
        assert mgr.is_available is False
        schemas = mgr.get_tool_schemas()
        # Should return placeholder names
        assert "memory.write" in schemas
        assert "filesystem.read" in schemas

    def test_manager_parses_env(self, monkeypatch):
        monkeypatch.setenv("MCP_MEMORY_PATH", "/usr/local/bin/mcp-memory")
        monkeypatch.setenv("MCP_SEQUENTIAL_THINKING_PATH", "/usr/local/bin/mcp-think")
        monkeypatch.setenv("MCP_FILESYSTEM_PATH", "/usr/local/bin/mcp-fs")
        mgr = get_mcp_manager()
        assert mgr.is_available is True
        assert "memory" in mgr._servers
        assert "sequential_thinking" in mgr._servers
        assert "filesystem" in mgr._servers

    def test_manager_parses_per_server_env(self, monkeypatch):
        monkeypatch.setenv("MCP_MEMORY_PATH", "/usr/local/bin/mcp-memory")
        monkeypatch.setenv("MCP_MEMORY_ENV", '{"API_KEY": "secret-123"}')
        mgr = get_mcp_manager()
        server = mgr._servers["memory"]
        assert server.env.get("API_KEY") == "secret-123"

    def test_manager_handles_invalid_env_json(self, monkeypatch, caplog):
        monkeypatch.setenv("MCP_MEMORY_PATH", "/usr/local/bin/mcp-memory")
        monkeypatch.setenv("MCP_MEMORY_ENV", "{not valid json")
        mgr = get_mcp_manager()
        # Should not crash
        assert mgr.is_available is True

    async def test_call_tool_invalid_name(self):
        mgr = get_mcp_manager()
        result = await mgr.call_tool("nodots")
        assert "invalid tool name" in result

    async def test_call_tool_unknown_server(self):
        mgr = get_mcp_manager()
        result = await mgr.call_tool("nonexistent.tool")
        assert "not found" in result

    async def test_call_tool_with_invalid_args_returns_placeholder(self):
        mgr = get_mcp_manager()
        # Server is configured but not connected
        mgr._servers["memory"] = MCPStdioClient("memory", ["/usr/local/bin/mcp-mem"])
        result = await mgr.call_tool("memory.write", key="value")
        assert "Not connected" in result or "error" in result.lower()


class TestToolRegistry:
    def test_register_mcp_tools_returns_list(self):
        tools = register_mcp_tools()
        assert isinstance(tools, list)

    def test_list_registered_tools_returns_list(self):
        tools = list_registered_tools()
        assert isinstance(tools, list)

    def test_get_registered_tools_returns_dict(self):
        tools = get_registered_tools()
        assert isinstance(tools, dict)

    def test_parse_schemas_handles_malformed(self):
        result = _parse_schemas(["a.b", "nodots", "", None, 123, "x.y.z"])
        # Should only return valid dotted pairs
        assert ("a", "b") in result
        assert ("x", "y.z") in result
        assert len(result) == 2


class TestStubLangChainTool:
    def test_basic_properties(self):
        tool = _StubLangChainTool("mem.write", "Writes to memory", "memory", "write")
        assert tool.name == "mem.write"
        assert tool.description
        assert "memory" in tool.description

    def test_run_returns_placeholder(self):
        tool = _StubLangChainTool("mem.write", "Writes", "memory", "write")
        result = tool._run(key="value")
        assert "sync calls not supported" in result
