"""MCP (Model Context Protocol) integration — stdio transport for Memory, Sequential Thinking, Filesystem servers."""
from mcp.client import (
    MCP_AVAILABLE,
    MCPClientManager,
    MCPStdioClient,
    get_mcp_manager,
)
from mcp.tool_registry import (
    get_registered_tools,
    list_registered_tools,
    register_mcp_tools,
)

__all__ = [
    "MCP_AVAILABLE",
    "MCPClientManager",
    "MCPStdioClient",
    "get_mcp_manager",
    "get_registered_tools",
    "list_registered_tools",
    "register_mcp_tools",
]
