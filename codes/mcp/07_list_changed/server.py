"""Stage-7 MCP list_changed + resource updated notifications on FastMCP.

Stages 1–6 covered tools, resources/prompts, Context progress, structured
output, completions, and tool annotations. Hosts that keep a live catalog
also need **change signals** — not only one-shot list/read.

This lab stays honest on the `2026-07-28` era:

- No `Context.sample` (sampling back-channel still absent in FastMCP 4.1)
- No roots / imperative elicitation (server→client request path removed)
- No protocol logging (`notifications/message` / `ctx.info` — SEP-2577)
- No `resources/subscribe` (removed; modern wire is `subscriptions/listen`,
  which FastMCP's Client does not wrap yet)

What *is* current and client-visible: session notifications the host
observes via `Client(..., message_handler=...)`:

- `notifications/tools/list_changed` — FastMCP sends these when
  `ctx.enable_components` / `ctx.disable_components` change visibility
- `notifications/resources/updated` — send explicitly with
  `ctx.send_notification(ResourceUpdatedNotification(...))` after you
  mutate resource bytes the host already read

Same FastMCP + Pydantic stack; no extra deps. See README.md for the skip
rationale in one place.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import Context, FastMCP
from mcp.types import ResourceUpdatedNotification, ResourceUpdatedNotificationParams
from pydantic import Field

mcp = FastMCP("lab-list-changed")

BOARD_URI = "lab://board"

# Mutable board body the resource re-reads on every resources/read.
_BOARD: dict[str, str] = {"text": "welcome"}


@mcp.resource(BOARD_URI, mime_type="text/plain")
def board() -> str:
    """Current board text (re-read after resources/updated)."""
    return _BOARD["text"]


@mcp.tool
async def post_board(
    text: Annotated[str, Field(description="New board text")],
    ctx: Context,
) -> str:
    """Replace the board body and notify subscribers of the URI update."""
    _BOARD["text"] = text
    await ctx.send_notification(
        ResourceUpdatedNotification(
            params=ResourceUpdatedNotificationParams(uri=BOARD_URI),
        )
    )
    return f"posted:{len(text)}"


@mcp.tool
async def unlock_secret(ctx: Context) -> str:
    """Reveal the previously hidden `secret_ping` tool for this session."""
    await ctx.enable_components(names=["secret_ping"])
    return "unlocked"


@mcp.tool
def secret_ping() -> str:
    """Hidden until unlock_secret enables it (list_changed → refetch tools)."""
    return "pong"


# Start hidden — hosts that list tools before unlock must not see it.
mcp.disable(names=["secret_ping"])


if __name__ == "__main__":
    mcp.run()
