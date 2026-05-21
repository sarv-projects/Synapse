"""MCP tool registry — wraps MCP tools as LangChain-compatible tools."""
import logging

logger = logging.getLogger(__name__)


def register_mcp_tools() -> list:
    """Return MCP tools wrapped as LangChain-compatible tool objects."""
    from mcp.client import get_mcp_manager
    manager = get_mcp_manager()
    schemas = manager.get_tool_schemas()
    logger.info(f"Registered {len(schemas)} MCP tools")
    return schemas
