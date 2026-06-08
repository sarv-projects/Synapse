"""MCP client layer — stdio transport for Memory, Sequential Thinking, Filesystem servers.

This module provides a resilient stdio client for the Model Context
Protocol.  When the official ``mcp`` Python package is unavailable, the
client is constructed normally and ``connect()`` simply returns ``False``
instead of raising — callers can detect the absence and fall back to
placeholder stubs.

Improvements over the original:
* Specific exception types (``OSError``, ``asyncio.TimeoutError``, ``ValueError``)
  instead of a bare ``except Exception`` blanket.
* ``health_check()`` method to verify a server is still alive before
  sending a tool call (avoids writing to a closed pipe).
* ``reconnect()`` helper that tears down and re-establishes a connection
  with bounded backoff.
* ``is_available`` property for the manager — fast-path that avoids
  iterating servers when none are configured.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MCP_AVAILABLE = False
try:
    import mcp  # type: ignore # noqa: F401
    MCP_AVAILABLE = True
except ImportError:
    logger.warning("mcp package not installed; MCP tools will use placeholder stubs")


# ── Helpers ─────────────────────────────────────────────────────────────────


class MCPError(Exception):
    """Raised for recoverable MCP protocol / transport failures."""


class MCPConnectionError(MCPError):
    """Raised when the connection to a server has been lost."""


# ── Single-server client ────────────────────────────────────────────────────


class MCPStdioClient:
    """Manages a subprocess MCP server via stdio transport."""

    HANDSHAKE_TIMEOUT: float = 15.0
    REQUEST_TIMEOUT: float = 30.0
    READ_LINE_TIMEOUT: float = 10.0

    def __init__(
        self,
        name: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("MCPStdioClient requires a non-empty name")
        self.name = name
        self.command: List[str] = list(command or [])
        if self.command and not all(isinstance(part, str) for part in self.command):
            raise ValueError("MCPStdioClient command parts must all be strings")
        self.env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._connected: bool = False
        self._last_activity: float = 0.0

    @property
    def connected(self) -> bool:
        return self._connected and self._process is not None and self._process.returncode is None

    async def connect(self) -> bool:
        """Spawn the server process and perform the MCP handshake."""
        if not self.command or not self.command[0]:
            logger.warning("MCP %s: no command configured, check env vars", self.name)
            return False
        if self.connected:
            return True
        try:
            full_env = {**os.environ, **self.env}
            self._process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=full_env,
                ),
                timeout=self.HANDSHAKE_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as e:
            logger.warning("MCP %s: spawn failed: %s", self.name, e)
            self._process = None
            return False
        except FileNotFoundError as e:
            logger.warning("MCP %s: binary not found: %s", self.name, e)
            self._process = None
            return False

        try:
            await self._initialize()
        except (MCPError, asyncio.TimeoutError, ValueError) as e:
            logger.warning("MCP %s: handshake failed: %s", self.name, e)
            await self._terminate()
            return False

        self._connected = True
        self._last_activity = time.monotonic()
        logger.info("MCP %s: connected via stdio", self.name)
        return True

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Invoke a tool and return its textual result."""
        if not self.connected:
            return f"[MCP:{self.name}] Not connected"
        if not isinstance(tool_name, str) or not tool_name:
            return f"[MCP:{self.name}] invalid tool name"
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        request = json.dumps({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        try:
            response = await self._send_request(request)
        except (MCPError, asyncio.TimeoutError) as e:
            logger.warning("MCP %s: tool %s failed: %s", self.name, tool_name, e)
            await self._terminate()
            return f"[MCP:{self.name}:{tool_name}] request failed: {e}"

        if response and "result" in response:
            content = response["result"].get("content", [])
            if content:
                first = content[0]
                if isinstance(first, dict):
                    return first.get("text", str(content))
                return str(first)
        return f"[MCP:{self.name}:{tool_name}] No result"

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    async def health_check(self) -> bool:
        """Return True if the process is alive and stdin/stdout are usable."""
        if not self._process:
            return False
        if self._process.returncode is not None:
            return False
        if not self._process.stdin or self._process.stdin.is_closing():
            return False
        if not self._process.stdout or self._process.stdout.at_eof():
            return False
        return True

    async def reconnect(self, attempts: int = 2) -> bool:
        """Tear down the current connection and try to re-establish it."""
        await self._terminate()
        for i in range(max(1, attempts)):
            ok = await self.connect()
            if ok:
                return True
            if i < attempts - 1:
                await asyncio.sleep(0.5 * (i + 1))
        return False

    async def close(self) -> None:
        await self._terminate()

    # ── internals ─────────────────────────────────────────────────────────

    async def _initialize(self) -> None:
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        response = await self._send_request(request)
        if response is None:
            raise MCPError("no response to tools/list")
        if "error" in response:
            raise MCPError(f"server reported error: {response['error']}")
        tools = response.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise MCPError("invalid tools/list response shape")
        validated: Dict[str, Dict[str, Any]] = {}
        for t in tools:
            if isinstance(t, dict) and isinstance(t.get("name"), str):
                validated[t["name"]] = t
        self._tools = validated

    async def _send_request(self, request_str: str) -> Optional[Dict[str, Any]]:
        """Write one request, read one response. Returns None on EOF."""
        if (not self._process or not self._process.stdin or not self._process.stdout):
            raise MCPConnectionError("process not running")
        try:
            self._process.stdin.write((request_str + "\n").encode())
            await self._process.stdin.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            raise MCPConnectionError(f"write failed: {e}") from e

        try:
            line = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=self.READ_LINE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise

        if not line:
            raise MCPConnectionError("EOF on stdout")
        try:
            payload = json.loads(line.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise MCPError(f"invalid JSON response: {e}") from e
        self._last_activity = time.monotonic()
        return payload

    async def _terminate(self) -> None:
        if not self._process:
            self._connected = False
            return
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._process.kill()
            try:
                await self._process.wait()
            except Exception:  # pragma: no cover - best effort
                pass
        except ProcessLookupError:
            pass
        finally:
            self._process = None
            self._connected = False
            self._tools = {}


# ── Multi-server manager ────────────────────────────────────────────────────


class MCPClientManager:
    """Manages Memory, Sequential Thinking, and Filesystem MCP servers."""

    def __init__(self) -> None:
        self._servers: Dict[str, MCPStdioClient] = {}
        self._connect_lock = asyncio.Lock()
        self._init_servers()

    @property
    def is_available(self) -> bool:
        """Fast path: do we have any servers configured at all?"""
        return bool(self._servers)

    def _init_servers(self) -> None:
        """Read env vars and construct per-server clients."""
        for env_var, server_name in (
            ("MCP_MEMORY_PATH", "memory"),
            ("MCP_SEQUENTIAL_THINKING_PATH", "sequential_thinking"),
            ("MCP_FILESYSTEM_PATH", "filesystem"),
        ):
            path = os.getenv(env_var, "")
            if not path:
                continue
            env_json = os.getenv(f"{env_var.rsplit('_PATH', 1)[0]}_ENV", "")
            extra_env: Dict[str, str] = {}
            if env_json:
                try:
                    import json as _json
                    parsed = _json.loads(env_json)
                    if isinstance(parsed, dict):
                        extra_env = {str(k): str(v) for k, v in parsed.items()}
                except (ValueError, TypeError) as e:
                    logger.warning("MCP %s: invalid %s_ENV JSON: %s", server_name, env_var, e)
            self._servers[server_name] = MCPStdioClient(server_name, [path], env=extra_env)

    async def connect_all(self) -> Dict[str, bool]:
        """Connect to all configured servers in parallel."""
        if not self._servers:
            return {}
        async with self._connect_lock:
            results = await asyncio.gather(
                *(server.connect() for server in self._servers.values()),
                return_exceptions=True,
            )
        out: Dict[str, bool] = {}
        for (name, server), result in zip(self._servers.items(), results):
            if isinstance(result, BaseException):
                logger.warning("MCP %s connect raised: %s", name, result)
                out[name] = False
            else:
                out[name] = bool(result)
        return out

    async def close_all(self) -> None:
        """Terminate every server subprocess. Safe to call multiple times."""
        servers = list(self._servers.values())
        self._servers.clear()
        for server in servers:
            try:
                await server.close()
            except (OSError, asyncio.TimeoutError, ProcessLookupError) as e:
                logger.warning("MCP %s close failed: %s", server.name, e)

    def get_tool_schemas(self) -> List[str]:
        """Return ``server.tool`` style names for every known tool."""
        schemas: List[str] = []
        for name, server in self._servers.items():
            for tool_name in server.get_tool_names():
                schemas.append(f"{name}.{tool_name}")
        if not schemas:
            return [
                "memory.write", "memory.read",
                "sequential_thinking.reason",
                "filesystem.read", "filesystem.write",
            ]
        return schemas

    async def call_tool(self, full_name: str, **kwargs: Any) -> str:
        """Route a dotted tool name to the right server."""
        if not isinstance(full_name, str) or "." not in full_name:
            return f"[MCP] invalid tool name: {full_name!r}"
        server_name, _, tool_name = full_name.partition(".")
        server = self._servers.get(server_name)
        if server is None:
            return f"[MCP] Tool {full_name} not found"
        if not await server.health_check():
            ok = await server.reconnect(attempts=2)
            if not ok:
                return f"[MCP:{server_name}] Not connected"
        return await server.call_tool(tool_name, kwargs)


# ── Singleton ───────────────────────────────────────────────────────────────

_mcp_manager: Optional[MCPClientManager] = None


def get_mcp_manager() -> MCPClientManager:
    """Return the global MCPClientManager singleton."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager


def reset_mcp_manager() -> None:
    """Tear down and clear the global manager - used by tests."""
    global _mcp_manager
    if _mcp_manager is not None:
        asyncio.run(_mcp_manager.close_all())
    _mcp_manager = None
