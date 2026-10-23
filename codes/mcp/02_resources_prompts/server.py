"""Stage-2 MCP resources + prompts on FastMCP + Pydantic.

Stage 1 covered tools. Here the same FastMCP server also exposes:

- a static resource (`lab://greeting`)
- a URI template (`note://{slug}`) — `{placeholder}` → function arg
- a prompt (`critique`) whose arguments come from Annotated + Field

Schemas and the MCP wire protocol stay with the framework (default era
`2026-07-28`). You still only write typed Python callables.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("lab-resources-prompts")


@mcp.resource("lab://greeting", mime_type="text/plain")
def greeting() -> str:
    """Static lab greeting (no URI parameters)."""
    return "hello from resources"


@mcp.resource("note://{slug}", mime_type="text/markdown")
def note(slug: str) -> str:
    """Templated note: clients read `note://alpha`, `note://beta`, …"""
    return f"# note:{slug}\nbody for {slug}"


@mcp.prompt
def critique(
    topic: Annotated[str, Field(description="What to critique")],
) -> str:
    """Build a short critique prompt the host can feed to a model."""
    return f"Critique this topic in 3 bullets:\n{topic}"


if __name__ == "__main__":
    mcp.run()
