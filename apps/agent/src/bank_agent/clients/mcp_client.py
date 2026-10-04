"""Synchronous client for the bank MCP server.

Graph nodes are synchronous and the MCP SDK is async, so one background thread
runs an event loop that owns a persistent ClientSession. A single owner task
opens and closes the transport (anyio requires enter/exit in the same task);
calls are scheduled onto the loop and awaited with a timeout.
"""
import asyncio
import concurrent.futures
import logging
import threading
from pathlib import Path
from typing import Any

from bank_agent.clients.contracts import ServiceFailure, SessionExpired

logger = logging.getLogger(__name__)

# Error text the bank MCP server returns for a bad, expired or forged session token.
SESSION_INVALID = "session_invalid"


def _error_code(result) -> str:
    """The server's message without the SDK's 'Error executing tool <name>: ' prefix."""
    text = " ".join(getattr(c, "text", "") for c in result.content or []).strip()
    return text.rpartition(": ")[2]


class McpToolClient:
    def __init__(self, *, url: str | None = None, command: str | None = None, args: list[str] | None = None,
                 cwd: str | Path | None = None, timeout_s: float = 30.0):
        if bool(url) == bool(command):
            raise ValueError("Provide exactly one of url (streamable HTTP) or command (stdio).")
        self._url, self._command, self._args, self._cwd = url, command, args or [], cwd
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._owner: concurrent.futures.Future | None = None
        self._session = None
        self._stop: asyncio.Event | None = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def _transport(self):
        if self._url:
            from mcp.client.streamable_http import streamable_http_client
            return streamable_http_client(self._url)
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        return stdio_client(StdioServerParameters(command=self._command, args=self._args, cwd=self._cwd))

    async def _own(self, ready: concurrent.futures.Future) -> None:
        from mcp import ClientSession
        try:
            async with self._transport() as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    self._session, self._stop = session, asyncio.Event()
                    ready.set_result(None)
                    await self._stop.wait()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            else:
                logger.warning("MCP session ended: %s", type(exc).__name__)
        finally:
            self._session = None

    def start(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, name="mcp-client", daemon=True)
                self._thread.start()
            ready: concurrent.futures.Future = concurrent.futures.Future()
            self._owner = asyncio.run_coroutine_threadsafe(self._own(ready), self._loop)
            try:
                ready.result(timeout=self.timeout_s)
            except Exception as exc:
                raise ServiceFailure("MCP server unavailable") from exc

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return its structured result; any problem is a ServiceFailure."""
        self.start()
        future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, arguments), self._loop)
        try:
            result = future.result(timeout=self.timeout_s)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ServiceFailure(f"{name} timed out") from exc
        except Exception as exc:
            raise ServiceFailure(f"{name} failed") from exc
        if result.is_error:
            # Server error text stays in logs; it is not shown to the customer.
            logger.info("MCP tool %s returned an error", name)
            if _error_code(result) == SESSION_INVALID:
                raise SessionExpired()
            raise ServiceFailure(f"{name} returned an error")
        if not isinstance(result.structured_content, dict):
            raise ServiceFailure(f"{name} returned no structured content")
        return result.structured_content

    def close(self) -> None:
        with self._lock:
            if self._loop is None:
                return
            if self._stop is not None:
                self._loop.call_soon_threadsafe(self._stop.set)
            if self._owner is not None:
                try:
                    self._owner.result(timeout=self.timeout_s)
                except Exception:
                    logger.warning("MCP session did not close cleanly")
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=self.timeout_s)
            self._loop.close()
            self._loop = self._thread = self._owner = self._stop = None
