"""Tiny stdio MCP server used by test_mcp_client.py. No GCP, no network."""
import time

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

mcp = MCPServer("echo")


class Echo(BaseModel):
    text: str


class Meta(BaseModel):
    conversation_id: str | None
    node: str | None


@mcp.tool()
def echo(text: str) -> Echo:
    return Echo(text=text)


@mcp.tool()
def meta(ctx: Context, session_token: str = "", document_number: str = "", card_id: str = "") -> Meta:
    """Returns the request _meta the client sent (correlation id)."""
    m = ctx.request_context.meta or {}
    return Meta(conversation_id=m.get("conversation_id"), node=m.get("node"))


@mcp.tool()
def boom() -> Echo:
    raise ToolError("secret detail that must not leak")


@mcp.tool()
def expired() -> Echo:
    raise ToolError("session_invalid")


@mcp.tool()
def slow() -> Echo:
    time.sleep(10)
    return Echo(text="late")


if __name__ == "__main__":
    mcp.run(transport="stdio")
