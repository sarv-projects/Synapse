"""MCP client layer — stdio transport for Memory, Sequential Thinking, Filesystem servers."""
import asyncio
import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

MCP_AVAILABLE = False
try:
    import mcp  # noqa: F401
    MCP_AVAILABLE = True
except ImportError:
    logger.warning("mcp package not installed; MCP tools will use placeholder stubs")


class MCPStdioClient:
    """Manages a subprocess MCP server via stdio transport."""

    def __init__(self, name: str, command: list[str], env: dict | None = None):
        self.name = name
        self.command = command
        self.env = env or {}
        self._process: subprocess.Popen | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tools: dict[str, dict[str, Any]] = {}
        self._connected = False

    async def connect(self) -> bool:
        if not self.command or not self.command[0]:
            logger.warning(f"MCP {self.name}: no command configured, check env vars")
            return False
        try:
            full_env = {**os.environ, **self.env}
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
            )
            loop = asyncio.get_event_loop()
            self._reader = asyncio.StreamReader(loop=loop)
            self._writer = asyncio.StreamWriter(
                self._process.stdin, None, self._reader, loop
            )
            await self._initialize()
            self._connected = True
            logger.info(f"MCP {self.name}: connected via stdio")
            return True
        except Exception as e:
            logger.warning(f"MCP {self.name}: connection failed: {e}")
            return False

    async def _initialize(self):
        request = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
        })
        response = await self._send_request(request)
        if response:
            tools = response.get("result", {}).get("tools", [])
            self._tools = {t["name"]: t for t in tools}

    async def _send_request(self, request_str: str) -> dict | None:
        if not self._writer or not self._process or not self._process.stdout:
            return None
        try:
            self._writer.write((request_str + "\n").encode())
            await self._writer.drain()
            line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._process.stdout.readline
                ),
                timeout=10.0,
            )
            if line:
                return json.loads(line.decode())
        except Exception as e:
            logger.debug(f"MCP {self.name}: request failed: {e}")
        return None

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self._connected:
            return f"[MCP:{self.name}] Not connected"

        request = json.dumps({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        response = await self._send_request(request)
        if response and "result" in response:
            content = response["result"].get("content", [])
            if content:
                return content[0].get("text", str(content))
        return f"[MCP:{self.name}:{tool_name}] No result"

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def close(self):
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._connected = False


class MCPClientManager:
    """Manages Memory, Sequential Thinking, and Filesystem MCP servers."""

    def __init__(self):
        self._servers: dict[str, MCPStdioClient] = {}
        self._tool_wrappers: dict[str, callable] = {}
        self._init_servers()

    def _init_servers(self):
        memory_path = os.getenv("MCP_MEMORY_PATH", "")
        seqthink_path = os.getenv("MCP_SEQUENTIAL_THINKING_PATH", "")
        filesystem_path = os.getenv("MCP_FILESYSTEM_PATH", "")

        if memory_path:
            self._servers["memory"] = MCPStdioClient("memory", [memory_path])
        if seqthink_path:
            self._servers["sequential_thinking"] = MCPStdioClient("sequential_thinking", [seqthink_path])
        if filesystem_path:
            self._servers["filesystem"] = MCPStdioClient("filesystem", [filesystem_path])

    async def connect_all(self):
        for name, server in self._servers.items():
            await server.connect()

    async def close_all(self):
        try:
            for server in self._servers.values():
                await server.close()
        finally:
            self._servers.clear()

    def get_tool_schemas(self) -> list[str]:
        schemas = []
        for name, server in self._servers.items():
            for tool_name in server.get_tool_names():
                schemas.append(f"{name}.{tool_name}")
        return schemas or ["memory.write", "memory.read", "seqthink.reason", "fs.read", "fs.write"]

    async def call_tool(self, full_name: str, **kwargs) -> str:
        parts = full_name.split(".", 1)
        if len(parts) == 2 and parts[0] in self._servers:
            return await self._servers[parts[0]].call_tool(parts[1], kwargs)
        return f"[MCP] Tool {full_name} not found"


_mcp_manager: MCPClientManager | None = None


def get_mcp_manager() -> MCPClientManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager
