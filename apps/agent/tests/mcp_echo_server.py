"""Tiny stdio MCP server used by test_mcp_client.py. No GCP, no network."""
import time

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

mcp = MCPServer("echo")


class Echo(BaseModel):
    text: str


@mcp.tool()
def echo(text: str) -> Echo:
    return Echo(text=text)


@mcp.tool()
def boom() -> Echo:
    raise ToolError("secret detail that must not leak")


@mcp.tool()
def slow() -> Echo:
    time.sleep(10)
    return Echo(text="late")


if __name__ == "__main__":
    mcp.run(transport="stdio")
