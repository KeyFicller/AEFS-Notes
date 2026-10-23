"""Stage-3 MCP Context + progress on FastMCP + Pydantic.

Stages 1–2 covered tools, resources, and prompts. Long-running tools also
need to talk back while they work. Inject FastMCP's `Context` (not part of
the tool's JSON Schema) and call `report_progress` with **absolute** values.

Protocol-level logging (`notifications/message` / `ctx.info`) is deprecated
in the `2026-07-28` era (SEP-2577) — this lab stays on progress, which is
still current. Use stderr / OpenTelemetry for ordinary server logs.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

mcp = FastMCP("lab-context-progress")


@mcp.tool
async def count_up(
    n: Annotated[int, Field(description="How many steps (1..5)", ge=1, le=5)],
    ctx: Context,
) -> str:
    """Count 1..n, reporting absolute progress after each step."""
    for i in range(1, n + 1):
        await ctx.report_progress(
            progress=float(i),
            total=float(n),
            message=f"step {i}",
        )
    return f"done:{n}"


if __name__ == "__main__":
    mcp.run()
