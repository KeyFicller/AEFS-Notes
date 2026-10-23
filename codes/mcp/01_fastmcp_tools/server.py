"""Stage-1 MCP tools server backed by FastMCP + Pydantic.

Schemas and the MCP wire protocol come from the framework — we only write
typed Python callables. FastMCP 4 defaults to the 2026-07-28 era.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("lab-tools-server")


@mcp.tool
def echo(
    text: Annotated[str, Field(description="Text to return unchanged")],
) -> str:
    """Return the given text unchanged."""
    return text


@mcp.tool
def add(
    a: Annotated[float, Field(description="Left operand")],
    b: Annotated[float, Field(description="Right operand")],
) -> str:
    """Add two numbers and return the sum as text."""
    return str(a + b)


if __name__ == "__main__":
    mcp.run()
